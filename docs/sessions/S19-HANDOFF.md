# S19 Handoff — JR Hermes VPS

**Session type:** Cross-project. Driven from **Clevious VPS S51** (that repo holds the
session of record: `Clevious VPS/sessions/S51-HANDOFF.md`); the Hetzner-side code work
was committed here as JR Hermes VPS S19. Auto mode was toggled off mid-session for the
one live DB write.
**Date:** 2026-09-07.
**Status:** 🟢 Three defects found by live read-only checks, all fixed + deployed +
live-verified. Host `running`, 0 failed units, replication `streaming/async/0`, disk 56%.

---

## Quick resume for S20

**Nothing open blocks this project.** `git -C /opt/hermes-vps log -1` = `d709773`.
`findings_log` 244 rows / 440 kB, **0 `open` rows** — and that is now a *true*
all-clear: every settled WARNING/CRITICAL row carries a human `[S51 triage: …]` stamp
attesting it was individually reviewed (not swept there by a bulk UPDATE).

**First checks in S20:**
- `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT count(*) FROM findings_log WHERE severity IN ('warning','critical') AND action_status='no_action_needed' AND (detail IS NULL OR position('triage:' in lower(detail))=0)"` → must be **0** (deploy_guardrail step 7b + the 15-min escalation check both assert this now).
- `bash /opt/hermes-vps/scripts/deploy_guardrail.sh` → all 9 steps green (exit 0).

---

## What S19 found and fixed

### 1. Tier 4 escalation queue was silently empty — HIGHEST

`deploy/sql/S17_findings_log_tier4.sql` lines 54-57 ran an **age-based, severity-blind**
`UPDATE findings_log SET action_status='no_action_needed' WHERE ts < now()-interval '7 days'
AND action_status='open'`, plus a second off-repo hand pass (S17-HANDOFF.md:94-100).
It retro-closed **17 CRITICAL + 9 WARNING** rows along with the INFO rows it meant to
settle. `log_finding.open_critical()` selects `action_status IN ('open','in_progress')`,
so the Tier 4 ladder had an empty input set and "0 open actionable findings" was a
**false all-clear that stood for two sessions (S17, S18)**.

- **`deploy/sql/S51_findings_log_severity_triage.sql`** — all 26 rows reviewed live
  against present host state (every one confirmed stale / false-positive / already
  resolved — evidence per group in the file; **zero genuine re-opens**), each stamped
  `[S51 triage: <reason>]`. State-update only, no DELETE (T-LOG.3). Pre-dump:
  `/opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s51.dump`. Applied 2026-09-07
  (`UPDATE 26`, verified 0 unstamped after).
- **`log_finding.settled_without_triage(db_url)`** — WARNING/CRITICAL rows in
  `no_action_needed` with no `triage:` note in `detail`.
- **`hermes_vps_escalation_check.queue_integrity_finding()`** — runtime half. Every
  15 min: WARNING if any, INFO otherwise. key prefix `queue-integrity` so the emission
  gate reads its recovery independently.
- **`deploy_guardrail.sh` step 7b** — deploy-time half.
- **`CONTINUOUS_IMPROVEMENT_STANDARD.md` Rule T-LOG.4** (workspace + `/opt`) — a bulk
  age-based settle is forbidden; settle by `severity='info'` or by enumerated ids only.

### 2. Executable-bit drift + guardrail coverage gaps

`log_finding.py`, `emission_state.py`, `hermes_vps_{guardrail,escalation_check,reconcile}.py`
were committed **0644** but ran 0755 on the host. `deploy_guardrail.sh` step 1 did
`chmod +x` **then** `test -x` — self-fulfilling, could never catch a 0644 clone → the
exact S67 `203/EXEC` silent-guardrail failure on any fresh clone.

- `git update-index --chmod=+x` on all 7 scripts + `deploy_guardrail.sh` (now 100755 committed).
- Step 1 now asserts the **committed** mode is 100755 (`git ls-files -s`) and fails
  otherwise; `hermes_vps_health_check.py` + `hermes_vps_daily_digest.py` added to the
  coverage loop (were unasserted for both exec bit and `py_compile`).
- `deploy_guardrail.sh` `REPO`/`PY` made env-overridable so a staged `git worktree`
  can actually be smoke-tested before the live `git pull` (the binding rule needed it).

### 3. `api.health` summary/severity mismatch

`hermes_vps_health_check.py`: when `/health` reports top-level `status="ok"` but an agent
is unhealthy, the row was recorded `summary="api.health: ok"` at `severity="critical"`,
real reason only in `detail` (live rows 108/127/133/146/152).

- `classify_api_health(status, agents)` extracted as a pure, unit-tested function. Summary
  now names the fault (`api.health: N agent(s) unhealthy (name=state, …)`); severity
  follows it. Live now: `info | api.health: ok (11 agents)`.

**Tests:** +9 (`tests/test_api_health_classify.py` ×6; `tests/test_escalation_check.py::TestQueueIntegrity` ×3). Full suite **39 pass**. *(The S19 commit message says "48 pass" — that was a miscount; the suite is 39.)*

**Commits:** `09f6765` (the three fixes), `d709773` (REPO/PY override). Both on
`origin/main`, deployed to `/opt/hermes-vps` by fast-forward `git pull` (mode-only local
changes on the deploy clone discarded first — content was identical).

---

## Housekeeping done (§4)

- **`/opt` standards sync** — was 3 of 6. Now all 6 identical to workspace
  (`md5sum` cross-checked): added `ORGANIZATIONAL_STRUCTURE.md`, `GLOBAL_GROUND_RULES.md`,
  `SESSION_NUMBERING_STANDARD.md`; refreshed `CONTINUOUS_IMPROVEMENT_STANDARD.md`
  (T-LOG.4) and `INTERACTION_NUMBERING_STANDARD.md` (Clevious S50 10th re-affirmation).
  `.bak-s51-*` backups left in `/opt`.
- **Backup registry** — `/etc/pg_backup.conf` still lists `hermes_v2` +
  `ALERT_ENV_HERMES_V2=/opt/hermes-ingestor/.env`. **Left as-is on purpose**: the
  `hermes_v2` DB still exists (~1.25 GB/dump) and the drop is JR Hermes Ingestor's under
  the S16 teardown escalation — pulling the registry line early would leave a live DB
  unbacked. Raised in the GM notice so the removal is coordinated with the DB drop.
  `hermes_vps_log` **is** correctly registered and backing up daily (verified) — that
  S16-era pending is closed.

---

## Cross-project (§5) — filed, awaiting GM

`JR_VPS_Orchestrators/docs/CROSS-PROJECT-NOTICE-2026-09-07-clevious-s51-cross-host-version-parity-ownership.md`
(committed `89bcf4a`, pushed). Asks **GM to own** a primary↔standby software-version
diff check (kernel / OS / `postgresql-16` / loaded TimescaleDB extension / shared agents)
and to add a version-parity clause to `HERMES_PLATFORM_STANDARD.md` §3 R5.

**Live inventory 2026-09-07 (the evidence in the notice):** kernel `6.8.0-139` both
sides ✅; OS 24.04 both ✅; **but** the two hosts track different apt repos for
`postgresql-16`/`timescaledb` (Hetzner PGDG `16.15-1.pgdg24.04+2` / TSDB pkg `2.29.2`;
Contabo Ubuntu archive `16.15-0ubuntu0.24.04.1` / TSDB pkg `2.29.1`). **Both clusters
currently *run* TimescaleDB `2.29.0`** (neither has restarted PG since its last
unattended upgrade) — so the running pair matches *today* but **diverges silently at the
next restart of either cluster**. This is why it needs a standing check, not a one-off.

Non-overlap stated explicitly in the notice: Clevious VPS S51 owns the *five-GUC
parameter* parity check (`contabo_tier1_watch.py`); GM takes *software version* parity.

---

## Not done / not this session

- **Version alignment itself** — the user chose "detect + standardise, change nothing".
  No upgrades, no reboots. Alignment happens once GM owns the check and R5 names it.
- **Clevious VPS S51's own two items** (GUC parity-diff check; standby headroom raise +
  restart) — those stay in that project; see `Clevious VPS/sessions/S51-HANDOFF.md`.
- The `hermes_v2` teardown / DB drop — JR Hermes Ingestor's, unchanged.

## Verification trail (all live, 2026-09-07)

- `deploy_guardrail.sh` from the staged worktree **and** from the live path: all 9 steps
  green, exit 0. Step 7b: "every settled WARNING/CRITICAL row carries a triage stamp".
- Real `systemctl start hermes-vps-{guardrail,escalation}.service`: both `0/SUCCESS`
  with the new code. `escalation --dry-run`: 4 findings, all INFO incl.
  `queue-integrity: all settled WARNING/CRITICAL rows carry a triage stamp`, exit 0.
- `check_api_health()` live → `info | api.health: ok (11 agents)`.
- Host: `is-system-running`=running, 0 failed units, replication `100.121.245.4 streaming
  async 0`, disk 56%, guardrail heartbeat fresh (`checks_run: 17`), 6 timers scheduled.
- T-LOG.1 note row logged to `findings_log` (session S51) + `@JRHermesVPSBot`.
