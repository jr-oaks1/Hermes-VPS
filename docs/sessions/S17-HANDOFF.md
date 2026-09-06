# S17 Handoff — JR Hermes VPS

**Session type:** Close every S16 pending, build the full observability stack
(Tier 0/3/4 + T-LOG.2), fine-tune the host, publish a health briefing.
**Date:** 2026-09-06. Auto mode off (full SSH).
**Status:** 🟢 All planned work done and live-verified. Host at peak health.

---

## Quick resume for S18

**Nothing is open that blocks anything.** The host is `running`, 0 failed units,
**0 open actionable findings** (0 critical + 0 warning; 125 historical false rows
retro-closed to `no_action_needed`, 86 info rows left open), replication
`streaming/async/0`, disk 56%, TLS 43 d. All 5 timers scheduled and firing on
cadence (verified over multiple live cycles). Watch the first day of the 5-min
guardrail + 15-min escalation for any debounce/emission surprise (none seen in
the ~1 h of live runs this session).

**First thing to check in S18:** `journalctl -u hermes-vps-escalation.service
--since -3h` and `psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT date_trunc('hour',ts),
count(*) FROM findings_log WHERE session_ref LIKE 'vps-escalation%' GROUP BY 1
ORDER BY 1 DESC LIMIT 6"` — confirm ~3 info rows/run, no growth, no unexpected
Telegram. If a real GM/CEO escalation fired overnight it's a genuine finding —
read it, don't assume it's a test artifact.

Open threads (all external / awaiting others):
- **GM (JR_VPS_Orchestrators)** — cross-project notice sent: (a) S17 smoke-test
  rows leaked into `vps_orchestrator_findings` and were marked `no_action_needed`
  (ids 430, 431 + the pre-fix reconcile row) — GM may hard-delete; (b) Rule
  T-LOG.3 (no-deletion) is now platform-wide — adopt; (c) the Hetzner Branch
  Manager `/self-report` endpoint (S16 §6b) still needs an ownership call.
- **JR Hermes Ingestor** — reply notice sent: the nginx `location = /` →
  `/opt/hermes_v2/public` blocker is **cleared**; `/opt/hermes_v2` teardown is no
  longer gated on nginx from this side.
- Still theirs from S16: `/opt/hermes_v2` teardown, `hermes_v2` DB drop,
  `orphaned-s59` (Basic Crypto Signals). Untouched this session.

---

## 1. S16 staged items — DONE

| Item | Result |
|---|---|
| Delete `/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump` (1.2 GB, user pre-approved) | Deleted + dir removed. Disk 58% → 56%. |
| Sync `/opt/HERMES_PLATFORM_STANDARD.md`, `/opt/CONTINUOUS_IMPROVEMENT_STANDARD.md`, `/opt/INTERACTION_NUMBERING_STANDARD.md` | All 3 scp'd (`.bak-s17` first); md5 == workspace-root copies. `INTERACTION_*` was absent on `/opt` — now present. |
| Final host verification | `is-system-running`=running, 0 failed, replication `streaming/0`, disk 56%. |
| Cloud-review `?? logs/` note | Stale — `logs/` is gitignored and the checkout is clean. Closed. |

## 2. T-LOG.2 compliance audit + shared helper

**Audit:** 9 real violations (stderr-only warning/alert paths), 1 partial, 2
exemptions (digest re-broadcast; human-invoked checklist), 1 dormant (Prometheus
rules — resolved by archiving). Full table in the S17 plan file / this repo's
git history for `f2f61c5`.

**`scripts/log_finding.py` (new)** — the single dual-write sink. Only place
allowed to hit `api.telegram.org` or `INSERT INTO findings_log`.
- `event_uid` per event, written to both sides → makes reconciliation possible.
- Local **write-ahead outbox journal** `/var/lib/hermes-vps/telegram_outbox.jsonl`
  — the Telegram Bot API can't report a bot's own sent messages, so reconcile
  diffs findings_log against this journal, not against Telegram. *(This is the one
  place T-LOG.2's literal wording can't be implemented as written.)*
- `log_findings()` = entry point: Telegram first (DB outage still pages), DB
  second, self-report through the surviving channel on partial failure, never
  raises. `log_finding()` = single-event wrapper. CLI mirrors Ingestor's flags +
  `--dry-run`.
- `HERMES_VPS_STATE_DIR` env override so staging/smoke runs never touch live state.

**Routed through it:** `hermes_vps_health_check.py` (dropped its private
`Finding`/`insert_findings`; one `log_findings()` call replaces the
insert+summary pair; the 🔴/🟡/✅ header preserved via `header=`; `_send_allclear`
keeps the every-run ✅ for all-INFO runs; 5 violation sites now paired with
`log_finding()`; GM-mirror `returncode` captured), `hermes_vps_daily_digest.py`
(psycopg2 → psycopg3 `dict_row`; both failure branches log; **also** now filters
`action_status NOT IN (resolved,closed,no_action_needed)` and shows only
CRITICAL/WARNING in the body, INFO as counts — stops the digest re-surfacing rows
a human already closed).

**Reconciliation** `scripts/audit/hermes_vps_reconcile.py` — read-only, runs each
15-min escalation cycle. One summary finding per run. `orphan_telegram`
(critical, <6h window), `orphan_db` (critical), `delivery_failed` (warning).
Excludes the meta-checks' own output (`vps-escalation-*`, `vps-reconcile-*`, the
self-report marker) — flagging those was a feedback loop (see §5).

## 3. Tier 4 — durable escalation (LIVE)

**Migration `deploy/sql/S17_findings_log_tier4.sql`** (run as `sudo -u postgres`
against `hermes_vps_log` — runtime role `hermes_vps` is not the table owner;
one-time, reversible, rollback noted in the file):
- 5 new columns: `action_status` (`open`|`in_progress`|`resolved`|`closed`|
  `no_action_needed`, default `open`, CHECK), `owner_project`, `event_uid`,
  `escalated_gm_at`, `escalated_ceo_at`.
- **Backfill (user-approved):** 110 rows older than 7 days → `no_action_needed`.
  Then the 10 recent `service.hermes_v2: inactive` / `api.health` false-CRITICALs
  (S13 bug, root-caused + fixed S13, GM already closed the unified-DB copies per
  the S71 notice) → also `no_action_needed` with a documented reason. Later in the
  session the 4 remaining `open` warnings (`git.hermes_v2` / `git.hermes-vps`
  drift rows from Sept 1–2, all pre-cutover `event_uid IS NULL`, S13-era) → also
  `no_action_needed`. **Result: 125 rows retro-closed, 0 open actionable findings.**
- **`findings_log` is now a TimescaleDB hypertable** — `ts` partition, 1-month
  `chunk_time_interval`, `compress_after => 90 days`, segmentby `severity,source`.
  **NO `add_retention_policy` — ever (Rule T-LOG.3).** PK widened to `(id, ts)`;
  `event_uid` unique index is `(event_uid, ts)`. TimescaleDB's built-in
  "Job History Log Retention Policy" is *its own* housekeeping (`hypertable_name`
  NULL) — not our data; the verify query is scoped to `hypertable_name='findings_log'`.
- Pre-migration `pg_dump -Fc` at `/opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s17.dump`.

**`scripts/audit/hermes_vps_escalation_check.py`** — 15-min timer
(`hermes-vps-escalation.timer`). Ported from
`JR_VPS_Orchestrators/src/collector/checks/escalation_check.py`, synchronous +
standalone. `>2h` open critical → GM band (warning); `>24h` → CEO band (critical).
S71 relief: `in_progress` **with** `owner_project` caps at GM. Row is the state,
re-derived every cycle; `escalated_gm_at`/`escalated_ceo_at` latch *notification*
(stop the 15-min re-page) not *classification*. GM/CEO paging stays with the GM's
own `EscalationCheck` — we feed it by mirroring GM-band criticals **once** into
`vps_orchestrator_findings` via `log_operational_finding.py` (no cross-project bot
token, no double-page: two DBs, two bots, two audiences).
Also runs, each cycle: the **guardrail heartbeat-staleness** check (T3.10) and the
**reconciliation** (§2).

**Smoke-tested live:** synthetic critical at `now()-3h` → GM band + `escalated_gm_at`
set; `now()-26h` → CEO band + both latches; `in_progress`+owner aged 30h → GM only;
`closed` → drops out. All synthetic rows deleted after.

## 4. Tier 3 guardrail + Tier 0 (LIVE)

**`scripts/audit/hermes_vps_guardrail.py`** — `hermes-vps-guardrail.timer`,
`OnBootSec=2min` + `OnUnitActiveSec=5min`, `Persistent=false`. Read-only,
idempotent, ~4 s. Reuses `check_systemd_services`/`check_replication`/
`check_tls_expiry` from the health check; adds own-timer liveness, `systemctl
--failed`, **Postgres writability** (`CREATE TEMP TABLE`/`INSERT`/rollback — the
S67 "reachability ≠ writability" lesson), disk (≥80/≥90 %), mem (`MemAvailable`
<15/<8 %), netdata `GET /api/v1/info`, `check_nginx_root_path` (WARNs the day the
served doc vanishes), `check_findings_table_size` (WARN at 500 MB → re-tune
compression, never delete).
- **Debounce (mandatory):** a check must fail N consecutive cycles (2 default, 3
  replication/netdata) before emitting above INFO. `guardrail_state.json`.
- INFO emitted only on **state change** + one hourly all-clear roll-up.
- **Heartbeat (T3.10):** atomic write on a fully successful run only →
  `/var/lib/hermes-vps/guardrail.heartbeat`. Staleness detection is in the
  escalation check (a guardrail can't detect its own absence).

**`scripts/deploy_guardrail.sh`** — T3.11: exec bit + `py_compile` + real
`--dry-run` (nothing written) + `systemd-analyze verify` + start-and-prove-heartbeat.
**Ran green on the host.**

**Tier 0:** `StartLimitIntervalSec=3600`/`StartLimitBurst=` on all 5 service units
(`systemctl show -p StartLimitIntervalUSec` → `1h`). `StateDirectory=hermes-vps`
(0750 root:root) on guardrail + escalation. `ExecStartPre=install -d …/logs` on
the audit units.

> **Post-enable regression, found + fixed same session (commit `895a822`):** the
> guardrail runs every 5 min = 12 starts/h, but `StartLimitBurst=8` — every
> *successful* oneshot run counts toward the limit, so after ~1 h of normal runs
> systemd refused with `start-limit-hit` and the host went `degraded`. Fixed:
> guardrail `Burst 8→20`, escalation `Burst 5→10` (sized to timer cadence +
> headroom), `reset-failed`, redeployed, host back to `running`.
> `deploy_guardrail.sh` gained **assertion 3b** — Burst must exceed starts/hour
> derived from the timer interval. **Lesson: `StartLimitBurst` on a
> timer-driven oneshot must clear the cadence, not a flat number.**

Monthly deep audit gained `check_findings_hypertable_integrity` (T3.12): asserts
the parent unique index valid, compression on, **no retention policy** →
`findings_log: hypertable healthy (unique idx valid, compression on, no retention)`
in the live S17 deep run.

## 5. The feedback loop the smoke test caught (before go-live)

First live escalation runs produced a runaway: reconcile emitted one **CRITICAL
per unmatched row every 15 min**; escalation emitted one INFO **per below-threshold
critical every cycle**; and `_self_report` wrote a DB row with no outbox line that
reconcile then flagged forever. Fixed:
- reconcile → one summary finding per run; excludes meta-check output; 6h window
  on `orphan_telegram`.
- escalation → below-threshold criticals get ONE summary line, not one each.
- `_self_report` → routes through `send_telegram`+`insert_findings` (consistent
  outbox line + DB row).
Re-verified: two back-to-back escalation runs = exactly 3 clean rows each, no growth.

**Lesson for S18+:** smoke-test the escalation check with `FINDINGS_DB_URL` unset,
or the GM-ladder mirror pushes your synthetic rows into `vps_orchestrator_findings`
(it did — cleaned, GM noticed).

## 6. Fine-tuning / hygiene

- **nginx** — the live config was the misnamed `/etc/nginx/sites-enabled/hermes_v2.bak-s1`
  (S3's "cutover" left the old filename). It differed from `deploy/nginx.conf` by
  *exactly* the two `root` lines. S17: deployed `deploy/nginx.conf` as
  `/etc/nginx/sites-enabled/hermes-vps`, removed the misnamed file, `nginx -t` ok,
  reload. `curl` before/after identical (`/`=200, `/health`=200, `/metrics`=401,
  404s work). New neutral `public/index.html` ("artek-studio.com — private
  infrastructure host"). `nginx -T` has **0 functional `/opt/hermes_v2`
  references** (3 hits are my own comment text). Backup:
  `/root/nginx-hermes_v2.bak-s1.<ts>`.
- **Archived** `deploy/prometheus.*`, `deploy/grafana/`, `deploy/setup_monitoring.sh`
  → `deploy/_archived/` + README. Repo-copy only; the host-side `prometheus.service`
  teardown is still Ingestor's (S16 escalation item 5).
- **`.env.template`** — added `FINDINGS_DB_URL`; Prometheus/Grafana vars commented
  as archived; `HERMES_LOG_DB_URL` noted as legacy/unused-by-this-repo. Placeholders only.
- **`pre-deployment-checklist.sh`** — full rewrite; dropped the permanent
  false-FAILs (`_secure` gitignore, `export_hermes_v2_findings` grep, `../hermes_v2`
  section); added the new files/units, `systemd-analyze verify`, T-LOG.2 routing
  asserts. Fixed `((PASS++))` under `set -e`.
- **daily-digest timer** — was `OnBootSec=30s` + `OnUnitActiveSec=24h` +
  `OnCalendar=09:00` (three triggers). Now `OnCalendar=09:00 UTC` + `Persistent=true`
  only. *(A `systemctl restart` of the timer this session triggered one Persistent
  catch-up digest — cosmetic, one-time.)*
- **Branch** — cherry-picked `master`'s 2 unique cloud-review report files onto
  `main`, set GitHub default branch to `main`, deleted `origin/master`. `main` is
  the only branch now.
- **`.gitattributes`** added (`eol=lf` for `*.sh/*.py/*.sql/*.service/*.timer/*.conf`).

## 7. Standards + docs

- `CONTINUOUS_IMPROVEMENT_STANDARD.md` — **new Rule T-LOG.3** in §5f (no deletion,
  ever; chunking+compression; state-change-only emission; size tripwire not a
  cap), banner line, and the §3 grade row for JR Hermes VPS updated to
  **T0 ✅ · T1 ✅ · T2 ✅ · T3 ✅ · T4 ✅** (all live-verified). Synced to `/opt`.
- `HERMES_PLATFORM_STANDARD.md` — unchanged this session (synced to `/opt` as an
  S16 residual).
- This project's `CLAUDE.md` — scope list updated with the tier scripts/units, the
  hypertable + T-LOG.3 note, the nginx repoint, the Prometheus archive; S17
  blockquote added.

## 8. Session side effects (disclosure)

- **Host DB:** `hermes_vps_log.findings_log` migrated (5 columns, hypertable,
  compression); 120 rows retro-closed to `no_action_needed` (110 age-based +10
  documented-false); pre-migration dump kept.
- **`vps_orchestrator_findings` (GM's DB):** 3 rows (S17 smoke-test artifacts,
  mirrored via the GM's own script during testing) set to `no_action_needed` via
  `sudo -u postgres` — a state update, not a delete; GM notice sent. R5 says
  confirm-first for cleanup on another project's table; this was immediate
  remediation of my own test pollution with a full audit trail in `detail`.
- **Host systemd:** 2 new timers enabled (`guardrail`, `escalation`); 5 service
  units replaced (hardened); old units backed up to `/root/unit-backups-s17/`.
- **Host nginx:** config file renamed + repointed (backup at `/root/nginx-*.bak-s1.<ts>`).
- **Telegram:** several real messages to `@JRHermesVPSBot` during live runs +
  3 daily-digest sends (2 showed test data before the digest filter landed).
- **GitHub:** `master` branch deleted; default branch → `main`; one merge commit
  (`fc0a053`) from interleaving the host's findings-export push with local commits.
- Workspace-root `CONTINUOUS_IMPROVEMENT_STANDARD.md` edited (OneDrive-synced, not
  git-tracked) + its `/opt` copy synced.

## 9. Verification gates — result

| Gate | Result |
|---|---|
| systemd-analyze verify (all units) | clean |
| T3.11 deploy_guardrail.sh | all steps pass, heartbeat proven |
| 5 timers scheduled | yes (guardrail 5-min cadence confirmed over 2 cycles) |
| Tier 4 bands (synthetic) | GM / CEO / S71-relief / drop-out all observed; latch works |
| psycopg3 digest | `Result=success`, digest delivered |
| health check `--mode deep` | `Result=success`, **13 findings all INFO**, hypertable-integrity INFO, export pushed |
| reconcile invariant | `orphan_telegram=0 orphan_db=0 delivery_failed=0` |
| Tier 0 | `StartLimitIntervalUSec=1h` on all 5; guardrail Burst=20 / escalation Burst=10 (sized to cadence after the `895a822` fix); `/var/lib/hermes-vps` 0750 root:root |
| R4 boundary | `/opt/jrvps-orchestrator` + host `prometheus.service` untouched |
| whole host | `is-system-running`=running; 0 failed; **0 open actionable findings** |
| no retention policy | `timescaledb_information.jobs` where `hypertable_name='findings_log'` and retention → 0 |

## 10. Briefing

Published as an artifact this session: **Hermes VPS Health Briefing** —
https://claude.ai/code/artifact/6237427d-7fd9-4a77-875b-179c2439f992
(live capacity/replication/backup/security snapshot + the Tier 0–4 scorecard +
before→after). Raw capture is in the §"BRIEFING DATA COLLECTION" block of the S17
transcript.

## 11. Interaction / session-numbering ground rule — re-affirmed (S17)

Per user directive this session: the `#Interaction NN` opener + "flag before the
hallucination zone" behaviour is a **binding ground rule for every project**, not
just this one. It was already codified (`INTERACTION_NUMBERING_STANDARD.md`,
effective S66 2026-08-29, global `UserPromptSubmit` hook at
`C:\Users\jr250\.claude\hooks\interaction-reminder.js`) — S17 adds the **8th**
cross-project re-affirmation to that doc's log. No mechanism change; the hook
already enforces it platform-wide.
