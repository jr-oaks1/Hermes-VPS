# Daily Digest Deployment Guide

**Status:** Ready for deployment (S6+)  
**Component:** `hermes_vps_daily_digest.py` — daily operational summary to @JRHermesVPSBot  
**Schedule:** 09:00 UTC daily  
**Target:** Chat ID 360294128 (@JRHermesVPSBot)

---

## Overview

The daily digest queries `vps_orchestrator_findings` for findings from the past 24 hours, aggregates by severity and source project, and posts a formatted summary to Telegram every morning at 09:00 UTC.

**Files to deploy:**
- `scripts/audit/hermes_vps_daily_digest.py` — main script
- `deploy/hermes-vps-daily-digest.service` — systemd service
- `deploy/hermes-vps-daily-digest.timer` — systemd timer (09:00 UTC)

---

## Deployment Steps

### Step 1: Copy script to server

```bash
scp -i ~/.ssh/hermes_ed25519 \
  scripts/audit/hermes_vps_daily_digest.py \
  root@100.97.62.7:/opt/hermes-vps/scripts/audit/
```

### Step 2: Make script executable

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "chmod 755 /opt/hermes-vps/scripts/audit/hermes_vps_daily_digest.py"
```

### Step 3: Copy systemd files

```bash
scp -i ~/.ssh/hermes_ed25519 \
  deploy/hermes-vps-daily-digest.{service,timer} \
  root@100.97.62.7:/etc/systemd/system/
```

### Step 4: Reload systemd and enable timer

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "systemctl daemon-reload && \
   systemctl enable hermes-vps-daily-digest.timer && \
   systemctl start hermes-vps-daily-digest.timer"
```

### Step 5: Verify deployment

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "systemctl list-timers | grep hermes-vps-daily-digest"
```

Expected output:
```
NEXT                                 LEFT     LAST PASSED UNIT
Fri 2026-08-23 09:00:00 UTC           ~7h left -    -      hermes-vps-daily-digest.timer
```

---

## Testing

### Manual test (before timer activates)

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "cd /opt/hermes-vps && \
   source /root/.hermes_vps/.env && \
   .venv/bin/python3 scripts/audit/hermes_vps_daily_digest.py"
```

Expected output:
```
info: digest sent (N findings, past 24h)
```

### Check logs after deployment

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "journalctl -u hermes-vps-daily-digest.service -n 30"
```

---

## What the Digest Contains

**Example message:**
```
📊 Daily Digest (past 24h)
🔴 1 CRITICAL
🟡 2 warning
ℹ️ 5 info

JR Hermes VPS: 3 findings
  🔴 SSL certificate expiry: 15 days remaining
  🟡 Disk usage: 78%
  ℹ️ Weekly health check completed

Clevious VPS: 5 findings
  🟡 Replication lag: 2.3 seconds
  ℹ️ Daily sync completed
  ... and 3 more info
```

---

## Requirements

**Environment variables** (loaded from `/root/.hermes_vps/.env`):
- `FINDINGS_DB_URL` — connection string for `vps_orchestrator_findings` (must be readable)
- `TELEGRAM_BOT_TOKEN` — @JRHermesVPSBot token
- `TELEGRAM_CHAT_ID` — target chat ID (360294128)

**Python dependencies** (already in venv):
- `psycopg2-binary` — PostgreSQL connection
- `requests` — Telegram API calls

---

## Troubleshooting

### Timer not running

```bash
systemctl status hermes-vps-daily-digest.timer
systemctl start hermes-vps-daily-digest.timer
```

### Script execution fails

Check logs:
```bash
journalctl -u hermes-vps-daily-digest.service -n 50
```

Common issues:
- **FINDINGS_DB_URL not set** → Verify `/root/.hermes_vps/.env` has the variable
- **psycopg2 import error** → Ensure script runs with venv python: `.venv/bin/python3`
- **Telegram timeout** → Check network; retry in a few minutes
- **DB connection refused** → Verify `vps_orchestrator_findings` DB is accessible

---

## Disabling

```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "systemctl stop hermes-vps-daily-digest.timer && \
   systemctl disable hermes-vps-daily-digest.timer"
```

---

## Next Steps

- [ ] Deploy to Hetzner before Sept 1 synthesis meeting
- [ ] Verify first automated run (09:00 UTC on first deployment day)
- [ ] Check Telegram message format and content
- [ ] Monitor for any exceptions in journalctl for first week
