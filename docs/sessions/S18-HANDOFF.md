# S18 Handoff — JR Hermes VPS

**Session type:** Close every remaining pending. Scope: *this project only + verify*
(no cross-project execution — user directive). Auto mode off (full SSH).
**Date:** 2026-09-06.
**Status:** 🟢 The one real defect found + fixed + live-verified. All owned paperwork filed.

---

## Quick resume for S19

**Nothing is open that blocks anything on this project.** Host `running`, 0 failed
units, replication `streaming/async/0`, disk ~53%, TLS 42 d, 5 timers on cadence.

**S18 found and fixed a defect the S17 "0 open findings" claim was masking:** the
Tier 4 escalation check wrote **3 INFO rows every 15-min cycle unconditionally**
(288/day) into `findings_log`, and because `insert_findings` never named
`action_status`, every one landed `'open'` (DB default). "0 open actionable
findings" had already drifted 86 → **111** and was climbing ~288/day. Fixed:
- `scripts/emission_state.py` (new) — the guardrail's debounce/state-change/hourly-
  roll-up gate, extracted and shared. Escalation check now passes
  `debounce_default=1` (a real WARNING/CRITICAL still emits on cycle 1; only
  steady-state INFO is throttled).
- `log_finding.py` — `initial_action_status()`: INFO enters `no_action_needed`,
  WARNING/CRITICAL enters `open`. `Finding.action_status` override field added.
- `deploy/sql/S18_findings_log_info_settle.sql` — **111 pre-fix open INFO rows
  settled** to `no_action_needed` (state update only; T-LOG.3 — no DELETE, no
  retention). Pre-dump at `/opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s18.dump`.
- `scripts/deploy_guardrail.sh` — 4 new assertions (offline test suite, escalation
  `--dry-run`, live bounded-emission double-start, `action_status`/`no INFO open`,
  T-LOG.3 retention guard).

**Live result:** emission dropped from 288 INFO/day → ~24/day (hourly roll-up +
genuine state changes). All rows now `no_action_needed` unless actionable.
**0 `open` rows of any severity** on the host now.

**First thing to check in S19:** `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT
action_status, severity, count(*) FROM findings_log GROUP BY 1,2 ORDER BY 1,2"` —
confirm `open` count is still 0 (or only genuine WARNING/CRITICAL), and
`SELECT date_trunc('hour',ts), count(*) FROM findings_log WHERE session_ref LIKE
'vps-escalation%' GROUP BY 1 ORDER BY 1 DESC LIMIT 8` — expect ≤ ~1 row/hour.

Open threads (all external / awaiting others):
- **GM** — reply filed closing S75 (three failed units) + S71 (health-check
  defects); both remediated S13/S17, confirmed live S18. Also still theirs from
  S16/S17: `/opt/hermes_v2` teardown, `hermes_v2` DB drop, `orphaned-s59` (Basic
  Crypto Signals), the `/self-report` ownership call + `ORCHESTRATOR_SELF_REPORT_TOKEN`
  issuance, the synthetic-row cleanup + T-LOG.3 adoption.
- **Clevious VPS** — S44 unattended-upgrades policy **decided** (accept upgrades,
  gate reboots; `HERMES_PLATFORM_STANDARD.md` R5 + `/opt` synced). Two small
  hardening asks handed to Clevious for Contabo (explicit `Automatic-Reboot false`,
  confirm S27 `needrestart` exclusions). S40 `:5434` readiness-gate reboot test
  **handed back** — needs a Contabo reboot, not ours to run.
- **Clevious VPS S50 R5 detection-control naming** — still "accepted S16", still
  awaiting Clevious confirming the primary↔standby param-diff check is live before
  R5 can name it. Untouched S18.

---

## 1. The defect — full detail

### What was wrong
S17 built the Tier 4 escalation check (`hermes_vps_escalation_check.py`, 15-min
timer) with a single `log_findings(findings, …)` call at the end. `findings` always
held 3 INFO lines in steady state:
`escalation: no unresolved CRITICAL findings` / `guardrail.heartbeat: fresh (…)` /
`reconcile: … orphan_telegram=0 orphan_db=0 delivery_failed=0`. No throttle — S17
§4's "INFO only on state change + hourly roll-up" rule was implemented in the
**guardrail** (`apply_debounce`) but never in the escalation check.

Compounding: `insert_findings()` (`log_finding.py`) never listed `action_status` in
its INSERT, so the column's `DEFAULT 'open'` (from `S17_findings_log_tier4.sql`)
applied to every row — INFO included. Nothing ever closes INFO.

Net: 288 `open` INFO rows/day into a hypertable that **T-LOG.3 forbids ever
pruning**. Table is still tiny (230 rows / 368 kB — the 500 MB tripwire is years
off), so this was **signal degradation, not storage**: "0 open actionable
findings" — the metric S17 used to certify host health — was on its way to
meaningless.

The daily digest is **not** affected — verified it reads `FINDINGS_DB_URL`
(`vps_orchestrator_findings`, the GM's DB), never `hermes_vps_log`.

### The fix — files
| File | Change |
|---|---|
| `scripts/emission_state.py` **(new, 131 ln)** | `load_state` / `save_state` / `finding_key` / `throttle` — extracted verbatim from the guardrail's private helpers, parameterized (`debounce`, `debounce_default`, `allclear_every_sec`, `allclear_summary`, `recovered_summary`). `debounce_default < 1` raises. Kept OUT of `log_finding.py` on purpose — the sink's invariant is "everything reaches both sinks"; a suppression rule inside it could one day drop a WARNING. |
| `scripts/audit/hermes_vps_guardrail.py` | Deleted the 4 private helpers; `apply_debounce` is now a 6-line shim over `throttle` with the guardrail's own `_DEBOUNCE`/`_DEBOUNCE_DEFAULT`. **Behaviour byte-identical** — all 5 `test_guardrail_debounce.py` cases pass unchanged. |
| `scripts/audit/hermes_vps_escalation_check.py` | Emission gate wired at the single `log_findings` choke point (`debounce_default=1`). `--dry-run` added (skips DB/Telegram/state/latch/GM-mirror). Sub-threshold summary re-keyed `escalation.subthreshold:` so it can't be read as a recovery of an active `escalation:` alert. `mark_escalated` + `_mirror_to_gm_ladder` guarded by `not dry_run`. |
| `scripts/log_finding.py` | `ACTION_STATUSES` const; `Finding.action_status: str|None` field + `__post_init__` validation; `initial_action_status(f)` (explicit override wins, else severity → `open`/`no_action_needed`); `insert_findings` writes the column. |
| `deploy/sql/S18_findings_log_info_settle.sql` **(new)** | Settle pre-fix open INFO rows. `\echo` step structure mirrors `S17_findings_log_tier4.sql`. Pre-flight checks no compressed chunks; UPDATE tags `detail` with `[S18 settle: …]` (rollback key); re-asserts 0 retention jobs. |
| `scripts/deploy_guardrail.sh` | Step 1 adds `emission_state.py`; step 1b runs the offline pytest suite (guarded on `import pytest`); step 2b escalation `--dry-run` with `FINDINGS_DB_URL` unset; step 6 live bounded-emission (2nd consecutive run must emit 0 rows); step 7 no INFO row is `open`; step 8 no retention job. |
| `tests/test_emission_state.py` **(new, 11 cases)** | threshold-1 never downgrades/suppresses a WARNING; steady-state INFO silent; reconcile varying-counts-same-key stays silent; recovery emits once; `debounce_default=0` raises; guardrail 2-cycle debounce still works through the shared fn; `initial_action_status` mapping + override + bad-value rejection. |

**Local:** 30/30 tests pass (was 19; +11).

### Deploy sequence executed
1. Branch `s18-emission-gate` → committed `2445449` → pushed → **ff-merged to `main`** → pushed.
2. Host `/opt/hermes-vps` `git pull --ff-only` → HEAD `2445449`.
3. **Staged smoke test** in `git worktree /tmp/s18-stage` off `origin/s18-emission-gate`:
   `py_compile` all 4 files ✓; `--dry-run` both scripts ✓ ("would emit 1 of 3"
   for escalation); **stateful 3-run test** with isolated `HERMES_VPS_STATE_DIR`
   + `FINDINGS_DB_URL` unset → run 1 emitted 1 row (`escalation: all 3 checks
   nominal`, `action_status=no_action_needed`), **runs 2 & 3 emitted 0**;
   threshold-1 safety property proven on host Python (steady → silent; escalation
   appears → warning emits cycle 1 unchanged; recovery → one "cleared").
4. Pre-migration `pg_dump -Fc` → `…/manual/hermes_vps_log_pre-s18.dump` (35 kB).
5. `sudo -u postgres psql -f deploy/sql/S18_findings_log_info_settle.sql` →
   **`UPDATE 111`**, verify steps all zero.
6. `bash scripts/deploy_guardrail.sh` → **ALL 8 ASSERTIONS PASS** (incl. step 6
   bounded-emission "2nd consecutive steady-state run emitted 0 rows", step 7
   "0 INFO rows are 'open'", step 8 "0 retention jobs").
7. Timers were already `enabled` since S17 → running timers now execute the S18
   code with no `systemctl enable` needed.
8. Worktree removed.

### Post-deploy live state (findings_log)
```
 action_status   | severity | count
------------------+----------+-------
 no_action_needed | critical |    17   (S17-era retro-closed)
 no_action_needed | info     |   211
 no_action_needed | warning  |     9   (S17-era retro-closed)
```
**0 `open` rows of any severity.** Emission before → 3/cycle × 96 = 288/day, all
`open`. After → ~1/hour, all `no_action_needed`.

---

## 2. Paperwork filed (Part 3 of the plan)

| Notice | File | Status |
|---|---|---|
| Clevious S44 — unattended-upgrades policy | `docs/CROSS-PROJECT-NOTICE-REPLY-2026-09-06-jr-hermes-vps-s18-to-clevious-s44-unattended-upgrades.md` | **DECIDED** — accept upgrades, gate reboots. `HERMES_PLATFORM_STANDARD.md` R5 new bullet; `/opt` copy synced (`.bak-s18` saved, md5 match). Mirrored to Clevious VPS, JR_VPS_Orchestrators/docs, JR Basic Crypto Signals/docs. |
| GM S75 (3 failed units) + S71 (health-check defects) | `docs/CROSS-PROJECT-NOTICE-REPLY-2026-09-06-jr-hermes-vps-s18-to-gm-s75-s71-closed.md` | **CLOSED** — all remediated S13/S17, confirmed live S18 (`systemctl show` all 3 = success/0; no active `hermes_v2` assertion in the health check). Mirrored to JR_VPS_Orchestrators/docs. |
| Clevious S40 (`:5434` readiness gates) | `docs/CROSS-PROJECT-NOTICE-REPLY-2026-09-06-jr-hermes-vps-s18-to-clevious-s40-5434-readiness-handback.md` | **HANDED BACK** — verification needs a Contabo reboot; not JR Hermes VPS's host. We fix the gate script if the test finds a bug. Mirrored to Clevious VPS, JR Basic Crypto Signals/docs. |

**Sibling-repo mirror copies are dropped but not committed in those repos** — left
for each project to pick up (matches how inbound notices reached us).

---

## 3. Verification gates — result

| Gate | Result |
|---|---|
| Local pytest | 30/30 (11 new) |
| Guardrail behaviour unchanged | 5/5 `test_guardrail_debounce.py` pass with zero edits |
| Staged smoke test (host worktree) | dry-run ✓; stateful 3-run: 1 / 0 / 0 rows ✓; safety property ✓ |
| `deploy_guardrail.sh` (8 steps) | all pass |
| SQL migration | `UPDATE 111`; open-INFO = 0; retention jobs = 0 |
| Live emission rate | 288/day → ~24/day |
| **23:45 UTC real timer fire** | **emitted 0 rows** (steady state, within-hour, roll-up spent) — live timer path confirmed |
| `open` rows on host | 0 (all severities) |
| `is-system-running` / failed units / replication | running / 0 / streaming-async-0 |
| No retention policy on `findings_log` (T-LOG.3) | 0 |

**23:45 UTC real timer fire (post-deploy): emitted 0 rows to `findings_log`** — the
running systemd timer executes the S18 code and the gate holds on the real path, not
just in `deploy_guardrail.sh`'s double-start.

**Cadence anomaly from S17 — investigated, benign, closed.** The escalation service
ran 22:17:29 then 22:22:36 on 2026-09-06 (~5 min, not 15). `journalctl _COMM=systemd`
shows a `systemctl daemon-reload` at 22:22:33 (an S17 unit edit) that re-armed the
timer and fired an immediate run. Cadence returned to 15–15.5 min immediately after.
One-off, not recurring. Nothing to fix.

---

## 4. NOT touched (still external, per scope)

`/opt/hermes_v2` teardown · `hermes_v2` DB drop · `orphaned-s59` · GM synthetic-row
cleanup + T-LOG.3 adoption · `/self-report` ownership + `ORCHESTRATOR_SELF_REPORT_TOKEN`
· R5 detection-control naming (awaiting Clevious) · Ingestor's `backup-pre-s*` dirs
+ sentiment grant fold-in.

---

## 5. Interaction / session-numbering ground rule — S18

`#Interaction NN` opener + hallucination-zone flagging observed throughout. No
mechanism change; the global `UserPromptSubmit` hook enforces it. Session = S18
for the whole conversation; next handoff = S19.
