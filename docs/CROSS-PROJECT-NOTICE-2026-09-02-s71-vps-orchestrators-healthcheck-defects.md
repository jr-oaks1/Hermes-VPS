# Cross-Project Notice: JR_VPS_Orchestrators S71 — `hermes_vps_health_check.py` defects driving false CRITICAL escalation + 2 failed units

**From:** JR_VPS_Orchestrators (S71, 2026-09-02)
**To:** JR Hermes VPS (owner of `/opt/hermes-vps/`, `hermes-vps-healthcheck-weekly.service`, `hermes-vps-audit-monthly.service`, `scripts/audit/hermes_vps_health_check.py`)
**Status:** RECOMMENDATION — not applied by us (R4 self-containment). Please apply on your own schedule.
**Affects:** `scripts/audit/hermes_vps_health_check.py`, the two systemd units, and the rows this writes into `vps_orchestrator_findings.findings_log` (`source_project='JR Hermes VPS'`)

---

## Summary

Live recon on Hetzner this session (both hosts fundamentally healthy — collectors/APIs
active, replication streaming, backups green) found that the bulk of the current
CEO/GM Telegram escalation storm is your health-check writing **false or mislabelled
CRITICAL findings** into the unified `findings_log`, which `EscalationCheck` (S70) then
re-pages every 15 minutes because nothing marks them resolved.

Four distinct defects:

### 1. `api.health: ok` is written at `severity='critical'`

Findings #193, #231, #237, #250 all have `summary = "api.health: ok"` and
`severity = critical`. A healthy result must not be a CRITICAL finding. Live check this
session: `curl http://127.0.0.1:8000/health` → `{"status":"ok", ...}`, all agents
`healthy`. This looks like the severity being set from the check's *category* rather than
its *result*.

### 2. `api.health: degraded` (#215) contradicted by live state

Same endpoint returns `status: ok`. `:8000` is nginx → `:8003` = `hermes-ingestor.service`
(the live successor). Whatever the check is probing for "degraded" is stale.

### 3. `service.hermes_v2: inactive` is CRITICAL for a decommissioned service

Findings #190, #212, #228, #234, #247. `hermes_v2.service` is `inactive/dead` since
2026-08-26 — **intentionally**, it was archived and split into JR Hermes Ingestor
(`hermes-ingestor.service`, live on :8003). The check needs to drop this assertion (or
retarget it at `hermes-ingestor.service`). As written it will fire CRITICAL forever.

### 4. `hermes-vps-healthcheck-weekly.service` + `hermes-vps-audit-monthly.service` fail every run

Both are the only failed units on Hetzner (`3d18h` / `1d18h` UNACKNOWLEDGED in Telegram).
Journal shows the checks **run and deliver Telegram fine** — the unit exits non-zero
because the final `git`-export step fails:

```
Aug 30 04:00:09 ... hermes-vps-healthcheck-weekly.service: Main process exited, code=exited, status=1/FAILURE
```

Root cause (confirmed S67 item 6, never actioned): the `docs/findings_export/` `git push`
is non-fast-forward — `/opt/hermes-vps` (and `/opt/hermes_v2`) local clones are behind
`origin/main`. Also a historical `209/STDOUT` "Failed to set up standard output"
(2026-08-22) = a `StandardOutput=` path whose directory doesn't exist.

## Recommendations

1. Set `severity` from the check *result*, not the check name. `ok` → `info`.
2. Remove or retarget the `service.hermes_v2` assertion (`hermes-ingestor.service` on :8003).
3. In the units: `git pull --ff-only` (or `fetch` + `reset --hard origin/main` on a
   read-only export clone) as an `ExecStartPre`, **and** don't let the push's exit code
   fail the unit — the health check succeeding is the point; the export is best-effort.
4. Confirm any `StandardOutput=append:/path` directory is created (`RuntimeDirectory=` /
   `mkdir -p` prestep).

## What we did on our side (so escalation calms while you action this)

The affected `findings_log` rows have been set to `action_status='no_action_needed'`
(defects 1–2, verified false live) or `'in_progress'` with `owner_project='JR Hermes VPS'`
(defects 3–4), each with a dated note in `detail`. `EscalationCheck` (S71) no longer
pages the CEO on `in_progress` rows that carry an `owner_project`; the GM still sees them.
Reverting is just setting `action_status` back to `open`.

## Why we're not applying this ourselves

R4 self-containment — we don't edit another project's scripts or unit files. Exception 3
(read-only audit access) is the basis for the finding rows and this notice.
