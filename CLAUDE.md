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
`hermes_v2` (conceptually "JR Hermes Ingestor" going forward — ingestion +
trading logic, same repo, no code split) keeps its own app-level deploy
(`deploy.sh`, `hermes_v2.service`), its own app-level Telegram bot
(`JRHermesIngestorbot`), and its own findings export/cloud-review pipeline
(`docs/findings_export/`, `hermes_v2_log.findings_log`) — unchanged by this
split. This project's health check reads `hermes_v2`'s DB and calls its
`hermes_replication_status()` function remotely, and cross-reads
`/opt/hermes_v2/.env` for one credential (`HERMES_LOG_DB_URL`) — that's the full
extent of the coupling.

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
---
