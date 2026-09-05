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
- systemd units for those checks (`deploy/hermes-vps-healthcheck-weekly.*`,
  `deploy/hermes-vps-audit-monthly.*`)
- nginx (`deploy/nginx.conf` — the single host-wide config; still contains
  `hermes_v2`'s app-specific `location`/`root` blocks inline, since nginx only
  runs once per host and someone has to own the whole file)
- Prometheus + Grafana (`deploy/prometheus.*`, `deploy/grafana/`,
  `deploy/setup_monitoring.sh`)
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
equivalent) now lives in Ingestor's own `/opt/hermes-ingestor/.env`; if the
health check script still points at the old path, that's a live bug to fix,
not documentation drift (unverified this session — flag for next session to
grep `scripts/audit/hermes_vps_health_check.py` for the old path).

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
---
