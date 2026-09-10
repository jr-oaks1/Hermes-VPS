# S21 Handoff — JR Hermes VPS

**Session type:** Housekeeping — close the last open JR-Hermes-VPS-owned pending
(P2 from S19b): reconcile the stale PostgreSQL roles table in
`docs/VPS_CONNECTIVITY_REFERENCE.md`.
**Date:** 2026-09-10.
**Numbering:** user first said "session 20"; `S19-HANDOFF.md` + `S20-HANDOFF.md`
already exist on disk (2026-09-07, the Clevious-driven parity_reader sessions) and
S19b (2026-09-10) said to verify disk and expect S21 — confirmed with user →
**this session is S21**. `S19b` was the last real work; `S20` untouched.
Next handoff = **S22**.

**Status:** 🟢 DONE. P2 closed. No infra changes — read-only live inventory only.
Host `running`, 0 failed units, 0 open/in_progress findings, replication
`streaming/async/0`, disk 54%.

---

## Quick resume for next session

**Nothing JR-Hermes-VPS-owned is open.** All remaining pendings are other projects'
(see §4). First checks unchanged from S19b:
- `systemctl is-system-running` = running; `systemctl --failed` empty.
- `bash /opt/hermes-vps/scripts/deploy_guardrail.sh` → all 9 green.
- `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT action_status,count(*) FROM findings_log WHERE action_status IN ('open','in_progress') GROUP BY 1"` → 0 rows.

---

## 1. What was done

Rewrote the **`### PostgreSQL roles`** subsection of
`docs/VPS_CONNECTIVITY_REFERENCE.md` §5 (was ~9 rows, mixed hosts, self-admittedly
stale since S20). New content, all from a **live read-only inventory this session**
(`pg_roles` / `pg_database` / `pg_hba_file_rules` / `information_schema.role_table_grants`
on both hosts, `sudo -u postgres`):

- **Databases mini-table** (new) — the 6 Hetzner `:5432` DBs + owners.
- **Full Hetzner `:5432` roles table** — 18 login roles + `vps_orchestrator`
  (NOLOGIN). Columns: Role | Scope | Privilege | Owns | Used by / provenance.
- **Contabo `:5434`** crypto_signals-primary role list (compact, pointer to
  Clevious/PionexBots/GM docs as authority — not ours).
- **Cross-host `pg_hba` grant matrix** into the Hetzner primary (8 error-free rules).
- Replaced the "table is stale" footnote with a dated "reconciled live S21" note.

### Live inventory captured (for the record)

**Hetzner `:5432` login roles (18):** ag_btc_reader, audit_reader, crypto_platform,
crypto_signals_research, cyclestation, findings_reader, findings_writer,
hermes_ingestor, hermes_log_writer, hermes_v2, hermes_v2_writer, hermes_vps,
hermes_vps_writer, market_sentinel_reader, parity_reader (conn-limit 3), pgbackup,
postgres (SUPERUSER), replicator (REPLICATION). **NOLOGIN:** vps_orchestrator.
No `VALID UNTIL` on any role.

**Memberships:** `audit_reader`→`pg_read_all_stats`; `pgbackup`→`pg_read_all_data`.
Every other custom role holds **no** memberships.

**DBs / owners:** hermes_v2 (postgres), hermes_v2_log (hermes_v2_writer),
hermes_vps_log (hermes_vps_writer), hermes_ingestor_log (postgres),
vps_orchestrator_findings (vps_orchestrator), parity (postgres).

**Table ownership in `hermes_v2` DB:** `public` — hermes_v2 ×34 (+2 views, +3 seq),
hermes_ingestor ×18 (+3 seq), crypto_signals_research ×4; schema `cyclestation`
(owner cyclestation) ×7 (+7 seq).

**Contabo `:5432`** = physical streaming replica of Hetzner — identical roles/DBs
(globals replicate), not independently writable.
**Contabo `:5434`** (crypto_signals primary, separate cluster): audit_reader,
clevious_audit_reader, clevious_writer, crypto_user, cs_admin, cs_reader, cs_writer,
findings_reader, orch_reader, orch_replicator, orch_writer, pgbackup, pionex_reader,
pionex_writer. DBs: crypto_signals (cs_admin), clevious_vps_log (clevious_writer),
vps_orchestrator (postgres).

## 2. One observation — NOT actioned (deliberately)

**`crypto_platform`** — a Hetzner `:5432` **login role with `CONNECT` + `public`
`USAGE` on `hermes_v2` but zero table grants** and no consumer confirmable this
session. Harmless (no data access) but it's an unused credential surface.
Per the plan, infra was not touched — logged here as a **candidate for review /
possible `DROP ROLE`** for a future session (verify no `crypto_data` / "crypto
platform" project still expects it first). Not severe enough to fire a Tier-1
finding/Telegram alert.

## 3. Verification

| Check | Result |
|---|---|
| Doc table vs. live `pg_roles` (login) | 18/18 match; `vps_orchestrator` listed as NOLOGIN |
| `systemctl is-system-running` | running |
| `systemctl --failed` | empty |
| `findings_log` open/in_progress | 0 |
| Replication (`pg_stat_replication`) | `streaming / async / 0` lag |
| Disk `/` | 54% |
| Infra changes this session | **none** (read-only SSH `psql` only) |
| `deploy_guardrail.sh` | not re-run — no code/infra changed; last green S19b |

## 4. Pendings — all external, carried forward unchanged from S19b

### JR Hermes VPS
- **Nothing open.** (P2 closed this session.)

### Handed to / owned by other projects
| # | Item | Owner | Status |
|---|---|---|---|
| X1 | Bulk-triage `vps_orchestrator_findings` for storm CRITICALs mirrored via `_mirror_to_gm_ladder` (2026-09-08→10), then close the S41 escalation | **GM** | OPEN |
| X3 | `/opt/hermes_v2` teardown + strip stale shadowed `FRED_API_KEY` in `/opt/hermes_v2/.env` | **JR Hermes Ingestor** (escalated S16) | OPEN |
| P3 | GM copy of the S19b reply notice (`JR_VPS_Orchestrators/docs/…s19b-to-ingestor-gm-deadlock-fixed.md`) is dropped, not committed | GM | OPEN |
| Y1 | Wire `parity_reader` into `contabo_tier1_watch.py` | Clevious VPS (S52) | OPEN |
| Y2 | Raise Contabo standby `max_wal_senders` 10→16 + `max_locks_per_transaction` 512→1024 + restart | Clevious VPS (S51 C1-B) | OPEN |
| Y3 | Cross-host TimescaleDB pkg divergence (2.29.2 Hetzner / 2.29.1 Contabo, different apt repos) — latent at next PG restart | GM (escalated S19) | OPEN |
| Y4 | Clevious S50 R5 detection-control naming — awaiting Clevious confirming the param-diff check is live | Clevious VPS | OPEN |

## 5. Interaction / numbering ground rule

`#Interaction NN` opener + hallucination-zone flagging observed throughout.
Session = S21 (disk-verified). Next = S22.
