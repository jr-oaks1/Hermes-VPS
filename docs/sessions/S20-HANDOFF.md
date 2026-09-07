# S20 Handoff — JR Hermes VPS

**Session type:** Cross-project. Driven from **Clevious VPS S51** (session of record:
`Clevious VPS/sessions/S51-HANDOFF.md`). S51 left exactly one item on this project's plate —
provision the read-only role on the Hetzner primary that Clevious's standby-parity check needs.
**Date:** 2026-09-07 (confirmed against the Hetzner host clock live; the workstation harness
clock reported 2026-09-06 — it was the outlier).
**Status:** 🟢 `parity_reader` provisioned + live-verified on the Hetzner primary. Host
`running`, replication `streaming/async/0`, unaffected.

---

## Quick resume for S21

**Nothing open blocks this project.** The ball is in Clevious VPS's court (their S52): wire
`parity_reader` into `contabo_tier1_watch.py`.

**First checks in S21:**
- `bash /opt/hermes-vps/scripts/deploy_guardrail.sh` → all 9 steps green (exit 0).
- `git -C /opt/hermes-vps log -1` == the S20 commit.
- Optional: confirm Clevious's check went live (expect a reply to
  `docs/CROSS-PROJECT-NOTICE-2026-09-07-parity-reader-role-provisioned.md`).

---

## What S20 did

### The blocker (Clevious S51 C1-A)

`HERMES_PLATFORM_STANDARD.md` R5 "Standby parameter parity" mandates a primary↔standby diff
check on 5 replication-critical GUCs (`max_connections`, `max_worker_processes`,
`max_wal_senders`, `max_prepared_transactions`, `max_locks_per_transaction`), owned by Clevious
on the Contabo Tier-1 watch (accepted S16). Their `contabo_tier1_watch.py` must read those from
the **Hetzner primary** — and had **no role to connect with**. S51: *"needs a read-only role on
the Hetzner primary — still does not exist, JR Hermes VPS must provision it."*

### Provisioned

| field | value |
|---|---|
| host / port | `100.97.62.7` (Tailscale) : `5432` |
| database | `parity` — new, empty, zero objects, **not** in `/etc/pg_backup.conf` (nothing to lose) |
| role | `parity_reader` — `LOGIN` + `CONNECT` on `parity` only; `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; **no role memberships**; `CONNECTION LIMIT 3` |
| auth | `scram-sha-256`; `pg_hba` line scoped to `100.121.245.4/32` (Contabo) only |
| credential | `_credentials/jr_hermes_vps/parity_reader.md` (vault area, not git-tracked) |

**Why no `pg_monitor`:** `VPS_CONNECTIVITY_REFERENCE.md` §19.4 (S58) — `pg_monitor` bundles
`pg_read_all_settings`, which lets a role read `primary_conninfo` (replication password,
cleartext). The 5 target GUCs are non-restricted; any login role reads them from `pg_settings`.

### Files

- `deploy/sql/S20_parity_reader_role.sql` — role + DB + grants, idempotent, house style,
  ROLLBACK block in header. Run as `sudo -u postgres`, password via `-v pw="'…'"`.
- `pg_hba.conf` — one line added above the replication block (pull/edit/push per §15.5;
  backup `/etc/postgresql/16/main/pg_hba.conf.bak-s20`). **Not a repo file**; recorded in
  `VPS_CONNECTIVITY_REFERENCE.md`.
- `docs/CROSS-PROJECT-NOTICE-2026-09-07-parity-reader-role-provisioned.md` — to Clevious.
- `docs/VPS_CONNECTIVITY_REFERENCE.md` — roles table row + pg_hba block + stale-table caveat.
- `../HERMES_PLATFORM_STANDARD.md` R5 — names the provisioned read path (+ `/opt` sync).
- `_credentials/jr_hermes_vps/parity_reader.md`, `CLAUDE.md`, memory.

### Deliberately NOT done

- **Roles-table reconciliation in `VPS_CONNECTIVITY_REFERENCE.md`** — the table is missing
  `hermes_vps`, `audit_reader`, `hermes_ingestor` and predates several splits. Out of scope
  for a single-role change; caveat added inline. Worth a dedicated housekeeping pass.
- **`listen_addresses` / any postgresql.conf change** — not needed; replication already rides
  `100.97.62.7:5432`. The standing `pending_restart` is untouched.
- **Wiring the check** — Clevious's, their S52.

---

## VERIFICATION (live, 2026-09-07 — host clock confirmed 2026-09-07)

- [x] `pg_dumpall --roles-only` → `/opt/backups/pg_globals_pre-s20.sql`; `pg_hba.conf.bak-s20` (postgres:postgres 0640)
- [x] SQL smoke-tested in staged worktree — role/grant statements in `BEGIN; … ROLLBACK;`, all asserts pass, role gone after rollback
- [x] SQL applied for real from worktree `8d59895` — `CREATE DATABASE` / `CREATE ROLE` / `ALTER ROLE` / grants OK; step-5 all privilege flags `f`, `rolconnlimit=3`; step-6 `pg_read_all_settings`/`pg_monitor` both `f`; step-7 `can_connect_parity = t`; step-8 printed all 5 GUCs
- [x] `pg_hba` line appended above nothing / at end, scoped `100.121.245.4/32 → parity`; `pg_reload_conf()` = t; `pg_hba_file_rules` 0 errors, rule present
- [x] **positive (from Contabo, `ssh contabo-tailscale`):** `psql "host=100.97.62.7 dbname=parity user=parity_reader"` → `max_connections=100, max_worker_processes=23, max_wal_senders=10, max_prepared_transactions=0, max_locks_per_transaction=512`
- [x] **negative (from Contabo):** `dbname=hermes_v2` → `FATAL: no pg_hba.conf entry`; `dbname=postgres` → `FATAL: no pg_hba.conf entry`; `SELECT … pg_authid` → `permission denied`; wrong password → `password authentication failed`; `SHOW primary_conninfo` / `data_directory` → `permission denied … pg_read_all_settings`
- [x] `deploy_guardrail.sh` exit 0 — all T3.11 assertions pass (offline pytest skipped on host as always; step 7b green)
- [x] host `is-system-running`=running, 0 failed units, replication `100.121.245.4 streaming async 0`, disk 56%, 5 timers
- [x] `/opt/HERMES_PLATFORM_STANDARD.md` md5 `51bf3488…` == workspace copy
- [x] T-LOG.1 note row logged (`findings_log` + `@JRHermesVPSBot`) — `scripts/log_finding.py --category note --session S20` (`set -a; . /root/.hermes_vps/.env` first — the CLI needs `HERMES_VPS_LOG_DB_URL` in env)
- [x] credential in `_credentials/jr_hermes_vps/parity_reader.md` + `/root/.hermes_vps_credentials/CREDENTIALS.md` (S20 section, backup `.bak-s20`); temp `/root/.parity_reader.pw` removed

### GUC parity snapshot at provision time (for Clevious S52 context)

| GUC | Hetzner primary (via `parity_reader`) | Contabo standby (Clevious S50) | headroom |
|---|---|---|---|
| `max_connections` | 100 | 120 | +20 |
| `max_worker_processes` | 23 | 32 | +9 |
| `max_wal_senders` | 10 | 10 | **0** |
| `max_prepared_transactions` | 0 | 0 | 0 |
| `max_locks_per_transaction` | 512 | 512 | **0** |

`max_wal_senders` / `max_locks_per_transaction` still have **zero standby headroom** — the
open half of Clevious S51 (item C1-B, their side): raise the standby + restart. The check this
role feeds would now catch a primary-side bump of either before replay halts.

### Worktree / cleanup

`git worktree remove --force /opt/hermes-vps-s20` done; `/opt/hermes-vps` fast-forwarded to
`2d643fb` (matches `origin/main`).
