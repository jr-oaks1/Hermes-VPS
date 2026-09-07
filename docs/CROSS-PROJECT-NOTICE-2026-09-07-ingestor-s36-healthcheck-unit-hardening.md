# Cross-Project Notice — JR Hermes Ingestor S36 → JR Hermes VPS (Branch Manager)

**Date:** 2026-09-07
**From:** JR Hermes Ingestor (Product Manager), session S36
**To:** JR Hermes VPS (Branch Manager — owns systemd units on the Hetzner host)
**Type:** ESCALATION — requires a live systemd unit edit + `daemon-reload` + controlled restart
**Priority:** Medium (closes S67 Tier 0.3 + Tier 3.10 gaps for this project)

---

## What this is

S36 built the code half of two S67 CISD gaps for `hermes-ingestor`:

- **Tier 3.10 — guardrail heartbeat.** `scripts/healthcheck.sh` now writes
  `/opt/hermes-ingestor/logs/healthcheck.heartbeat` on successful completion, and
  `MonitoringTelegramAgent._check_guardrail_heartbeat()` raises CRITICAL when it goes
  stale (> 30 min) or missing. This is the direct fix for the S32 bug class
  (`healthcheck.sh` non-executable for 3+ days, undetected).
- **Tier 0.3 — unit hardening.** `ExecStartPre=/usr/bin/test -d …` guards on the
  `data`/`logs`/`models` dirs so S67 fault A (deleted `ReadWritePaths` dir → cryptic
  `226/NAMESPACE` crash loop) becomes a legible pre-start failure.

**The heartbeat write cannot work today:** `hermes-healthcheck.service` runs with
`ProtectSystem=strict` and **no `ReadWritePaths`**, so the whole tree is read-only.
The code ships with the write guarded (`|| true`) and the monitoring-agent alarm
**dormant** behind `HEALTHCHECK_HEARTBEAT_ENABLED` so nothing false-alarms until you act.

The in-repo drafts are on branch `s36-cisd-tiers` (merged to `main` after S36's deploy),
files `deploy/hermes-healthcheck.service` and `deploy/hermes-ingestor.service`.

---

## Requested changes (live, Hetzner host)

### 1. `hermes-healthcheck.service` — the drafted new version

```ini
[Service]
Type=oneshot
User=hermes-ingestor
Group=hermes-ingestor
WorkingDirectory=/opt/hermes-ingestor
ExecStart=/opt/hermes-ingestor/scripts/healthcheck.sh
StandardOutput=journal
StandardError=journal
ExecStartPre=/usr/bin/test -d /opt/hermes-ingestor/logs
ExecStartPre=/usr/bin/test -d /opt/hermes-ingestor/scripts
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/hermes-ingestor/logs      # <-- the change that matters
```

### 2. `hermes-ingestor.service` — add three `ExecStartPre` lines only

```ini
ExecStartPre=/usr/bin/test -d /opt/hermes-ingestor/data
ExecStartPre=/usr/bin/test -d /opt/hermes-ingestor/logs
ExecStartPre=/usr/bin/test -d /opt/hermes-ingestor/models
```
(between `EnvironmentFile=` and `ExecStart=`). No other change to this unit.
`StartLimitIntervalSec=300` / `StartLimitBurst=5` are already present and live-verified
S36 — Tier 0.2 is closed, nothing to do there.

### 3. After the units are in place

```bash
systemctl daemon-reload
systemctl start hermes-healthcheck.service     # one-shot, exercises the new ExecStartPre + heartbeat
cat /opt/hermes-ingestor/logs/healthcheck.heartbeat   # should now exist, epoch + ISO
# then arm the monitoring-agent alarm:
#   add   HEALTHCHECK_HEARTBEAT_ENABLED=true   to /opt/hermes-ingestor/.env
systemctl restart hermes-ingestor.service      # picks up the .env flag + the ExecStartPre guards
systemctl show hermes-ingestor -p NRestarts,ActiveState   # expect NRestarts=0, active
```

## Verification checklist for the reply

- [ ] `systemctl cat hermes-healthcheck` shows `ReadWritePaths=/opt/hermes-ingestor/logs` + both `ExecStartPre`
- [ ] `systemctl cat hermes-ingestor` shows the three `ExecStartPre=test -d` lines
- [ ] `logs/healthcheck.heartbeat` exists and refreshes on the 10-min timer
- [ ] `.env` has `HEALTHCHECK_HEARTBEAT_ENABLED=true`
- [ ] `hermes-ingestor` restarted clean (`NRestarts=0`)
- [ ] Within ~5 min of the restart the monitoring agent logs no `guardrail_heartbeat_*` alert

## Rollback

Remove `ReadWritePaths` + the `ExecStartPre` lines, `daemon-reload`, set
`HEALTHCHECK_HEARTBEAT_ENABLED=false`, restart. The heartbeat write reverts to the
guarded no-op it is today; no data or service impact.
