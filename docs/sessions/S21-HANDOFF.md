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

## 4b. Deep forensic audit (2026-09-10, read-only sweep of the Hetzner host)

Host is genuinely healthy — **no CRITICAL or HIGH findings.** S19b deadlock fix
verified holding: **0 unit failures since 10:00 UTC**, guardrail + escalation
cycles all clean, `deploy_guardrail.sh` all 9 assertions pass, steady-state
emission ~1 row/hr. `is-system-running`=running, 0 failed units, replication
`streaming/async/0`, `contabo_replica` slot reserved+active, `findings_log`
0 open/in_progress (40,113 rows total — 39,772 `no_action_needed` W/C are S19b
storm residue, no-retention by design per T-LOG.3, stable/not growing). Backups:
`pg_backup.service` 02:31 today exit 0, all 4 configured DBs OK + off-site synced
to Contabo, 7-dump retention enforced. netdata 102 alarms all CLEAR. TLS
`artek-studio.com` → Oct 19, certbot renewed 08:14 today. UFW active, fail2ban
0 banned, 3 auth failures/24h. Tailscale key-expiry disabled both nodes, Docker
masked, NTP synced. unattended-upgrades on, `Automatic-Reboot=false` (matches
Clevious S44 R5).

### MEDIUM
| # | Finding | Owner |
|---|---|---|
| A1 | **`hermes_ingestor_log` DB has zero backup coverage** — not in `/etc/pg_backup.conf` `DATABASES=`, no `/opt/backups/` dir. It is JR Hermes Ingestor's permanent continuous-improvement findings record. The backup job config is JR-Hermes-VPS-owned; the DB is Ingestor's. → cross-project notice to Ingestor to register it (one line in `/etc/pg_backup.conf` + a smoke-tested run). | JR Hermes VPS + Ingestor |
| A2 | **`:5435` orch cluster `vps_orchestrator` DB (~950 MB) is dumped to only a ~30 MB file** (`/opt/backups/vps_orchestrator/…_013016.dump`, 01:30 daily) by a mechanism **outside** `/etc/pg_backup.conf`. Could be legit compression, could be schema-only/partial. Coverage unverified. | GM |

### LOW
| # | Finding |
|---|---|
| B1 | **X3 still open** (known, Ingestor-escalated S16): 5 timers still fire from `/opt/hermes_v2` (`walk_forward_monitor`, `bronze-audit-daily/weekly`, `funnel_scoring`, `server_health_audit`) + `hermes_v2.service` (disabled) + dead `prometheus.service` unit file. `/opt/hermes_v2` = 1.8 GB. |
| B2 | `/opt` housekeeping ~7 GB: `/opt/hermes-ingestor.backup-pre-s{25,27,27b,28}` + `-pre-s{14,16}-*` ≈ 4.4 GB (Ingestor, known S16); `/opt/backups/hermes_v2/manual` 2.4 GB stale manual dumps (Sep 2, no retention); `/opt/archives` 552 MB. Disk 54% — no pressure. |
| B3 | `sshd` binds `0.0.0.0:22` (+ `:52222`) though design intends port 22 Tailscale-only; only UFW's eth0 default-deny protects `:22`, with `permitrootlogin without-password`. Consider `ListenAddress 100.97.62.7` + loopback. Defense-in-depth only. |
| B4 | Old kernel `linux-image-6.8.0-137` retained alongside running `-139`. |
| B5 | Stale 4-day-idle root SSH session from `jrminipc` (`100.113.177.23`, user's own box, `root@notty` — likely a leftover ControlMaster/port-forward). |
| B6 | `telegram_outbox.jsonl.1.pre-s19b` (5.4 MB) + `.storm-s19b-archive` (8 MB) kept uncompressed in `/var/lib/hermes-vps/` (deliberate S19b record; gzip candidate). |
| B7 | = **Y3** (GM, escalated S19): TimescaleDB runtime 2.29.0 vs installed pkg 2.29.2; 2 apt packages held back — latent divergence at next PG restart. |
| B8 | `crypto_platform` login role — `CONNECT` + `public` `USAGE` on `hermes_v2`, **zero table grants**, no active connections. Candidate `DROP ROLE` after confirming no `crypto_data`-style consumer. |

**Actioned this session:** `/opt/hermes-vps` deploy clone fast-forwarded to
`b026634` (was 1 commit behind — S21 doc commits only, no service impact).
Nothing else changed — all MEDIUM/LOW items are either cross-project or need the
staged-smoke-test path.

## 5. Interaction / numbering ground rule

`#Interaction NN` opener + hallucination-zone flagging observed throughout.
Session = S21 (disk-verified). Next = S22.
