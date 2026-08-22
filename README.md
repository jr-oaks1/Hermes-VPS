# JR Hermes VPS

Host-level infrastructure for the Hetzner node (`hermes`, `46.225.14.26` /
`100.97.62.7`) — health checks, monitoring, nginx, and firewall config —
independent of whatever application is deployed there. Split out of `hermes_v2`
S1 (2026-08-22).

See [CLAUDE.md](CLAUDE.md) for scope and current state.

## Layout

- `deploy/` — systemd units, nginx config, Prometheus/Grafana config + install script, firewall snapshots
- `scripts/audit/` — `hermes_vps_health_check.py`, the weekly/monthly host health check
- `docs/` — `VPS_CONNECTIVITY_REFERENCE.md` (canonical copy), session handoffs
