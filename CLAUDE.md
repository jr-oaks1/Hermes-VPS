# JR Hermes VPS — Project Guide for Claude

## Project Goal

Owns everything about the **Hetzner host itself** (`hermes`, `46.225.14.26` /
`100.97.62.7` Tailscale) as a piece of physical infrastructure — independent of
whatever application happens to be deployed on it. Split out of `hermes_v2` in
session **S1** (2026-08-22), because the VPS-level health-check/monitoring
tooling had been built directly inside the app's repo (S178/S179) simply because
this project didn't exist yet.

**Scope — what lives here:**
- Host-level recurring health checks (`scripts/audit/hermes_vps_health_check.py`,
  weekly quick / monthly deep, writes to `hermes_vps_log.findings_log`)
- **Observability tiers (S17, 2026-09-06) — all live on the Hetzner host:**
  - **Tier 3 guardrail** `scripts/audit/hermes_vps_guardrail.py` — read-only,
    boot + every 5 min (`hermes-vps-guardrail.timer`), N=2 debounce, success
    heartbeat at `/var/lib/hermes-vps/guardrail.heartbeat` (Rule T3.10)
  - **Tier 4 escalation** `scripts/audit/hermes_vps_escalation_check.py` — every
    15 min (`hermes-vps-escalation.timer`); durable ladder over
    `hermes_vps_log.findings_log` (`action_status` + `escalated_gm_at`/
    `escalated_ceo_at`), row-is-the-state; also runs the heartbeat-staleness
    check and the T-LOG.2 reconciliation each cycle. **S18: shares the
    guardrail's emission gate (`scripts/emission_state.py`, `debounce_default=1`) —
    steady-state INFO is throttled to state-change + one hourly roll-up; a real
    WARNING/CRITICAL still emits on its first cycle. `--dry-run` added.**
  - **`scripts/emission_state.py` (S18)** — shared `throttle()` used by both the
    guardrail and the escalation check: N-cycle debounce + INFO-only-on-state-change
    + one hourly all-clear. Deliberately NOT inside `log_finding.py` (the sink must
    never suppress).
  - **`scripts/log_finding.py`** — the ONLY place allowed to call Telegram or
    `INSERT INTO findings_log`. CLI (ad-hoc T-LOG.1 findings) + importable. Every
    warning/alert path routes through it (T-LOG.2). **S18: `initial_action_status()`
    — INFO enters `no_action_needed`, WARNING/CRITICAL enters `open`, so "open"
    means actionable (was: everything took the DB default `open`).**
  - `scripts/deploy_guardrail.sh` — the T3.11 deployment assertion; run it on the
    host after any guardrail/escalation change before enabling the timers.
- 🔴 **`hermes_vps_log.findings_log` is a TimescaleDB hypertable (S17)** — 1-month
  chunks, compression after 90 days, **NO retention policy, ever** (Rule T-LOG.3 —
  it is the permanent continuous-improvement record; bound cost with compression,
  never DELETE). One-time migration: `deploy/sql/S17_findings_log_tier4.sql`.
  Runtime role `hermes_vps` is not the table owner — schema changes need
  `sudo -u postgres`.
- systemd units for those checks (`deploy/hermes-vps-healthcheck-weekly.*`,
  `deploy/hermes-vps-audit-monthly.*`, `deploy/hermes-vps-daily-digest.*`,
  `deploy/hermes-vps-guardrail.*`, `deploy/hermes-vps-escalation.*` — all 5
  service units carry `StartLimitIntervalSec=`/`Burst=` per Tier 0 rule T0.2)
- nginx (`deploy/nginx.conf` — the single host-wide config, deployed to
  `/etc/nginx/sites-enabled/hermes-vps`; still contains the crypto-signals
  dashboard proxy inline, since nginx only runs once per host. S17: `location = /`
  root repointed `/opt/hermes_v2/public` → `/opt/hermes-vps/public/index.html`
  (a neutral holding page in `public/`) — this cleared the last nginx blocker on
  the `/opt/hermes_v2` teardown)
- Host metrics monitoring. **Current reality (verified S13, re-confirmed S17): the
  live stack is `netdata`** (systemd `netdata`, active, local API on
  `127.0.0.1:19999`). **Prometheus is installed-but-disabled+inactive and
  Grafana is not installed at all** — the in-repo Prometheus/Grafana files were
  **archived to `deploy/_archived/` in S17** (their alert thresholds moved into
  the Tier 3 guardrail). Not live config.
- UFW firewall snapshots (`deploy/firewall/`)
- The Hermes VPS Telegram bot (`@JRHermesVPSBot` / `Clevious_Hermes_Bot`,
  credentials in `/root/.hermes_vps/.env`) and its infra-level alert routing
  (CPU/mem/disk/SSL/replication, `service.started`)

**What does NOT live here:** the actual applications running on the host.
`hermes_v2` is decommissioned (`hermes_v2.service` stopped/disabled since
Ingestor's S8, 2026-08-26); its ingestion role now belongs to **`JR Hermes
Ingestor`** — a fully separate repo
(`https://github.com/jr-oaks1/JR-Hermes-Ingestor`), its own systemd service
(`hermes-ingestor.service`, port 8003, Hetzner), its own database role
(`hermes_ingestor`) and its own findings DB (`hermes_ingestor_log`) — corrected
here S11 (2026-09-05), stale since S09. This project's health check no longer
cross-reads `/opt/hermes_v2/.env` — that credential (`HERMES_LOG_DB_URL`
equivalent) now lives in Ingestor's own `/opt/hermes-ingestor/.env`.
**Verified clean S15 (2026-09-06):** `scripts/audit/hermes_vps_health_check.py`
has no `/opt/hermes_v2/.env` path — the secondary `EnvironmentFile` was dropped
S13 and the script reads only `/root/.hermes_vps/.env` (it does still read the
`hermes_v2` DB via `DATABASE_URL` for replication/freshness checks — intentional).

Read **[../HERMES_PLATFORM_STANDARD.md](../HERMES_PLATFORM_STANDARD.md)** before
any infrastructure change — this project *is* Hermes-platform infra. Also read
**[docs/VPS_CONNECTIVITY_REFERENCE.md](docs/VPS_CONNECTIVITY_REFERENCE.md)**
(canonical copy of the two-node Hetzner/Contabo reference, moved here from
`hermes_v2` in the same split — this project is now the natural project-level
home for it, alongside the workspace-root copy).

## Server

**Host:** `hermes`, Hetzner. Public IP `46.225.14.26` (web/DNS only). SSH via
Tailscale: `root@100.97.62.7`, key `~/.ssh/hermes_ed25519`. Public SSH fallback:
`root@46.225.14.26:52222`. Full detail in `docs/VPS_CONNECTIVITY_REFERENCE.md`.

**Live install path:** `/opt/hermes-vps` (this repo, deployed). Own credential
file: `/root/.hermes_vps/.env` — self-contained per `HERMES_PLATFORM_STANDARD.md`,
does not reuse `hermes_v2`'s `.env` except for the one cross-read noted above.

## Session numbering

This is a brand-new project as of 2026-08-22 — sessions start at **S1**, tracked
independently from `hermes_v2`'s own numbering (currently past S180). See the
cross-project session-numbering discipline in the workspace-root `CLAUDE.md` —
same rule applies here: verify against `docs/sessions/` on disk before writing
any handoff filename, never assume the next number.

## Session history

Handoffs live at `docs/sessions/S{N}-HANDOFF.md`, one file per session, most
recent linked here once it exists.

---
> ## 🟢 S1 — Project genesis (2026-08-22)
> Created by splitting VPS-infra files out of `hermes_v2`. See
> `docs/sessions/S1-HANDOFF.md` for what moved, what changed, and current live
> state.

> ## 🟢 S2 — GitHub remote + cloud-review docs (2026-08-22)
> Created GitHub repo, added cloud-review setup documentation, scaffolding complete. See
> `docs/sessions/S2-HANDOFF.md`.

> ## 🟢 S3 — Server deployment complete (2026-08-22)
> Deployed all 11 steps to Hetzner: cloned repo, systemd units, health-check tested, nginx cutover. Both projects verified healthy.
> See `docs/sessions/S3-HANDOFF.md`.

> ## 🟢 S4 — Git SSH + RemoteTrigger cloud-review (2026-08-22)
> Fixed git SSH credentials (HTTPS → SSH), verified findings export pipeline, created two cloud-review routines (weekly + monthly). All automated reviews scheduled. See
> `docs/sessions/S4-HANDOFF.md`.

> ## 🟢 S05 — Operational framework design + unified findings DB deployment (2026-08-22)
> Two phases: (1) Designed three-tier operations structure coordinated with Clevious VPS; created 5 workspace-wide docs (roles, audit schedule, Telegram routing, continuous-improvement, SQL templates). (2) Deployed vps_orchestrator_findings DB on Hetzner, dual-write logging, log_operational_finding.py script. End-to-end verified: 7 findings logged to both DBs; systemd timers active (weekly Sun 04:00, monthly 1st 04:15 UTC). Ready for Sept 1 synthesis meeting. See `docs/sessions/S05-HANDOFF.md` and `docs/sessions/S5-HANDOFF.md` (framework design phase).

> ## 🟢 S06 — Daily digest automation deployed (2026-08-22)
> Resolved all S05 pendings: daily digest script built + deployed + tested to @JRHermesVPSBot (09:00 UTC daily). Git push issue already resolved. Three-tier operational reporting now complete (weekly audit + monthly deep + daily digest). All automation ready for Sept 1 synthesis meeting. See `docs/sessions/S06-HANDOFF.md`.

> ## 🟡 S07 — Credentials exposure remediated + vault onboarding (2026-08-26)
> Verified daily-digest/weekly-check automation healthy. Found and fixed a real incident while onboarding this project into the workspace's new credentials vault: Telegram bot token, DB passwords (including a cross-project hermes_v2 one), and the Grafana password were committed in plaintext to this project's **public** GitHub repo. Redacted (commit `e49ca82`) and rotated this project's own two secrets; hermes_v2's exposed passwords flagged for a session scoped there instead. Bonus fix: server's git clone had silently diverged from `origin/main` since ~S06 — reset and reconciled. Added `_credentials/jr_hermes_vps/` scaffolding. **Telegram token rotation still pending user's @BotFather action** — see `docs/sessions/S07-HANDOFF.md`. Not the "post-synthesis" S07 originally planned in S06 — that still waits for Sept 1.

> ## 🟢 S08 — Closed all four S07 pendings (2026-08-26)
> hermes_v2's DATABASE_URL/HERMES_LOG_DB_URL rotated cross-project (self-corrected a ~7-min outage mid-rotation); found and fixed a stale duplicate DATABASE_URL in this project's own `.env`; `@jr_crypto_knife_bot` mystery confirmed resolved (hermes_v2's own legacy bot); two vault items staged for Jorge. See `docs/sessions/S08-HANDOFF.md`.

> ## 🟢 S09 — hermes_v2 → JR Hermes Ingestor split (redirected session, 2026-08-26)
> Session opened here but redirected by the user to a larger cross-project task: split `hermes_v2` into a new standalone project, `JR Hermes Ingestor` (local repo + GitHub remote, no server deployment). `hermes_v2` archived in full to `_archive/hermes_v2-pre-ingestor-split/`. Nothing changed in JR Hermes VPS itself — this project's `/opt/hermes_v2` cross-read stays valid until Ingestor's own server deployment happens. Full split detail lives in JR Hermes Ingestor's own `docs/sessions/01-10/S1-HANDOFF.md`. See `docs/sessions/S09-HANDOFF.md`.

> ## 🟢 S13 — Deep forensic audit + P1 remediation (2026-09-05)
> Full live forensic sweep of the Hetzner host. **Both P1 (High) items fixed and verified live:** (1) `hermes_vps_health_check.py` was emitting false CRITICALs every run (`hermes_v2` in `SYSTEMD_SERVICES`; agent state `disabled` mistreated as a fault) → weekly + monthly units permanently `failed`, host `degraded`. Fixed → all-INFO, exit 0, `is-system-running` = **running**. (2) Both `/opt/hermes-*` deploy clones badly diverged and self-worsening via the findings-export git loop → hard-reset + made `export_hermes_vps_findings()` self-healing (`_sync_repo_to_origin` + push-rollback). Bonus: dropped fragile `EnvironmentFile=/opt/hermes_v2/.env` from all 3 units (verified `/root/.hermes_vps/.env` sufficient), fixed monitoring scope in CLAUDE.md (netdata is live, not Prometheus/Grafana), gitignored `logs/`, freed 543 MB journald. Everything else (reboot, disk cleanup, `/opt/hermes_v2` teardown) is user-gated or cross-project — see `docs/sessions/S13-HANDOFF.md` §4.

> ## 🟢 S11 — DB crisis catch-up, cross-project notices closed, daily-digest fix deployed live (2026-09-05)
> Confirmed S10's DB corruption crisis had already been resolved (undocumented) via Ingestor's own S27 audit; closed 3 pending cross-project notices; root-caused 3 failed systemd units (weekly/monthly health checks failing on a stale git-push step, daily-digest failing on unescaped Telegram HTML). Fixed, staged, smoke-tested, and — after explicit user go-ahead — **deployed and live-verified** the daily-digest fix (`status=0/SUCCESS`, real digest sent). Weekly/monthly git-push bug and stale `hermes_v2` references in `hermes_vps_health_check.py` remain open for S12. See `docs/sessions/S11-HANDOFF.md` and `docs/sessions/S12-HANDOFF.md` (continuation pickup).

> ## 🟡 S14 — Closed all S13 pendings, reboot executed, one new cross-project bug surfaced (2026-09-06)
> With explicit user go-ahead on every gated item: dropped `temp_recovery_s23` DB (2.6 GB, safety-dumped first), removed unused `/swapfile2` (8 GB), added a persistent journald cap and a fail2ban `recidive` jail, ran `apt dist-upgrade` (postgres auto-restarted via trigger, replication verified unaffected), then executed the planned reboot (kernel `-137`→`-139`) with a clean `hermes-ingestor` stop/start and full post-reboot verification (nginx, postgres bind, replication, all timers — all green). Disk 70%→58%. **New finding, not fixed here:** `walk_forward_monitor.service` (hermes_v2-owned) is broken — the `sentiment` table in the `hermes_v2` DB is now owned by `hermes_ingestor` (apparent side effect of the DB least-privilege split) and `hermes_v2`'s role lost SELECT on it; host now shows `degraded` solely because of this real cross-project issue (not a health-check false positive). Cross-project notices written to JR Hermes Ingestor and JR Basic Crypto Signals. See `docs/sessions/S14-HANDOFF.md`.

> ## 🟢 S15 — S14 residuals closed; host back to `running` (2026-09-06)
> With the user's explicit one-time authorization to apply a cross-project fix directly: root-caused and fixed `walk_forward_monitor.service` live — `public.sentiment` (hermes_v2 DB, owned by `hermes_ingestor` since the least-privilege split) was re-granted to `crypto_signals_research`/`cyclestation`/`audit_reader` but **not** the `hermes_v2` role. Applied `GRANT SELECT ON public.sentiment TO hermes_v2`; service now exits `0/SUCCESS`, `is-system-running` **`degraded` → `running`**, replication `streaming/0`. Deliberately did *not* blanket-grant the other 19 ingestor-owned tables `hermes_v2` lost (verified `bronze-audit-daily`/`funnel_scoring`/`server_health_audit` last runs all exited 0 — none need them). Verified the stale `/opt/hermes_v2/.env` CLAUDE.md flag is a non-issue (script clean since S13). All other S14 residuals are load-bearing (`/opt/hermes_v2` teardown) or too-fresh (1.2 GB safety dump) — documented, not forced. Cross-project notice to Ingestor to fold the grant into source. See `docs/sessions/S15-HANDOFF.md`.

> ## 🟢 S16 — All pendings closed or escalated for ownership transfer (2026-09-06)
> **Clevious VPS S50 parity (🟠) shaped + replied:** new binding bullet in `HERMES_PLATFORM_STANDARD.md` §3 R5 — replication-critical Postgres params (`max_connections`/`max_worker_processes`/`max_wal_senders`/`max_prepared_transactions`/`max_locks_per_transaction`) must bump the Contabo standby to matching-or-higher in the *same session*; detection accepted with **Clevious VPS owning** the primary↔standby diff-check on the Contabo Tier-1 watch; standby headroom bump ack'd. **hermes_v2 residue fully escalated to JR Hermes Ingestor** — one ESCALATION notice (pushed to `s27-s28-audit-fixes`) hands over all 5 items: `/opt/hermes_v2` teardown (5 units), `hermes_v2` DB drop (2.7 GB), the S15 `sentiment` grant, Ingestor's `backup-pre-s*` dirs (~1.76 GB), dead `prometheus.service` path. **`orphaned-s59` (1.1 GB) escalated to JR Basic Crypto Signals.** Three host actions **staged but SSH-blocked** by the auto-mode classifier: delete `temp_recovery_s23-pre-drop-s14.dump` (1.2 GB, **user pre-approved, no grace period**), sync `/opt/HERMES_PLATFORM_STANDARD.md`, final host verification. See `docs/sessions/S16-HANDOFF.md` for full detail. Also **codified CONTINUOUS_IMPROVEMENT_STANDARD.md §5f Rule T-LOG.2** (user directive) — every automated WARNING/ALERT event must be dual-written (findings log + Telegram), all projects, next session forward; JR Hermes VPS carries the first compliance audit (S17). 7th cross-project re-affirmation of `#Interaction NN` numbering. All 4 sibling repos synced/pushed. See `docs/sessions/S16-HANDOFF.md` §3 + §6.

> ## 🟢 S17 — Full observability build + all S16 pendings closed; host at peak health (2026-09-06)
> Auto mode off, full SSH. **S16 staged items done:** 1.2 GB safety dump deleted (disk 58%→56%), 3 workspace standards synced to `/opt/`, final host verification. **T-LOG.2 compliance audit:** 9 stderr-only warning paths found in the health check + digest; all routed through a new single dual-write sink `scripts/log_finding.py` (`event_uid` correlation, write-ahead outbox journal, self-reports on partial failure); digest ported psycopg2→psycopg3. **Tier 4 built + live:** `deploy/sql/S17_findings_log_tier4.sql` (action_status ladder + `findings_log` → TimescaleDB hypertable, 1-month chunks, compression after 90d, **NO retention — Rule T-LOG.3**, user directive replicated platform-wide), `hermes_vps_escalation_check.py` (15-min timer, row-is-the-state, S71 in_progress+owner relief, GM-ladder mirror). **Tier 3 built + live:** `hermes_vps_guardrail.py` (boot + 5-min, read-only, N=2 debounce, T3.10 heartbeat), `deploy_guardrail.sh` (T3.11). **Tier 0:** `StartLimit*` on all 5 units. **Smoke test caught a real escalation/reconcile feedback loop before go-live** — fixed to summary-only emission. **nginx:** `location = /` repointed off `/opt/hermes_v2/public` → new neutral `public/index.html` (before/after `curl` identical; clears the last nginx blocker on the hermes_v2 teardown). Archived the never-live Prometheus/Grafana tree to `deploy/_archived/`. Branch: `main` now default, `master` deleted. **Final: `is-system-running`=running, 0 failed units, 0 open criticals, replication streaming/0, disk 56%, 5 timers scheduled.** Test rows that leaked to the GM's unified DB during smoke tests were cleaned (GM notice sent). See `docs/sessions/S17-HANDOFF.md`.

> ## 🟢 S18 — Escalation-check INFO emission bounded; all owned paperwork closed (2026-09-06)
> The S17 first-check surfaced a real defect: the Tier 4 escalation check wrote **3 INFO rows every 15-min cycle unconditionally** (288/day) into the no-retention `findings_log`, and `insert_findings` never named `action_status` so every row (INFO included) took the DB default `open` — "0 open actionable findings" had drifted 86→111 and was climbing. Fixed: extracted the guardrail's emission gate to `scripts/emission_state.py` (shared `throttle()`), wired into the escalation check with `debounce_default=1` (a real WARNING/CRITICAL still emits on cycle 1), added `initial_action_status()` to `log_finding.py` (INFO→`no_action_needed`), `deploy/sql/S18_findings_log_info_settle.sql` settled the 111 pre-fix rows (state update only — T-LOG.3), 4 new `deploy_guardrail.sh` assertions, 11 new tests. Staged + smoke-tested in a host `git worktree`, then deployed: **emission 288/day → ~24/day, 0 `open` rows of any severity, host `running`.** Paperwork: Clevious S44 unattended-upgrades **decided** (accept upgrades / gate reboots — `HERMES_PLATFORM_STANDARD.md` R5 + `/opt` synced); GM S75+S71 **closed** (remediated S13/S17, live-confirmed); Clevious S40 `:5434` **handed back** (needs a Contabo reboot). See `docs/sessions/S18-HANDOFF.md`.

> ## 🟢 S19 — Tier-4 queue integrity restored + guardrail hardening (cross-project, driven from Clevious VPS S51, 2026-09-07)
> Live read-only checks (verifying the pendings list) found three defects. **(1) The Tier 4 escalation ladder was silently empty:** `deploy/sql/S17_findings_log_tier4.sql` ran an **age-based, severity-blind** `UPDATE … no_action_needed WHERE ts < now()-7d`, retro-closing 17 CRITICAL + 9 WARNING rows — `open_critical` selects `open`/`in_progress`, so "0 open actionable findings" was a false all-clear for two sessions. Fixed: `deploy/sql/S51_findings_log_severity_triage.sql` (all 26 rows individually reviewed live — all confirmed stale/false/resolved, zero re-opens — stamped `[S51 triage: …]`, state-update only, T-LOG.3); new guard both ways — `log_finding.settled_without_triage` → `queue_integrity_finding` (runtime, every 15 min) + `deploy_guardrail.sh` **step 7b** (deploy); `CONTINUOUS_IMPROVEMENT_STANDARD.md` **Rule T-LOG.4** (no age-blind settle, workspace + `/opt`). **(2) Exec-bit drift:** 7 scripts committed 0644 but 0755 on host; `deploy_guardrail.sh` step 1 did `chmod` *then* `test -x` (self-fulfilling — the exact S67 203/EXEC risk on a fresh clone). Fixed: `git update-index --chmod=+x`; step 1 now asserts the *committed* mode + covers `health_check.py`/`daily_digest.py`; `REPO`/`PY` env-overridable for real worktree smoke tests. **(3) `api.health` bug:** `summary="api.health: ok"` at `severity=critical` when the API said ok but an agent was unhealthy — `classify_api_health()` extracted + unit-tested, summary now names the fault. +9 tests (suite 39). Staged worktree smoke test → `git pull` → live-verified (`deploy_guardrail.sh` exit 0, both timers `0/SUCCESS` on new code, host `running`, 0 failed, replication `streaming/0`, disk 56%). **`/opt` standards: 3→6 synced.** **Version parity** (kernel/PG/TimescaleDB across both hosts): live inventory taken; both run TimescaleDB 2.29.0 but installed pkgs are 2.29.2 (Hetzner PGDG) / 2.29.1 (Contabo Ubuntu-archive) — **latent divergence at next PG restart**. Escalated to **GM to own** (`JR_VPS_Orchestrators/docs/CROSS-PROJECT-NOTICE-2026-09-07-clevious-s51-cross-host-version-parity-ownership.md`, `89bcf4a`); non-overlapping with Clevious's five-GUC parity check. See `docs/sessions/S19-HANDOFF.md` (+ `Clevious VPS/sessions/S51-HANDOFF.md`, session of record).

> ## 🟢 S20 — `parity_reader` role provisioned on the Hetzner primary (cross-project, Clevious S51 C1-A, 2026-09-07)
> Closed the one JR-Hermes-VPS-side blocker left by Clevious S51: their `contabo_tier1_watch.py` standby-parity check had **no role to read the 5 replication-critical GUCs from the Hetzner primary**. Provisioned `parity_reader` — a bare `LOGIN` role (no `SUPERUSER`/`CREATEDB`/`CREATEROLE`, **no `pg_monitor`/`pg_read_all_settings`** per the S19.4 `primary_conninfo`-cleartext lesson), `CONNECT` on a new empty holding DB `parity` only, `pg_hba`-scoped to Contabo `100.121.245.4/32`. `deploy/sql/S20_parity_reader_role.sql` + one `pg_hba.conf` line (reload-only, no restart — cluster already binds `100.97.62.7:5432`). Credential in `_credentials/jr_hermes_vps/parity_reader.md`; handed to Clevious via `docs/CROSS-PROJECT-NOTICE-2026-09-07-parity-reader-role-provisioned.md` (they own the `contabo_tier1_watch.py` wiring — their S52). `HERMES_PLATFORM_STANDARD.md` R5 now names the provisioned read path. Staged worktree smoke test → live apply → probe returns 5 rows as `parity_reader`, negative checks deny, host `running` / replication `streaming/async/0` unaffected. Roles-table reconciliation in `VPS_CONNECTIVITY_REFERENCE.md` still pending (noted). 11th cross-project re-affirmation of the `#Interaction NN` + hallucination-flag ground rule (already binding + hook-enforced; `INTERACTION_NUMBERING_STANDARD.md` + `/opt` synced). Session of record is **Clevious VPS S52** (`Clevious VPS/sessions/S52-HANDOFF.md`). See `docs/sessions/S20-HANDOFF.md`.

> ## 🟢 S19b — Guardrail↔escalation deadlock + ~40k-row alert storm FIXED (incident response, 2026-09-10)
> Named S19b because `S19-HANDOFF.md` + `S20-HANDOFF.md` already existed (user's call). JR Hermes Ingestor S40/S41 (escalated to GM) flagged `hermes-vps-guardrail.service` + `hermes-vps-escalation.service` in a self-sustaining deadlock since 2026-09-08 — ~40,094 findings_log rows, ~16.3k Telegram delivery failures. **Root cause (verified live):** seed was `hermes-healthcheck.service` (Ingestor's check, our unit file) exiting non-zero on a real now-recovered CRITICAL → `failed` unit; the Tier 3 guardrail alarmed on it and, because `run()` returned 1 on any critical, **became a `failed` unit itself** → alarmed on its own failure → Tier 4 escalation escalated that every 15 min, writing a fresh CRITICAL row per cycle, nesting `CEO ESCALATION … "CEO ESCALATION …"`. **Fix (branch `s19b-deadlock-fix`, on `main`, deployed):** exit-code contract (0 = audit ran, 2 = could not run — a CRITICAL finding never fails the oneshot); guardrail `check_failed_units()` excludes its own 2 units (liveness = T3.10 heartbeat check); escalation emits once per band crossing gated on the row's own `escalated_gm_at`/`escalated_ceo_at` latch (`is_first_band_crossing`); `open_critical()` excludes the check's own output + notification rows written `no_action_needed`+`[meta:]`; `send_telegram()` honours a 429 `retry_after` once; `reconcile` `orphan_db` counts only open/in_progress, `delivery_failed` 6h-recency-gated; `deploy_guardrail.sh` step 9. **51 tests (+13).** **Data:** `deploy/sql/S19b_findings_log_storm_triage.sql` class-scoped stamped settle (`UPDATE 39726`, T-LOG.3 state-only, T-LOG.4 not age-blind, ran as runtime role — has UPDATE priv); 16,270 storm outbox lines archived to `telegram_outbox.jsonl.storm-s19b-archive`. Pre-dump `hermes_vps_log_pre-s19b.dump`. **Result: 0 open/in_progress findings, `is-system-running` = running, both timers green, deploy_guardrail.sh all 9 pass.** Also applied `ReadWritePaths=/opt/hermes-ingestor/logs` + `ExecStartPre` guards to `hermes-healthcheck.service` (S36/S37/S39 ask, ~3 days pending — heartbeat file now writes). **Concurrent Ingestor S42** verified the fix live, committed the reply notice, closed `healthcheck.sh` exit-0-on-finding (`22c3dc8` — the seed antipattern) + armed `HEALTHCHECK_HEARTBEAT_ENABLED` + restarted `hermes-ingestor.service` clean. **Open after S19b:** (1) GM to bulk-triage `vps_orchestrator_findings` for mirrored storm CRITICALs then close the S41 escalation; (2) `VPS_CONNECTIVITY_REFERENCE.md` roles-table reconciliation (ours, housekeeping); (3) `/opt/hermes_v2` teardown + stale `FRED_API_KEY` (Ingestor, escalated S16). New durable lesson: `memory/reference_monitoring_exit_code_contract.md`. See `docs/sessions/S19b-HANDOFF.md`.

> ## 🟢 S21 — Roles table reconciled + deep forensic audit + user-authorized disk cleanup (2026-09-10)
> Three phases. **(1) P2 closed** (last S19b owned pending): rewrote `### PostgreSQL roles` in `docs/VPS_CONNECTIVITY_REFERENCE.md` §5 from a live read-only inventory of both hosts — databases mini-table, full Hetzner `:5432` table (18 login roles + `vps_orchestrator` NOLOGIN, Owns/Used-by/provenance), `:5435` `16/orch` cluster pointer, compact Contabo `:5434` list, 8-rule cross-host `pg_hba` matrix. **(2) Deep forensic audit** — no CRITICAL/HIGH; S19b deadlock fix verified holding (0 unit failures since 10:00, `deploy_guardrail.sh` 9/9, emission back to ~1/hr). 2 MEDIUM, both → cross-project notices: **A1** `hermes_ingestor_log` DB has zero backup coverage (Ingestor+GM); **A2** `:5435` `vps_orchestrator` DB (~950 MB) dumps to only ~30 MB, completeness unverified (GM). **(3) User-authorized disk cleanup 54%→47%** (~5.6 GB): `apt autoremove`; `/opt/backups/hermes_v2/manual/` stale S68 dumps (2.4 GB); 6 stale Ingestor deploy snapshots (2.6 GB, **closes the S16-escalated `/opt` clutter item**); `/opt/archives/crypto_db_v1_archive` (578 MB, verified sole copy of a decommissioned DB, deleted on explicit go-ahead). Also gzipped the 2 S19b storm outbox archives (13→0.9 MB). **No JR-Hermes-VPS-owned pending open** — B3 (sshd `ListenAddress`, needs go-ahead) / B8 (`DROP ROLE crypto_platform`, needs consumer check) are low-priority user-decision items; X1/X3/P3/A1-A2/Y1–Y4 are GM / Ingestor / Clevious. Host `running`, 0 failed units, 0 open findings, replication `streaming/async/0`. See `docs/sessions/S21-HANDOFF.md`.

> ## 🟢 S22 — Both S21 owned items closed; cross-project sweep finds Y1/Y2 already done elsewhere (2026-09-11)
> **B8**: live-verified `crypto_platform` was a genuine orphan (0 connections, 0 grants in `hermes_v2`, no `crypto*` DB, no `/opt/crypto_platform`, no systemd refs — the only surviving mentions are the decommissioned `crypto_data` project's stale bootstrap files) — `pg_dumpall --roles-only` snapshot, `BEGIN/ROLLBACK` smoke test, then `deploy/sql/S22_drop_crypto_platform_role.sql` applied for real (its own `pg_shdepend` hard-gate returned 0 rows first). Dropped, verified gone; `VPS_CONNECTIVITY_REFERENCE.md` 18→17 login roles. **B3**: `sshd`'s `ListenAddress` is inert under this host's socket-activation, so the real fix is an `ssh.socket` drop-in — staged, `systemd-analyze verify`d, applied with a 10-min armed auto-revert, both `:22` (Tailscale) and `:52222` (public fallback) confirmed reachable from fresh connections, **then** disarmed. `deploy/ssh.socket.d/20-jr-bind-scope.conf` now tracked. **Cross-project sweep** (read-only, nothing else touched): **Y1 + Y2 confirmed already closed** by Clevious VPS S53/S57 (parity-check wiring live+quiet; standby GUC headroom holding at 16/1024). A1/A2/X1/X3/P3/Y3(B7)/Y4 all re-confirmed still genuinely waiting on their owners (GM's newest session S77 predates both our S21 notices and the S19b storm; Ingestor S42 explicitly restates X3 as open; P3's reply notice sits untracked in GM's own repo). **No JR-Hermes-VPS-owned pending remains.** Host `running`, 0 failed units, 0 open findings, replication `streaming/async/0` (424 B lag), disk 46%, `deploy_guardrail.sh` 9/9 (re-run clean after both changes). See `docs/sessions/S22-HANDOFF.md`.
---
