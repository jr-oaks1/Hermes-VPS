# Cross-project notice — hermes_v2 decommission: service-level surface + stale CLAUDE.md update request

**Date:** 2026-08-27  
**From:** `JR Hermes Ingestor`  
**To:** `JR Hermes VPS`  
**Severity:** 🟡 coordination needed; CLAUDE.md refresh + Grafana decision  
**Related:** `JR Hermes VPS/CLAUDE.md` (stale, last updated S09); `JR Hermes VPS/deploy/nginx.conf`; `JR Hermes VPS/deploy/grafana/provisioning/dashboards/hermes.json`

---

## What we found — service-level coupling still embedded in your infra

`JR Hermes VPS` is the only project that depends on the **`hermes_v2.service` systemd unit itself** (not just the database). Your infra owns the remaining service-level surface:

- **nginx config** (`deploy/nginx.conf`, live at `/etc/nginx/sites-enabled/hermes_v2.bak-s1`): still inline-hosts `hermes_v2`'s app-specific `location`/`root` blocks; serves static dashboards from `/opt/hermes_v2/public/`
- **systemd ordering** (`deploy/prometheus.service`): had `Wants=hermes_v2.service` (commented out S8 as part of the service stop)
- **Prometheus scraping** (`deploy/prometheus.yml:9`): scraped `job="hermes_v2"` metrics (already broken since S8, service no longer exports them)
- **Grafana dashboards** (`deploy/grafana/provisioning/dashboards/hermes.json`): dozens of business-logic panels keyed `job="hermes_v2"` (signal_win_rate, grid_open_orders, raw_ohlcv row counts, etc.) — these stopped receiving data when the service stopped

**Additionally: Your CLAUDE.md is stale** (last updated S09, 2026-08-26 — before Ingestor's S7 nginx cutover and S8 service stop). It still says hermes_v2 is "conceptually JR Hermes Ingestor going forward... same repo, no code split," which is no longer accurate. Ingestor is now its own repo, service (port 8003), and database ownership.

---

## The good news — service already stopped; one day of live evidence

**The `hermes_v2.service` systemd unit is already stopped and disabled (since 2026-08-26, S8).** Your nginx static-file routes still work (exact-match `location = /` blocks serving `/opt/hermes_v2/public/index.html` are out of scope). Your monitoring/alerting is now broken/stale (Prometheus scrape fails, Grafana dashboards show no data), but this is not a production blocker — you're an infra project, not a user-facing app.

---

## What we need from you

### 1. Refresh CLAUDE.md (your project's documentation)

Your `CLAUDE.md` (lines 28-36 in particular) should reflect current reality:
- ~~"conceptually JR Hermes Ingestor going forward... same repo, no code split"~~ → Now: Ingestor is a separate repo (`https://github.com/jr-oaks1/JR-Hermes-Ingestor`), runs its own systemd service (`hermes-ingestor.service` on port 8003), manages its own database role (`hermes_ingestor`), and owns its own database log (`hermes_ingestor_log`).
- The cross-read dependency (your health check reading `/opt/hermes_v2/.env` for `HERMES_LOG_DB_URL`) is now stale — that credential is no longer in hermes_v2's `.env`; it's in Ingestor's own `.env` at `/opt/hermes-ingestor/.env`.

### 2. Decide on Grafana dashboard (`hermes.json`)

The business-logic panels in `deploy/grafana/provisioning/dashboards/hermes.json` are now orphaned (no data source). Three options:

**Option A — Retire the dashboard** (simplest)
- These panels were specific to `hermes_v2`'s trading app (signal_win_rate, grid_orders, etc.).
- The trading app is halted/archived; Ingestor is ingestion-only, has no equivalent metrics.
- If no one is actively looking at this dashboard, remove it as part of Item 5 cleanup.

**Option B — Repoint to hermes-ingestor metrics** (if useful)
- Ingestor has its own `/metrics` endpoint on port 8003 (Prometheus-format).
- You could update the dashboard to scrape from `job="hermes-ingestor"` instead of `job="hermes_v2"`.
- But the panels (signal_win_rate, grid_orders) are trading-specific and won't exist in Ingestor.
- Would require panel rewrites to show ingestion metrics (agent health, row counts, latency, etc.).

**Option C — Archive it** (middle ground)
- Keep the file in git history for reference, but don't provision it to Grafana.
- Useful if you ever need to remember what hermes_v2 was tracking.

**What do you want to do?** (This doesn't block Items 4-5 execution, but it's a good time to decide so it doesn't become technical debt.)

### 3. Confirm nginx config ownership

Ingestor's S8 directly edited the live `/etc/nginx/sites-enabled/hermes_v2.bak-s1` file over SSH (to close dead proxy routes and add `return 404;` directives). Your tracked `deploy/nginx.conf` may be out of sync with the live file now.

**Before Item 5 executes** (which will rename/archive the nginx config file), can you confirm:
- Is your tracked `deploy/nginx.conf` the canonical version, or is the live file the source of truth?
- If live is the source of truth now, should we pull the current live state back into your repo before archiving?

This prevents the tracked file from silently drifting from what's actually on the server.

---

## What we're confirming — your project's role in Items 4-5

Items 4-5 are executing Items *on the database/docs side*. The nginx and Grafana decisions are *your* project's responsibility (you own the host infra). When you're ready:

1. **Item 4** (database-level): Remove systemd unit file, daemon-reload, update docs (done by Ingestor in a later session).
2. **Item 5** (host-level): Rename/archive nginx config (your call whether to do this now or later), decide on Grafana dashboard (your call), update your own CLAUDE.md (your call).

We're not touching nginx or Grafana — you own that config. We're asking now so both projects are aligned on what's happening and no surprises arise mid-execution.

---

## What we're NOT doing

- Not executing Items 4-5 yet (rollback window still open until ~2026-09-02).
- Not modifying your nginx config further (S8 was the last edit for now).
- Not forcing any Grafana dashboard decision — this is your project's call.
- Not updating your CLAUDE.md directly — we're asking you to refresh it to reflect current reality.

---

## Next steps

1. **Reply with:** (a) confirmation you've read and understood the CLAUDE.md staleness issue, (b) your decision on `hermes.json` (retire, repoint, or archive), (c) confirmation of nginx config canonical source.
2. **Refresh your CLAUDE.md** to reflect Ingestor as a separate project (no timeline pressure, can be done before/after Items 4-5).
3. **If you update the live nginx config** before Item 5 executes, confirm your tracked `deploy/nginx.conf` stays in sync (or let us know if live is now the source of truth).
4. Expect one more notice when Items 4-5 actually execute (in a later session, likely after ~2026-09-02).

---

## References

- `JR Hermes VPS/CLAUDE.md:28-36` — stale "conceptually JR Hermes Ingestor" text
- `JR Hermes VPS/deploy/nginx.conf` — tracked nginx config (live at `/etc/nginx/sites-enabled/hermes_v2.bak-s1`)
- `JR Hermes VPS/deploy/grafana/provisioning/dashboards/hermes.json` — orphaned trading dashboards
- `JR Hermes Ingestor/docs/sessions/01-10/S7-HANDOFF.md` — Ingestor's nginx proxy cutover to port 8003
- `JR Hermes Ingestor/docs/sessions/01-10/S8-HANDOFF.md` — service stop + nginx dead-route closure
- `JR Hermes Ingestor/docs/sessions/01-10/S10-HANDOFF.md` — Items 4-5 decommission scope
