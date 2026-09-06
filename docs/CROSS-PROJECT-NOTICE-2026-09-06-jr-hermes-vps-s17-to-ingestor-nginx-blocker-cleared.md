# Cross-Project Notice: JR Hermes VPS S17 → JR Hermes Ingestor — nginx `/opt/hermes_v2` blocker CLEARED

**From:** JR Hermes VPS (S17, 2026-09-06)
**To:** JR Hermes Ingestor
**Re:** the S16 ESCALATION notice (`…-s16-ESCALATION-hermes-v2-teardown-ownership.md`), item 1

---

## The nginx blocker is gone

S16 handed you `/opt/hermes_v2` teardown, blocked on (among others) nginx still
serving its landing page from `/opt/hermes_v2/public`.

**S17 removed that dependency.** The live host config
(`/etc/nginx/sites-enabled/hermes-vps`, deployed from
`JR Hermes VPS/deploy/nginx.conf`) now serves `location = /` from
`/opt/hermes-vps/public/index.html` (a neutral holding page owned by this
project). Verified live: `nginx -t` ok, `curl` of `/`, `/health`, `/metrics` and
a 404 path all identical before/after. `nginx -T | grep /opt/hermes_v2` returns
only comment text — **0 functional references.**

## What this means for the teardown

`/opt/hermes_v2/public/` is no longer read by anything on the host. The remaining
`/opt/hermes_v2` teardown items are yours as before:
- 5 hermes_v2-owned systemd units (`bronze-audit-daily`/`-weekly`,
  `funnel_scoring`, `server_health_audit`, `walk_forward_monitor`) — all
  `loaded/inactive/dead` with active timers (scheduled oneshots), verified S17.
- `hermes_v2` DB drop (2.75 GB, verified S17).
- host-side `/etc/systemd/system/prometheus.service` (dead config path).
- The S15 `GRANT SELECT ON public.sentiment TO hermes_v2`.
- `/opt/hermes-ingestor.backup-pre-s*` dirs.

Nothing else on the host now points at `/opt/hermes_v2`. When you're ready to
remove it, the nginx side is clear.

## Also: the `/dashboard` and `/_next/` nginx proxies

Those still route via the hostname `hermes-v2.vercel.app` — but that's a
**Next.js rewrite alias for the crypto-signals Vercel app**, not a
`/opt/hermes_v2` filesystem dependency. Live, low-traffic (~5 hits/2 days), left
as-is. Not a teardown blocker.

See `JR Hermes VPS/docs/sessions/S17-HANDOFF.md` §6.
