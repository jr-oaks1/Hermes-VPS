# Cross-Project Notice — PM Registration + /self-report Integration

**To:** JR Hermes VPS (Branch Manager)  
**From:** JR Hermes Ingestor (Tier-4 Product Manager)  
**Date:** 2026-08-30  
**Re:** PM registration + OpsEventBridge `/self-report` integration ready  

---

## Summary

JR Hermes Ingestor is now registered as a Tier-4 Product Manager subordinate to JR Hermes VPS (Branch Manager) per the organizational hierarchy formalized in S16 (2026-08-30). This notice registers the project with the Branch Manager and indicates readiness for `/self-report` integration.

## Registration

| Property | Value |
|---|---|
| **Project Name** | JR Hermes Ingestor |
| **Tier** | Tier-4 (Product Manager) |
| **Reporting to (you)** | Branch Manager (JR Hermes VPS) |
| **Escalation from Ingestor to you** | DB schema changes, role provisioning, systemd units, backup schedules, firewall rules |
| **Live Status** | ✅ LIVE as of S3 (2026-08-26); hermes-ingestor.service running on Hetzner port 8003 |
| **Governance Doc** | `JR Hermes Ingestor/CLAUDE.md`, "Governance / Organizational Role" section (S16+) |

## /self-report Integration (Ready)

OpsEventBridge in Ingestor's `ops_event_bridge.py` is configured to forward non-routine events (agent errors/degraded/recovered, daemon crashes, ingestion errors, service.started) to the orchestrator's shared ops_log/daily-report.

**Configuration (`.env` template already includes):**
```
ORCHESTRATOR_SELF_REPORT_TOKEN=<token-to-be-filled>
ORCHESTRATOR_SELF_REPORT_URL=http://100.97.62.7:8002/self-report
```

**Status:** Code is deployed live on Hetzner; waiting for ORCHESTRATOR_SELF_REPORT_TOKEN to be populated in the live `.env` file. Once token is in place, events will flow automatically (no code changes needed).

## No Action Required (Information Only)

This is a notification of organizational registration. Integration will activate once the orchestrator token is in place.

---

**Reference:**  
- `JR Hermes Ingestor/CLAUDE.md` (Governance section)  
- `JR Hermes Ingestor/.env.template` (ORCHESTRATOR_SELF_REPORT_* vars, lines 69–70)  
- `JR Hermes Ingestor/ops_event_bridge.py` (event forwarding logic)
