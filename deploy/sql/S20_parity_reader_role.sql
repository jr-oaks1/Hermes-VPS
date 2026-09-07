-- ===================================================================== --
-- S20 / JR Hermes VPS  (cross-project origin: Clevious VPS S51 item C1-A)
--   Provision a dedicated remote read-only login role on the Hetzner
--   primary cluster (port 5432) so Clevious VPS's contabo_tier1_watch.py
--   can read the 5 replication-critical GUCs from the primary for its
--   standby-parameter-parity diff check (HERMES_PLATFORM_STANDARD.md R5
--   "Standby parameter parity"; detection accepted S16).
-- ===================================================================== --
--
-- Run as a SUPERUSER against the maintenance DB (creating a role + database
-- is owner/superuser work; the runtime role hermes_vps is unrelated to this
-- cluster -- HERMES_PLATFORM_STANDARD.md R5 + Exception 3; explicit user OK,
-- reversible):
--
--     SECRET=$(openssl rand -base64 24)
--     sudo -u postgres psql -v ON_ERROR_STOP=1 -v pw="'$SECRET'" \
--          -d postgres -f deploy/sql/S20_parity_reader_role.sql
--
-- Take a roles/globals backup first (R5 "back up before you edit"):
--     sudo -u postgres pg_dumpall --roles-only \
--          > /opt/backups/pg_globals_pre-s20.sql
--
-- NETWORK (applied separately, NOT by this script -- pull/edit/push per
-- VPS_CONNECTIVITY_REFERENCE.md S15.5, preserve postgres:postgres 0640):
--   cp /etc/postgresql/16/main/pg_hba.conf \
--      /etc/postgresql/16/main/pg_hba.conf.bak-s20
--   # add, ABOVE the replication block:
--   host  parity  parity_reader  100.121.245.4/32  scram-sha-256
--   sudo -u postgres psql -c "SELECT pg_reload_conf();"
-- No postgresql.conf change and NO restart: the cluster already binds
-- 100.97.62.7:5432 (streaming replication rides it today); pg_hba is
-- reload-only.
--
-- WHY least-privilege matters here: VPS_CONNECTIVITY_REFERENCE.md S19.4
-- (S58) -- pg_monitor bundles pg_read_all_settings, which on a node lets a
-- role read primary_conninfo (the replication password, cleartext). The 5
-- target GUCs are non-restricted settings visible to ANY login role via
-- pg_settings / SHOW, so this role gets NO role memberships at all.
--
-- The 5 GUCs Clevious reads with this role:
--   max_connections, max_worker_processes, max_wal_senders,
--   max_prepared_transactions, max_locks_per_transaction
--
-- ROLLBACK (per R5):
--   sudo -u postgres psql -d postgres -c "DROP DATABASE IF EXISTS parity;"
--   sudo -u postgres psql -d postgres -c "DROP ROLE IF EXISTS parity_reader;"
--   cp /etc/postgresql/16/main/pg_hba.conf.bak-s20 \
--      /etc/postgresql/16/main/pg_hba.conf
--   sudo -u postgres psql -c "SELECT pg_reload_conf();"
--   Nothing else on the host depends on the role; replication is untouched.
-- ===================================================================== --

\set ON_ERROR_STOP on

\echo '== 0. Pre-flight: connected as superuser to the primary cluster =='
SELECT current_user AS run_as_MUST_BE_postgres,
       inet_server_addr() AS server_addr,
       inet_server_port() AS server_port;

\echo '== 1. Create the empty holding database "parity" (idempotent) =='
SELECT 'CREATE DATABASE parity OWNER postgres'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'parity')\gexec

\echo '== 2. Create / refresh the parity_reader login role (idempotent) =='
SELECT format('CREATE ROLE parity_reader LOGIN CONNECTION LIMIT 3 PASSWORD %L', :'pw')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'parity_reader')\gexec

ALTER ROLE parity_reader
      LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
      CONNECTION LIMIT 3
      PASSWORD :'pw';

\echo '== 3. Database CONNECT privileges: parity only, PUBLIC revoked there =='
REVOKE CONNECT ON DATABASE parity   FROM PUBLIC;
GRANT  CONNECT ON DATABASE parity   TO   parity_reader;

-- Defense in depth: make sure the role can never reach the app databases on
-- this cluster even if PUBLIC connect is ever re-granted on one of them.
REVOKE CONNECT ON DATABASE hermes_v2 FROM parity_reader;
SELECT format('REVOKE CONNECT ON DATABASE %I FROM parity_reader', datname)
  FROM pg_database
 WHERE datname IN ('crypto_db', 'crypto_signals')\gexec

\echo '== 4. Lock down the public schema inside "parity" =='
\connect parity
REVOKE ALL ON SCHEMA public FROM parity_reader;

\echo '== 5. VERIFY -- role attributes (all privilege flags MUST be false) =='
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolconnlimit
  FROM pg_roles
 WHERE rolname = 'parity_reader';

\echo '== 6. VERIFY -- no elevated role memberships (both MUST be f) =='
SELECT pg_has_role('parity_reader', 'pg_read_all_settings', 'MEMBER')
         AS has_pg_read_all_settings_MUST_BE_F,
       pg_has_role('parity_reader', 'pg_monitor', 'MEMBER')
         AS has_pg_monitor_MUST_BE_F;

\echo '== 7. VERIFY -- database reachability =='
SELECT has_database_privilege('parity_reader', 'parity',    'CONNECT')
         AS can_connect_parity_MUST_BE_T,
       has_database_privilege('parity_reader', 'hermes_v2',  'CONNECT')
         AS can_connect_hermes_v2_MUST_BE_F;

\echo '== 8. VERIFY -- the 5 GUCs are readable in this session (proof of concept) =='
SELECT name, setting, unit
  FROM pg_settings
 WHERE name IN ('max_connections', 'max_worker_processes', 'max_wal_senders',
                'max_prepared_transactions', 'max_locks_per_transaction')
 ORDER BY name;

\echo '== DONE. Now apply the pg_hba.conf line (see header) and reload. =='
\echo '== Then verify AS THE ROLE from the primary:'
\echo '==   psql "host=100.97.62.7 dbname=parity user=parity_reader" \'
\echo '==        -c "SELECT name,setting FROM pg_settings WHERE name IN (...)"'
