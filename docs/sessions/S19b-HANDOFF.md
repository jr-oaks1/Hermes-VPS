# S19b Handoff — JR Hermes VPS

**Session type:** Incident response — break the Tier 3 ↔ Tier 4 guardrail/escalation
deadlock + ~40k-row alert storm flagged by JR Hermes Ingestor S40/S41 (escalated to GM).
**Date:** 2026-09-10. Auto mode toggled off for host work (DB bulk-write stayed
classifier-gated even so — user disabled twice).
**Numbering:** user-stated session = S19. `S19-HANDOFF.md` + `S20-HANDOFF.md` already
existed (both 2026-09-07) so per the user's call this handoff is **`S19b-HANDOFF.md`**;
branch / SQL / triage-stamp / notice all read **S19b**. Next handoff = **S21**
(S19b is a same-number continuation, not a new counter — but S20 is the last clean
integer on disk, so the next session should verify and most likely use S21).

**Status:** 🟢 RESOLVED. Deadlock fixed in code, storm settled, both units green,
`is-system-running` = running, **0 open/in_progress findings**.

---

## Quick resume for next session

Nothing open blocks this project. First checks:
- `systemctl --failed` empty; `systemctl is-system-running` = running.
- `bash /opt/hermes-vps/scripts/deploy_guardrail.sh` → all 9 steps green.
- `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT action_status,severity,count(*) FROM findings_log GROUP BY 1,2 ORDER BY 1,2"`
  → `open` count should be 0 (or only genuinely-actionable new findings).
- `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT date_trunc('hour',ts),count(*) FROM findings_log WHERE severity<>'info' AND ts>now()-interval '6h' GROUP BY 1 ORDER BY 1 DESC"`
  → steady state ≈ 0/hour.

**Open threads (see §6 for the full table):**
- **GM** (X1) — bulk-triage `vps_orchestrator_findings` for mirrored storm CRITICALs,
  then close the S41 escalation. Only external item still needing action.
- **JR Hermes VPS** (P2) — `VPS_CONNECTIVITY_REFERENCE.md` roles-table reconciliation
  (housekeeping, nothing broken).
- **Ingestor** (X3) — `/opt/hermes_v2` teardown + stale `FRED_API_KEY` (escalated S16).
- Concurrent **Ingestor S42** already closed X2 (`healthcheck.sh` exit-0-on-finding)
  and armed the heartbeat + restarted their prod service (was P1) — verified live.

---

## 1. Root cause (verified live this session)

**Seed:** 2026-09-08 00:00:12 UTC `hermes-healthcheck.service` (Ingestor's Tier-3
check, unit owned by this project) emitted `[CRITICAL] Tip-advance: raw_onchain …
172812s old` and **exited non-zero** → `failed` unit. *(raw_onchain has since
recovered; that unit has run `0/SUCCESS` every 10 min since ≥06:42 UTC 09-10.)*

**Self-sustaining loop** (00:04:41 onward — seed then irrelevant):
1. Tier 3 guardrail `check_failed_units()` saw a `failed` unit → `systemd: 1
   failed unit(s)` CRITICAL → `run()` returned **1 on any critical** → systemd
   marked `hermes-vps-guardrail.service` **`failed`**.
2. Next guardrail run saw *its own* unit failed → same CRITICAL → stayed failed.
3. Tier 4 escalation check saw the unresolved CRITICAL, escalated it (GM→CEO
   ladder), **wrote a new `findings_log` row** for the escalation, which is
   itself an unresolved CRITICAL → next run escalated *that* → nested
   `CEO ESCALATION … "CEO ESCALATION …"`. Exited 1 on CEO band → its unit
   `failed` too.
4. All ladder lines shared emission-gate key `escalation` and re-emitted **every
   row every 15-min cycle**.
5. Telegram rate-limited (429) → each failure spawned a `_self_report` CRITICAL
   → more ladder fuel.

**Freeze state:** 40,094 findings_log rows, 39,726 self-generated open W/C;
~16.3k Telegram delivery failures in the outbox journal.

## 2. The fix — code (branch `s19b-deadlock-fix` → `main`, deployed `/opt/hermes-vps`)

Commits `b1059ca`, `2bcd67c`, `7115f14`, `3b2b566`.

| # | Change | File |
|---|---|---|
| 1 | **Exit-code contract:** 0 = audit ran (findings or not), 2 = audit could not run. A CRITICAL finding is dual-written + heartbeat-recorded but does **not** fail the oneshot. | `hermes_vps_guardrail.py`, `hermes_vps_escalation_check.py` (docstrings + `run()` returns) |
| 2 | **Guardrail excludes its own 2 units** (`_OWN_UNITS`) from `systemctl --failed`. Only *other* failed units are CRITICAL; own ones noted in `detail`. Liveness backstop = T3.10 heartbeat-staleness check. | `hermes_vps_guardrail.check_failed_units()` |
| 3 | **Escalation emits once per band crossing** — `is_first_band_crossing(row, band)` gates on the row's own `escalated_gm_at`/`escalated_ceo_at`. Already-latched → one INFO roll-up (`escalation.notified: N GM + M CEO already latched`). | `hermes_vps_escalation_check.py` |
| 4 | Notification rows written `action_status='no_action_needed'` + `detail='[meta: derived Tier 4 …]'`. `open_critical()` also excludes `session_ref LIKE 'vps-escalation-%'` / `summary LIKE 'escalation:%'`. Double protection against self-escalation. | `log_finding.open_critical()`, escalation `run()` |
| 5 | `settled_without_triage()` + `deploy_guardrail.sh` step 7b accept `[meta:` as a valid disposition marker alongside `triage:` (`_TRIAGE_MARKERS`). | `log_finding.py`, `deploy_guardrail.sh` |
| 6 | **Telegram 429** — honour `retry_after` once (bounded 1–30s), then mark undelivered. | `log_finding.send_telegram()` |
| 7 | **reconcile** — `orphan_db` counts only `open`/`in_progress` rows (a dispositioned row is not an actionable orphan); `delivery_failed` recency-gated to 6h like `orphan_telegram`; selects `session_ref` so `_is_meta()` works; summary line names which window each count uses. | `hermes_vps_reconcile.py` |
| 8 | `deploy_guardrail.sh` **step 9** — units not `failed` after a normal run + own-unit-exclusion assertion (headerless fake, matching `--no-legend`). | `deploy_guardrail.sh` |

**Tests:** +13 (`test_guardrail_failed_units.py` ×5, `is_first_band_crossing` ×4,
`test_reconcile_recency.py` ×4). **51 pass.**

## 3. The fix — data / host ops

- **`deploy/sql/S19b_findings_log_storm_triage.sql`** — class-scoped
  (`escalation:%` / `systemd:%failed unit(s)%` / `reconcile:%` /
  `log_finding: dual-write incomplete%` / `guardrail:%`), `ts >= 2026-09-08`,
  `action_status='open'` → `no_action_needed`, each row individually stamped
  `[S19b triage: …]`. **`UPDATE 39726`.** T-LOG.3: state-update only, no DELETE,
  0 retention jobs. T-LOG.4: not age-blind — every class named + stamped.
  Pre-flight confirmed only 2 non-storm open rows (own smoke-test artifacts).
  Ran as runtime role `hermes_vps` (verified `has_table_privilege … UPDATE` = t;
  no `sudo -u postgres` needed for DML). Pre-dump:
  `/opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s19b.dump` (verified
  restorable). Rollback: `UPDATE … SET action_status='open' WHERE detail LIKE '%[S19b triage:%'`.
- **8 deploy/smoke-test artifact rows** (`timer.*inactive` while timers stopped;
  2 pre-fix reconcile CRITICALs) settled the same way (`UPDATE 8`).
  → **0 open/in_progress rows.**
- **Telegram outbox journal** — 16,270 storm-era lines (ts < 09:00 UTC 09-10)
  moved to `/var/lib/hermes-vps/telegram_outbox.jsonl.storm-s19b-archive`
  (out of `_read_outbox()`'s path — it reads `.jsonl` + `.jsonl.1` only). Old
  `.jsonl.1` → `.jsonl.1.pre-s19b`. Active journal: 6 recent lines. Record
  preserved, reconcile window clean now (not in 6h).
- **`hermes-healthcheck.service`** (S36/S37/S39 ask, ~3 days pending) — applied
  the S36 draft: `WorkingDirectory`, two `ExecStartPre=/usr/bin/test -d` guards,
  **`ReadWritePaths=/opt/hermes-ingestor/logs`**. Backup
  `/etc/systemd/system/hermes-healthcheck.service.bak-s19b`. `daemon-reload` +
  one `start` → `ExecMainStatus=0`, `logs/healthcheck.heartbeat` now written
  (was `[INFO] heartbeat write skipped` every cycle). Alarm still dormant
  (Ingestor owns `HEALTHCHECK_HEARTBEAT_ENABLED` in their `.env`) → no
  false-alarm risk.

## 4. Deploy sequence executed

1. Branch → 4 commits → ff-merge `main` → push.
2. Host: stopped `hermes-vps-{guardrail,escalation}.timer` FIRST (froze the storm).
3. Staged `git worktree /opt/hermes-vps-s19b`: `py_compile` all; stateful
   escalation 3-run (isolated `HERMES_VPS_STATE_DIR`, `FINDINGS_DB_URL` unset) →
   **run 1 emitted first-crossings, runs 2 & 3 emitted 0.** Guardrail 2-run →
   exit 0 both, heartbeat written, `systemd: no failed units`.
4. Pre-dump `hermes_vps_log`. `git pull` `/opt/hermes-vps` → `3b2b566`.
5. Ran S19b triage SQL (`UPDATE 39726`, all verify checks 0).
6. Archived storm outbox lines.
7. `deploy_guardrail.sh` → **all 9 assertions pass** (step 6 "2nd consecutive
   steady-state run emitted 0 rows").
8. `systemctl reset-failed` + `systemctl start` both timers (were still
   `enabled`). Settled the 8 artifact rows.
9. Watched 2 guardrail + 1–2 escalation cycles — see §5.

## 5. Live verification (2026-09-10 ~09:35–09:58 UTC)

| Check | Result |
|---|---|
| Guardrail timer cycles post-fix (09:34, 09:44, 09:50, 09:55) | all `Deactivated successfully`, `ExecMainStatus=0`, `NRestarts=0`; 09:34 wrote `guardrail: all 17 checks OK` + `timer.* recovered`, later cycles wrote **nothing** (throttled steady state) |
| Escalation timer cycle post-fix (09:49) | `Deactivated successfully`, `ExecMainStatus=0`, wrote **0 findings_log rows** |
| `systemctl --failed` | empty |
| `systemctl is-system-running` | **running** |
| `findings_log` open/in_progress | **0** |
| `findings_log` last write | 09:34:08 (`guardrail: all 17 checks OK`) — nothing since |
| Replication (`pg_stat_replication` as postgres) | `16/main streaming async 0` |
| Guardrail heartbeat | fresh (age 176 s at 09:58) |
| `escalation_state.json` | all 4 checks `info`, `fail_counters` all 0 |
| Disk `/` | 54% |
| Active telegram outbox | 15 lines (storm 16,270 archived) |
| Staged smoke test (host worktree, isolated state) | escalation run 1 emitted first-crossings, **runs 2 & 3 emitted 0**; guardrail exit 0 both runs, heartbeat written, `systemd: no failed units` |
| `deploy_guardrail.sh` | **all 9 assertions pass** |
| Local `pytest tests/` | **51 pass** |

Storm was self-generated end to end: `SELECT … WHERE severity='critical' AND
action_status IN ('open','in_progress') AND summary NOT LIKE 'escalation:%' AND
summary NOT LIKE 'systemd:%' …` → **0 rows** before the fix. No real finding was
masked or swept.

## 6. Pendings — full list (for seamless continuation)

> **A concurrent JR Hermes Ingestor session (S42) ran during/just after S19b** — it
> verified the fix live (their F7 → RESOLVED, `findings_log` #74 resolved), committed
> the reply notice into their repo (`69d0d2d`), **closed X2** (`healthcheck.sh` now
> exits 0 on a finding — `22c3dc8`/`c895c0d`) and **closed the P1 arming + prod
> restart** (`HEALTHCHECK_HEARTBEAT_ENABLED=true` in `/opt/hermes-ingestor/.env`;
> `hermes-ingestor.service` restarted clean 11:27 UTC 2026-09-10, `NRestarts=0`).
> Verified live from the host this session. Our two units stayed green throughout.

### Yours to direct (JR Hermes VPS)

| # | Item | Status / next step |
|---|---|---|
| ~~P1~~ | ~~`hermes-ingestor.service` hardening + heartbeat arm + prod restart~~ | **DONE** by Ingestor S42 (arm + restart). The optional `ExecStartPre=/usr/bin/test -d` dir guards on `hermes-ingestor.service` were **not** added — Ingestor (code owner) wired the heartbeat in-script on every path instead and considers S67 fault A covered. Nothing owed here. |
| P2 | **`VPS_CONNECTIVITY_REFERENCE.md` roles-table reconciliation** — table is missing `hermes_vps`, `audit_reader`, `hermes_ingestor`, `parity_reader`; predates several splits. | Deferred since S20. Housekeeping pass, any time, nothing broken. **Only open JR-Hermes-VPS-owned item.** |
| P3 | GM copy of the reply notice (`JR_VPS_Orchestrators/docs/…s19b-to-ingestor-gm-deadlock-fixed.md`) is dropped, not committed | Left for GM to pick up (concurrent-session safety — do not commit into the GM repo). Ingestor already committed theirs. |

### Handed to other projects (S19b reply notice: `docs/CROSS-PROJECT-NOTICE-REPLY-2026-09-10-s19b-to-ingestor-gm-deadlock-fixed.md`)

| # | Item | Owner | Status |
|---|---|---|---|
| X1 | Check / bulk-triage `vps_orchestrator_findings` for storm CRITICALs mirrored via `_mirror_to_gm_ladder` (2026-09-08→10), then **close the S41 escalation**. Mirror fired latch-gated per GM-band row (bounded to distinct escalated rows, not 40k). | **GM** | OPEN |
| ~~X2~~ | ~~`healthcheck.sh` exit 0 on a finding~~ | JR Hermes Ingestor | **DONE S42** (`22c3dc8`) — see `reference_monitoring_exit_code_contract.md` |
| X3 | `/opt/hermes_v2` teardown + strip the stale shadowed `FRED_API_KEY` in `/opt/hermes_v2/.env`. | **JR Hermes Ingestor** (escalated S16) | OPEN |

### Pre-existing, other projects *(from prior handoffs — not re-verified live S19b)*

| # | Item | Owner |
|---|---|---|
| Y1 | Wire `parity_reader` into `contabo_tier1_watch.py` | Clevious VPS (their S52) |
| Y2 | Raise Contabo standby `max_wal_senders` (10→16) + `max_locks_per_transaction` (512→1024) + restart — zero headroom vs primary | Clevious VPS (S51 C1-B) |
| Y3 | Cross-host TimescaleDB pkg divergence (2.29.2 Hetzner / 2.29.1 Contabo, different apt repos) — latent at next PG restart | GM (escalated S19) |
| Y4 | Clevious S50 R5 detection-control naming — awaiting Clevious confirming the param-diff check is live | Clevious VPS |

## 7. Interaction / numbering ground rule

`#Interaction NN` opener + hallucination-zone flagging observed throughout.
Session = S19 (user-stated); handoff = `S19b-HANDOFF.md` by user's explicit call
(S19 + S20 already on disk from 2026-09-07). Next session verifies disk before
numbering — expect **S21**.
