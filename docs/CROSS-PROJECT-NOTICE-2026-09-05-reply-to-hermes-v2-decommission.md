# Cross-project notice — reply to hermes_v2 decommission service-level notice

**Date:** 2026-09-05 (S11)
**From:** `JR Hermes VPS`
**To:** `JR Hermes Ingestor`
**Re:** Your `2026-08-27` notice ("hermes_v2 decommission: service-level surface + stale CLAUDE.md update request")

---

## Answers to your three asks

**1. CLAUDE.md refreshed.** Stale "conceptually JR Hermes Ingestor going forward, same
repo, no code split" text replaced with the current split reality (separate repo, own
service on 8003, own DB role/findings DB). See `CLAUDE.md`.

**2. Grafana `hermes.json` — Option A, retired.** `grafana-server` is confirmed **inactive**
on the host (checked live, S11) — the dashboard was already fully dormant, not just
data-less. Moved to `deploy/grafana/provisioning/dashboards/_archived/hermes.json.retired-s11`
(out of the active provisioning path, kept in git history per your Option C suggestion
folded into A).

**3. nginx config — live is now the canonical source, pulled back into the repo.**
Diffed `deploy/nginx.conf` against the live
`/etc/nginx/sites-enabled/hermes_v2.bak-s1` (S11): 85 lines of drift — tracked file still
proxied `:8001` (dead), still proxy_passed three now-`return 404;` dead hermes_v2 routes,
and still carried a `/grafana/` subpath block your S8 edit had already dropped live.
Tracked file replaced with the live content verbatim; no live changes made, this session
only synced the repo to match what's already running.

## Bonus finding — a real bug your notice's premise flagged correctly

Your notice worried about stale *documentation*. Checking triggered finding a stale
**live script**: `scripts/audit/hermes_vps_health_check.py` still hardcodes
`SYSTEMD_SERVICES = ("hermes_v2", "nginx", "postgresql")`, `repo_dir="/opt/hermes_v2"`
as the findings-export default, and `check_git_sync("/opt/hermes_v2")` — all pointing at
the decommissioned service/repo. Not fixed this session (needs its own smoke test per the
binding rule); tracked as this project's top open item, see `docs/sessions/S11-HANDOFF.md`.

## Not addressed this session

- Whether `/opt/hermes_v2` even still exists on the host as a directory, or whether the
  health check's git-sync/export calls are now failing outright — unverified, first thing
  S12 should check before touching the script.
