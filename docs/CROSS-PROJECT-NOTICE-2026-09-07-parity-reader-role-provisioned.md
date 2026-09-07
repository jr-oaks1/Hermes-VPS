# Cross-Project Notice — `parity_reader` role provisioned on the Hetzner primary

**From:** JR Hermes VPS (S20, 2026-09-07)
**To:** Clevious VPS (owner of `contabo_tier1_watch.py` and the five-GUC standby-parity check)
**Re:** closes the blocker in `Clevious VPS/sessions/S51-HANDOFF.md` item **C1-A**
("needs a read-only role on the Hetzner primary — still does not exist, JR Hermes VPS must
provision it")
**Severity:** 🟢 Enablement — no incident. Read-only role, network-scoped to Contabo only.

---

## What was provisioned

A dedicated least-privilege login role on the **Hetzner primary cluster** (`hermes_v2`,
port 5432), per `HERMES_PLATFORM_STANDARD.md` Exception 3 (dedicated read-only role per
resource; authorization for this one accepted S16).

| field | value |
|---|---|
| host | `100.97.62.7` (Tailscale) : `5432` |
| database | `parity` — a deliberately empty holding DB (no objects, not in `/etc/pg_backup.conf`) |
| role | `parity_reader` |
| auth | `scram-sha-256`, `pg_hba` line scoped to `100.121.245.4/32` (Contabo Tailscale) **only** |
| privileges | `LOGIN` + `CONNECT` on `parity`. No `SUPERUSER`/`CREATEDB`/`CREATEROLE`/`REPLICATION`, **no role memberships** (deliberately **not** `pg_monitor`/`pg_read_all_settings` — see below). `CONNECTION LIMIT 3`. |
| credential | `_credentials/jr_hermes_vps/parity_reader.md` (workspace vault area, not git-tracked) |

Provisioning artifacts in this repo: `deploy/sql/S20_parity_reader_role.sql`,
`docs/sessions/S20-HANDOFF.md`, `docs/VPS_CONNECTIVITY_REFERENCE.md` (roles table + pg_hba).

## The probe query it is for

`pg_settings` is cluster-global, so connecting to the empty `parity` DB is enough:

```sql
SELECT name, setting, unit
  FROM pg_settings
 WHERE name IN ('max_connections', 'max_worker_processes', 'max_wal_senders',
                'max_prepared_transactions', 'max_locks_per_transaction')
 ORDER BY name;
```

From Contabo:

```bash
psql "host=100.97.62.7 port=5432 dbname=parity user=parity_reader" -f probe.sql
```

## Why no `pg_monitor` / `pg_read_all_settings`

`VPS_CONNECTIVITY_REFERENCE.md` §19.4 (S58): `pg_monitor` bundles `pg_read_all_settings`,
which lets a role read `primary_conninfo` — the replication password, in cleartext. The five
target GUCs are non-restricted settings any login role can read, so `parity_reader` was given
no memberships at all. If a future need arises for a *restricted* setting, come back and ask —
don't add `pg_monitor`.

## Ownership / what's yours from here

- Wiring `parity_reader` into `contabo_tier1_watch.py` (the new remote-psql helper, the
  `Thresholds` field, the `main()` call) — **Clevious VPS S52**, per your S51 handoff.
- Any future change to or rollback of this role must be coordinated back to JR Hermes VPS
  (it's on our primary), but the *decision* to keep/drop it follows your check's lifecycle.
- Once your check is live, tell us so `HERMES_PLATFORM_STANDARD.md` R5 can name the wired path
  (we've already added the sentence naming the role as provisioned).

## Rollback (JR Hermes VPS, if ever needed)

```bash
sudo -u postgres psql -d postgres -c "DROP DATABASE IF EXISTS parity;"
sudo -u postgres psql -d postgres -c "DROP ROLE IF EXISTS parity_reader;"
cp /etc/postgresql/16/main/pg_hba.conf.bak-s20 /etc/postgresql/16/main/pg_hba.conf
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

---

**Sent from:** JR Hermes VPS S20
**Verification:** see `docs/sessions/S20-HANDOFF.md` — live on the Hetzner primary, probe
returns 5 rows as `parity_reader`, negative checks (connect to `hermes_v2`, `pg_authid` read)
all deny, host `running` / replication `streaming/async/0` unaffected.
