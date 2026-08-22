# JR Hermes VPS — Credential Setup Guide

**Date Created:** 2026-08-22  
**Scope:** Server-side credential configuration for `/root/.hermes_vps/.env`  
**Security:** File mode must be 600 (read by root only); never commit to git  

---

## Overview

This project requires environment variables for three categories:
1. **Monitoring infrastructure** (Prometheus, Grafana)
2. **Health-check databases** (hermes, hermes_v2_log, hermes_vps_log)
3. **Alerting** (Telegram bot)

All credentials are stored in `/root/.hermes_vps/.env` on the Hetzner server, read by systemd units via `EnvironmentFile=` directive (per `HERMES_PLATFORM_STANDARD.md`).

---

## Variable Breakdown

### Monitoring Infrastructure

**`PROMETHEUS_RETENTION_DAYS`**
- **Purpose:** Time-series data retention in Prometheus
- **Value:** `30` (default) or adjust based on disk space
- **Source:** Manual choice; update `deploy/prometheus.yml` if different
- **Set By:** deployment script or manual `systemctl set-environment`

**`GRAFANA_ADMIN_PASSWORD`**
- **Purpose:** Admin password for Grafana web UI
- **Value:** Strong password (min 12 chars, mixed case + numbers + special)
- **Source:** Set manually on server (not in any git repo or backup)
- **Location:** Generated during `setup_monitoring.sh` run or manually before systemd start
- **Backup:** Store in password manager; recovery requires database reset if lost

**`GRAFANA_DATASOURCES_UID`**
- **Purpose:** Prometheus datasource UID in Grafana (auto-generated or manual)
- **Value:** UID string (e.g., `prometheus-default`)
- **Source:** Grafana provisioning scripts or admin UI
- **Set By:** `deploy/grafana/provisioning/datasources/` (auto) or manual

### Health-Check Databases

**`DATABASE_URL`**
- **Purpose:** Main Hermes database (replication status queries)
- **Value:** `postgresql://hermes:hermes@localhost/hermes`
- **Source:** Copied from `/opt/hermes_v2/.env` or direct schema
- **Credentials:** Username `hermes`, password from hermes_v2 role setup
- **Role Requirements:** `SELECT` on replication tables

**`HERMES_LOG_DB_URL`**
- **Purpose:** hermes_v2_log database (cross-project findings export)
- **Value:** `postgresql://hermes_v2:hermes_v2@localhost/findings_log`
- **Source:** Copied from `/opt/hermes_v2/.env` (same as hermes_v2 uses)
- **Credentials:** Username `hermes_v2`, role created by hermes_v2
- **Role Requirements:** `SELECT` on `hermes_v2_log.findings_log`
- **Note:** Read-only; this project exports to GitHub, not into this DB

**`HERMES_VPS_LOG_DB_URL`**
- **Purpose:** hermes_vps_log database (this project's findings)
- **Value:** `postgresql://hermes_vps:hermes_vps@localhost/hermes_vps_log`
- **Source:** New role + database created during S2 or S3 deployment
- **Credentials:** Username `hermes_vps`, password same as role
- **Role Requirements:** `SELECT`, `INSERT` on `hermes_vps_log.findings_log`
- **Creation:** If DB/role doesn't exist on server, run:
  ```sql
  CREATE DATABASE hermes_vps_log;
  CREATE ROLE hermes_vps WITH LOGIN PASSWORD '<password>';
  GRANT SELECT, INSERT ON hermes_vps_log.findings_log TO hermes_vps;
  ```

### Alerting

**`TELEGRAM_BOT_TOKEN`**
- **Purpose:** Bot token for Hermes VPS infrastructure alerts (health checks, findings triage)
- **Value:** Telegram bot API token (long alphanumeric string)
- **Source:** Existing `@JRHermesVPSBot` (shared infrastructure bot, same as hermes_v2) OR new bot if preferred per `HERMES_PLATFORM_STANDARD.md`
- **Location:** `/root/.hermes_vps/.env` (not in git)
- **Access:** Only root can read
- **Setup:** Via Telegram BotFather; token never shared or logged

**`TELEGRAM_CHAT_ID`**
- **Purpose:** Target chat/channel for Hermes VPS alerts
- **Value:** `360294128` (existing channel ID, verified live in S1)
- **Source:** Existing channel (same as hermes_v2 uses)
- **Delivery:** `hermes_vps_health_check.py` sends findings summaries to this chat

**`CLOUD_REVIEW_API_KEY`** (Optional)
- **Purpose:** API key for RemoteTrigger cloud-review automation (weekly + monthly routines)
- **Value:** Anthropic API key or project-specific remote-trigger token
- **Source:** Created if using cloud-based review routines
- **Location:** `/root/.hermes_vps/.env` if needed; not used by health-check directly
- **Note:** Only needed if remote-trigger cloud agents are wired up; can be deferred

---

## Deployment Checklist

Before running `deploy.sh` or systemd units on the server:

- [ ] **PROMETHEUS_RETENTION_DAYS:** Decide value (default 30 OK)
- [ ] **GRAFANA_ADMIN_PASSWORD:** Generated or chosen; stored securely (password manager)
- [ ] **DATABASE_URL:** Copied from hermes_v2 `/opt/hermes_v2/.env` or schema docs
- [ ] **HERMES_LOG_DB_URL:** Copied from hermes_v2 (read-only cross-project access)
- [ ] **HERMES_VPS_LOG_DB_URL:** New DB/role created or credentials ready for creation
- [ ] **TELEGRAM_BOT_TOKEN:** Existing bot token (or new bot created)
- [ ] **TELEGRAM_CHAT_ID:** Verified to be correct channel (360294128)
- [ ] **CLOUD_REVIEW_API_KEY:** Obtained if using remote-trigger routines (optional for S2)
- [ ] **File permissions:** `/root/.hermes_vps/.env` mode 600, owner root

---

## Setting Up on Server

SSH to Hetzner and create the `.env` file:

```bash
ssh root@100.97.62.7  # via Tailscale

# Create file with template
cat > /root/.hermes_vps/.env << 'EOF'
PROMETHEUS_RETENTION_DAYS=30
GRAFANA_ADMIN_PASSWORD=<your_strong_password>
GRAFANA_DATASOURCES_UID=prometheus-default
DATABASE_URL=postgresql://hermes:hermes@localhost/hermes
HERMES_LOG_DB_URL=postgresql://hermes_v2:hermes_v2@localhost/findings_log
HERMES_VPS_LOG_DB_URL=postgresql://hermes_vps:hermes_vps@localhost/hermes_vps_log
TELEGRAM_BOT_TOKEN=<token_from_bot_father>
TELEGRAM_CHAT_ID=360294128
CLOUD_REVIEW_API_KEY=<if_needed>
EOF

# Secure permissions
chmod 600 /root/.hermes_vps/.env
ls -la /root/.hermes_vps/.env
```

---

## Validation

After creating `/root/.hermes_vps/.env`, verify systemd can read it:

```bash
systemctl status hermes-vps-healthcheck-weekly.service
# Should show: EnvironmentFile=/root/.hermes_vps/.env read successfully
```

Test database connectivity:

```bash
source /root/.hermes_vps/.env
psql "$DATABASE_URL" -c "SELECT 1 AS connection_test;"
psql "$HERMES_LOG_DB_URL" -c "SELECT COUNT(*) FROM findings_log LIMIT 1;"
```

Test Telegram notification:

```bash
cd /opt/hermes-vps
source /root/.hermes_vps/.env
./.venv/bin/python3 -c "
import os
import subprocess
token = os.environ.get('TELEGRAM_BOT_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')
msg = 'JR Hermes VPS: Credential setup verified on server'
subprocess.run(['curl', '-s', f'https://api.telegram.org/bot{token}/sendMessage',
  '-d', f'chat_id={chat_id}&text={msg}'])
"
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `EnvironmentFile not found` | Path typo or missing file | Verify `/root/.hermes_vps/.env` exists, not `/root/.env` |
| `Permission denied reading .env` | Wrong file mode | `chmod 600 /root/.hermes_vps/.env` |
| Database connection refused | Credentials wrong or DB down | `psql $DATABASE_URL` manually; check hermes_v2 `.env` |
| Telegram bot "401 Unauthorized" | Token expired or wrong | Get new token from BotFather; update `.env` |
| Prometheus not scraping | Config path wrong | Verify `deploy/prometheus.yml` path in `prometheus.service` |

---

## Post-Deployment Updates

If credentials need to be rotated (e.g., password reset, new bot token):

1. Update `/root/.hermes_vps/.env` on server
2. `systemctl daemon-reload` (if systemd cache needs refresh)
3. Restart affected service: `systemctl restart hermes-vps-*.service`
4. Do NOT commit new credentials to git
5. Do store in password manager for recovery

---

## Cross-Project Notes

- This `.env` is **independent** from hermes_v2's `.env` per `HERMES_PLATFORM_STANDARD.md`
- Exception: `HERMES_LOG_DB_URL` is copied from hermes_v2 to enable cross-project findings export
- If hermes_v2's database credentials change, update this `.env` (and all other projects')
- Health-check script reads **both** DB URLs to export findings to both repos

---

**Last Updated:** 2026-08-22 (S2)  
**Next Review:** After server deployment (S2.4, step 3)
