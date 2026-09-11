-- ===================================================================== --
-- S22 / JR Hermes VPS   (forensic-audit follow-up: S21 finding B8)
--   Drop the orphaned `crypto_platform` login role from the Hetzner
--   primary cluster (port 5432).
-- ===================================================================== --
--
-- WHY THIS ROLE IS AN ORPHAN (all verified live, S22, 2026-09-11):
--   * LOGIN role, NOSUPERUSER, no VALID UNTIL.
--   * 0 rows in pg_stat_activity (not connected now).
--   * 0 table / sequence / schema grants in `hermes_v2` (relacl scan empty).
--   * No `crypto*` database exists on this cluster (crypto_db was
--     decommissioned; S21 deleted the last archive dump).
--   * `/opt/crypto_platform/` does not exist on the host.
--   * No systemd unit references it (`grep -rl` over /etc/systemd/system).
--   * No recent connections in /var/log/postgresql/*.log.
--   * Only surviving references are documentation: this repo's
--     VPS_CONNECTIVITY_REFERENCE.md, and the `crypto_data` project
--     (workspace-root CLAUDE.md: "Legacy/superseded -- do not build on
--     this") whose bootstrap SQL / .env.template still name the role but
--     whose database and /opt deploy dir are both gone.
--
-- Run as SUPERUSER against the maintenance DB (dropping a global role is
-- owner/superuser work; the runtime role `hermes_vps` is unrelated to role
-- administration -- HERMES_PLATFORM_STANDARD.md R4 Exception; explicit user
-- OK obtained in the S22 session; reversible -- see ROLLBACK):
--
--     sudo -u postgres pg_dumpall --roles-only \
--          > /opt/backups/pg_globals_pre-s22.sql          # R5: back up first
--
--     sudo -u postgres psql -v ON_ERROR_STOP=1 \
--          -d postgres -f deploy/sql/S22_drop_crypto_platform_role.sql
--
-- SMOKE TEST FIRST (SMOKE-TEST BINDING RULE) -- prove no dependency error
-- without committing:
--     sudo -u postgres psql -d postgres <<'SQL'
--     BEGIN;
--     REVOKE ALL ON DATABASE hermes_v2 FROM crypto_platform;
--     DROP ROLE crypto_platform;
--     ROLLBACK;
--     SQL
--   A clean run (no ERROR) means the real apply below is safe.
--
-- ROLLBACK (per R5 -- recreates the exact pre-drop state; the role held no
-- data access, so nothing else needs restoring):
--     sudo -u postgres psql -d postgres -c \
--       "CREATE ROLE crypto_platform LOGIN;
--        GRANT CONNECT ON DATABASE hermes_v2 TO crypto_platform;"
--   (or: sudo -u postgres psql -f /opt/backups/pg_globals_pre-s22.sql,
--    which replays every global role line including this one.)
-- ===================================================================== --

\set ON_ERROR_STOP on

\echo '== 0. Pre-flight: connected as superuser to the primary cluster =='
SELECT current_user AS run_as_MUST_BE_postgres,
       inet_server_addr() AS server_addr,
       inet_server_port() AS server_port;

\echo '== 1. Confirm the role still exists and is still login-capable =='
SELECT rolname, rolcanlogin, rolsuper, rolvaliduntil
  FROM pg_roles
 WHERE rolname = 'crypto_platform';

\echo '== 2. HARD GATE: no owned objects / ACL entries anywhere in the cluster =='
-- pg_shdepend is cluster-wide: any ownership (o), ACL (a) or default-ACL (A)
-- dependency on this role in ANY database shows up here. Expected: 0 rows.
-- If this returns rows, STOP -- something still depends on the role.
SELECT dbid::regclass AS ignore, deptype, count(*)
  FROM pg_shdepend s
  JOIN pg_authid a ON a.oid = s.refobjid
 WHERE a.rolname = 'crypto_platform'
 GROUP BY 1, 2;

\echo '== 3. Not connected right now =='
SELECT count(*) AS active_connections_MUST_BE_0
  FROM pg_stat_activity WHERE usename = 'crypto_platform';

\echo '== 4. Revoke the only privilege it holds, then drop =='
REVOKE ALL ON DATABASE hermes_v2 FROM crypto_platform;
DROP ROLE crypto_platform;

\echo '== 5. VERIFY -- role is gone (MUST return 0 rows) =='
SELECT rolname FROM pg_roles WHERE rolname = 'crypto_platform';

\echo '== DONE. Update VPS_CONNECTIVITY_REFERENCE.md S5 (remove the row, 18 -> 17 login roles). =='
