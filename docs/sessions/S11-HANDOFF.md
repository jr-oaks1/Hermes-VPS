# S11 HANDOFF — Catch-up: S10 DB crisis resolved (undocumented), decommission notice closed, one new live bug found

**Date:** 2026-09-05
**Status:** 🟢 S10 crisis confirmed resolved; three pending cross-project notices closed;
one new CRITICAL-severity live finding opened for S12
**Duration:** ~1 session, read-only + doc/config-sync work only (no risky changes)

---

## Why this session exists

Opened cold, 5 days after S10 ("AWAITING S11 BACKUP STRATEGY DECISION", 2026-08-31).
No S11 had been written in this project's own `docs/sessions/`, so per this project's
own session-numbering discipline the record looked like the crisis was still open. It
was not — this session's job was to catch the record up to reality, then clear what else
was pending.

---

## 1. S10 database corruption crisis — CONFIRMED RESOLVED (not by this project)

**Finding (live-verified 2026-09-05 via JR Hermes Ingestor's own S27-HANDOFF.md):**
> "The S23–S26 database crisis is over. Live host verified 2026-09-04: `hermes_v2` DB
> fully recovered (6.45M `raw_ohlcv` rows, ingesting normally)... Recovery was executed
> by the Branch Manager (JR Hermes VPS) between S26 and 2026-09-02 and was **never
> documented in this repo**."

**What this means:** the Option A/B/C restore-strategy decision from S10 was made and
executed — by someone, under this project's Branch Manager role — sometime between
2026-08-31 (S26, still blocked) and 2026-09-02. It was never written up here. The only
record of it existing is a side-note in a *different* project's forensic audit two days
later. This is a real process gap: a P0-severity recovery with no S11-HANDOFF.md, no
memory update, and no commit trail in this repo.

**Not verified this session (flag):** which restore option (A/B/C) was actually chosen,
who executed it, exact commands run, or whether the "5 days of Aug 26–30 history" loss
flagged in S10 was in fact eaten or avoided. I have not re-derived this from host state
(e.g. `raw_ohlcv` time-range boundaries) — only confirmed the *outcome* (DB healthy,
6.45M rows, ingesting) via Ingestor's independent verification. If the exact mechanism
matters later (audit, postmortem), it needs forensic reconstruction from Hetzner's
`/opt/backups/hermes_v2/manual/` dated dumps (`pre-s68-repair.dump`,
`s68-verified-checkpoint-*.dump` — named per Ingestor's S27, not inspected here) — the
undocumented recovery session apparently left artifacts even though it left no handoff.

**Action taken this session:** none beyond documenting — the DB is healthy, re-doing or
second-guessing a 3-day-old successful recovery would be pure risk for no benefit.

---

## 2. Live incident (this session) — Contabo standby crash loop, self-resolved

Independent of the above: your screenshot showed live Telegram alerts
(`postgres.bind: :5432 missing`, `replication.standby: check failed`) from
`contabo_findings_sync`.

**Root cause (live-verified via `pg_log`):** at 04:44–04:52 CEST today, Contabo's
`postgresql@16-main` (hermes_v2/crypto_db standby) failed to start 4 times:
```
FATAL: recovery aborted because of insufficient parameter settings
DETAIL: max_locks_per_transaction = 128 is a lower setting than on the primary
server, where its value was 512.
```
Hetzner's primary had `max_locks_per_transaction` raised 128→512 today, per its own
config comment: `# raised S31 2026-09-05 for returns_1h chunk-count
ownership/consolidation` (whose S31 this is — unverified, likely a different project;
not traced further this session). Contabo's conf hadn't caught up yet. Both nodes are
now confirmed live at 512, replication healthy (~3 min lag, actively streaming), socket
present, service `active` since 04:55:34 CEST.

**No action needed** — self-resolved once config sync completed. Flagging only because
it's the literal live alert that opened this session.

---

## 3. Three pending cross-project notices — all closed this session

Three untracked notice files were sitting in this repo's git status, addressed to this
project, never acted on:

### a) `2026-08-27` — hermes_v2 decommission (from JR Hermes Ingestor)
Answered in full via `docs/CROSS-PROJECT-NOTICE-2026-09-05-reply-to-hermes-v2-decommission.md`:
- **CLAUDE.md refreshed** — stale "hermes_v2 conceptually Ingestor, same repo" text
  replaced with current split reality.
- **Grafana `hermes.json` retired (Option A)** — `grafana-server` confirmed **inactive**
  on the host (live check), so the dashboard was fully dormant, not just data-less.
  Moved to `deploy/grafana/provisioning/dashboards/_archived/hermes.json.retired-s11`.
- **nginx config drift closed** — tracked `deploy/nginx.conf` was 85 lines out of sync
  with the live `/etc/nginx/sites-enabled/hermes_v2.bak-s1` (dead `:8001` proxies where
  live now has `return 404;`, a `/grafana/` block live had already dropped). Tracked
  file replaced with live content verbatim. **No live nginx change made** — repo now
  matches reality, that's it.

### b) `2026-09-04` — findings-log-practice (from JR Hermes Ingestor, all projects)
Informational only, Continuous Improvement Standard §5f (Rule T-LOG.1): log findings
as-you-go via a `log_finding.py`-equivalent, if the project has a findings_log +
Telegram bot. This project does (`hermes_vps_log.findings_log`, `@JRHermesVPSBot`).
**No script exists yet here.** Not built this session (real work, deserves its own
session) — added to S12 backlog below.

### c) `2026-08-30` — PM registration + `/self-report` (from JR Hermes Ingestor)
Registers Ingestor as this project's Tier-4 subordinate per the org structure. Informational,
but its one action item — `ORCHESTRATOR_SELF_REPORT_TOKEN` populated in Ingestor's live
`.env` — **checked live and is still empty** (`/opt/hermes-ingestor/.env` on Hetzner,
value length 1 = just a newline). Integration has been silently inert since 2026-08-30.
**Not fixed this session** — the token is issued by the endpoint owner
(`JR_VPS_Orchestrators`, port 8002), not fabricated by either Ingestor or this project;
this is a cross-project coordination item, not a unilateral fix. Flagged for S12/GM.

---

## Live-verified this session (for the record)

- Hetzner `postgresql@16-main`: active, listening on `100.97.62.7:5432` + `127.0.0.1:5432`.
- Contabo `postgresql@16-main` (standby) and `postgresql@16-crypto` (crypto_signals
  primary): both active; replication lag ~3 min, streaming.
- `max_locks_per_transaction`: 512 on both nodes (was briefly mismatched, see §2).
- `grafana-server` on Hetzner: inactive.
- `hermes_v2` systemd unit: inactive, disabled, `/opt/hermes_v2` directory still present.
- `hermes_vps_health_check.py` (this repo): still hardcodes `hermes_v2` service name,
  `/opt/hermes_v2` paths — see §4 below.
- `ORCHESTRATOR_SELF_REPORT_TOKEN` in Ingestor's live `.env`: empty.

---

## 4. New finding — CRITICAL for S12: health check script never updated post-decommission

`scripts/audit/hermes_vps_health_check.py` still hardcodes, unchanged since before the
hermes_v2→Ingestor split:
- `SYSTEMD_SERVICES = ("hermes_v2", "nginx", "postgresql")` — checks a unit that has
  been `inactive`/`disabled` for 10 days by design, not by failure.
- `check_git_sync("/opt/hermes_v2")` and `repo_dir="/opt/hermes_v2"` (findings-export
  default) — `/opt/hermes_v2` still exists as a directory so this won't hard-crash, but
  it's exporting/syncing against a repo that's no longer the live source of anything.
- Reads `HERMES_LOG_DB_URL` from `/opt/hermes_v2/.env` per this project's own (now-fixed)
  CLAUDE.md description — **not independently re-verified this session** whether that
  file/credential still exists there or has moved to Ingestor's own `.env` (flag: this
  is an assumption carried from the stale doc, not a live check).

**Likely live impact:** every health-check cycle for the last ~10 days has probably
logged/alerted a false "hermes_v2 service down" finding, since the service is
*intentionally* stopped, not failed. Not confirmed this session — didn't query
`hermes_vps_log.findings_log` for the actual alert history.

**Why not fixed now:** this is a live monitoring script running on a schedule — a code
change here needs the binding smoke-test treatment (stage, verify no false-negative
introduced, only then deploy), not a rushed edit tacked onto a catch-up session.

---

## For S12

1. **Fix `hermes_vps_health_check.py`** (top priority): remove `hermes_v2` from
   `SYSTEMD_SERVICES`, repoint `repo_dir`/git-sync default and the `HERMES_LOG_DB_URL`
   env-file read at Ingestor's actual live paths (verify both first — don't assume).
   Stage + smoke-test per the binding rule before touching the live systemd timer.
2. **Query `hermes_vps_log.findings_log`** for the last 10 days to confirm/quantify the
   suspected false "hermes_v2 down" alert volume — cheap, would turn a hypothesis into
   a fact.
3. **Build a `log_finding.py`-equivalent** for this project (Continuous Improvement
   Standard §5f) — this project has the findings_log + bot, just no as-you-go script yet.
4. **Coordinate `ORCHESTRATOR_SELF_REPORT_TOKEN` issuance** with JR_VPS_Orchestrators (GM)
   — Ingestor's `/self-report` integration has been dead code since 2026-08-30 for lack
   of a token neither project can unilaterally generate.
5. **Optional forensic reconstruction** of the undocumented S26→S27 DB recovery, if an
   audit trail is ever needed (see §1) — low priority, DB is healthy now.

---

## Changes made this session

- `CLAUDE.md`: stale hermes_v2/Ingestor coupling text corrected.
- `deploy/nginx.conf`: replaced with live host content (repo-only change, zero live
  server modification).
- `deploy/grafana/provisioning/dashboards/hermes.json` → moved to
  `deploy/grafana/provisioning/dashboards/_archived/hermes.json.retired-s11`.
- `docs/CROSS-PROJECT-NOTICE-2026-09-05-reply-to-hermes-v2-decommission.md`: new, reply
  to Ingestor's S8-era notice.
- This handoff.

**No production system was modified this session** — every live check was read-only
(`systemctl status`, `ss -tlnp`, `psql` `SELECT`/`SHOW`, log reads, `diff`). The nginx
and Grafana changes are repo-only, syncing tracked files to already-live/already-inactive
reality.

---

## Session close (wrap-up)

- Commit `fbd3aa8` pushed to `origin/main` (`https://github.com/jr-oaks1/Hermes-VPS`).
  Repo confirmed clean and in sync with remote at close.
- Memory index (`~/.claude/projects/.../memory/MEMORY.md`) updated with an S11 entry;
  S10's entry marked superseded rather than deleted, per this workspace's "update or
  remove stale memory, don't silently overwrite history" convention.
- Obsidian note (`ObsidianVault/Projects/JR Hermes VPS.md`) appended with an S11
  summary in this file's established per-session format, committed locally
  (`3392183`, vault repo has no remote — local commit is the full sync).
  **Scope note:** the vault repo had substantial pre-existing drift across 8 *other*
  projects' notes (modified/untracked, none touched this session) — left entirely
  alone; only this project's own file was staged and committed.
- **Interaction-numbering + hallucination-flagging ground rule:** confirmed already
  binding workspace-wide (`GLOBAL_GROUND_RULES.md` Rules 1–2, effective 2026-08-31;
  `INTERACTION_NUMBERING_STANDARD.md` at the workspace root) — re-verified by reading
  both files live this session (interaction 02). No new rule needed; nothing to change
  here or in any other project.

## Quick resume for S12

**Start here:** §4 above (`hermes_vps_health_check.py` CRITICAL fix) is the single
highest-value next action — a 10-day-old suspected false-alert source on a live
production timer. Everything else in the "For S12" list is lower urgency and can be
sequenced after.

**Nothing is currently blocked.** No pending user decision, no open cross-project
notice addressed to this project, no in-progress risky change left mid-flight.
