# JR Hermes VPS S2 — Server Deployment Guide

**Date:** 2026-08-22  
**Risk Level:** HIGH (nginx cutover, systemd unit swaps, path changes)  
**Estimated Duration:** 30-45 minutes  
**Rollback:** Fully reversible; see rollback section at end  

---

## Pre-Flight

**Before you start:**

1. ✅ All local commits pushed to GitHub (verify: `git log` shows 6+ commits)
2. ✅ `.env.template` checked in (local reference; don't commit actual secrets)
3. ✅ You have SSH access to Hetzner (Tailscale 100.97.62.7 or public 46.225.14.26:52222)
4. ✅ You have sudo/root access on the server
5. ✅ A backup of `/opt/hermes_v2` exists (if not, hermes_v2 can recover from git)
6. ✅ You have the credentials ready (Grafana password, Telegram token, DB URLs)

**If any of the above is missing, STOP and set it up first.**

---

## Step 1: Create `/opt/hermes-vps` & Clone Repo

**On the server:**

```bash
ssh root@100.97.62.7  # via Tailscale
# or: ssh -i ~/.ssh/hermes_ed25519 -p 52222 root@46.225.14.26

# Create directory
mkdir -p /opt/hermes-vps
cd /opt/hermes-vps

# Clone repo
git clone https://github.com/jr-oaks1/Hermes-VPS.git .

# Verify (should see .git + all files)
ls -la | head -20
git log --oneline | head -5
```

**Expected output:**
```
Cloning into '.'...
remote: Enumerating objects: ...
...
86f3634 S2: Add pre-deployment checklist script
b60b681 S2: Add cloud-review prompt files (weekly + monthly)
546da85 S2: Add cloud-review routine setup guide
969398c S2: Add .env.template + credential setup guide
65e73d0 S1: Add session summary & continuity guide for next session
```

**If clone fails:**
- Check network/firewall (GitHub public access)
- Verify SSH key available on server (if using SSH; this uses HTTPS)
- Check git version: `git --version`

**✅ Step 1 Complete:** `/opt/hermes-vps` cloned and ready

---

## Step 2: Create Python Virtual Environment

```bash
cd /opt/hermes-vps

# Create .venv
python3 -m venv .venv

# Activate (optional for this step)
source .venv/bin/activate

# Install dependencies
./.venv/bin/pip install -q -r requirements.txt

# Verify
./.venv/bin/python3 --version
./.venv/bin/pip list | grep -E "requests|psycopg2|flask" | head -5
```

**Expected output:**
```
Python 3.x.x
requests ...
psycopg2-binary ...
```

**If pip install fails:**
- Check internet/PyPI access
- Check `requirements.txt` exists
- Try: `./.venv/bin/pip install --upgrade pip` first

**✅ Step 2 Complete:** Python environment ready

---

## Step 3: Set Up `/root/.hermes_vps/.env`

**Create the file with your secrets:**

```bash
cat > /root/.hermes_vps/.env << 'EOF'
# Hermes VPS Infrastructure Environment
# Created 2026-08-22, S2 deployment
# File mode: 600 (root-only read)

# Prometheus
PROMETHEUS_RETENTION_DAYS=30

# Grafana
GRAFANA_ADMIN_PASSWORD=<your_strong_password_here>
GRAFANA_DATASOURCES_UID=prometheus-default

# Databases
DATABASE_URL=postgresql://hermes:hermes@localhost/hermes
HERMES_LOG_DB_URL=postgresql://hermes_v2:hermes_v2@localhost/findings_log
HERMES_VPS_LOG_DB_URL=postgresql://hermes_vps:hermes_vps@localhost/hermes_vps_log

# Telegram Bot
TELEGRAM_BOT_TOKEN=<your_bot_token_here>
TELEGRAM_CHAT_ID=360294128

# Cloud-Review API (if using RemoteTrigger)
CLOUD_REVIEW_API_KEY=<if_needed>
EOF

# Set permissions
chmod 600 /root/.hermes_vps/.env

# Verify
ls -la /root/.hermes_vps/.env
```

**Replace placeholders:**
- `<your_strong_password_here>` — min 12 chars, mixed case + numbers + special
- `<your_bot_token_here>` — from Telegram BotFather (existing `@JRHermesVPSBot` token)
- `<if_needed>` — optional, skip if not using RemoteTrigger yet

**Verify database URLs are correct:**
```bash
source /root/.hermes_vps/.env
psql "$DATABASE_URL" -c "SELECT 1 AS ok;" 
# Should output: ok | 1
```

**✅ Step 3 Complete:** Credentials in place, mode 600

---

## Step 4: Copy Systemd Units to `/etc/systemd/system/`

**Backup old units (if they exist):**

```bash
# Check if VPS units exist from old hermes_v2 deploy
ls /etc/systemd/system/hermes-vps-* 2>/dev/null || echo "No old VPS units found"

# If found, back them up
for f in /etc/systemd/system/hermes-vps-*; do
    [[ -f "$f" ]] && cp "$f" "$f.bak-s1"
done

# Verify backups created (optional)
ls -la /etc/systemd/system/*.bak-s1 2>/dev/null || echo "No backups needed"
```

**Copy new units:**

```bash
cp /opt/hermes-vps/deploy/hermes-vps-*.service /etc/systemd/system/
cp /opt/hermes-vps/deploy/hermes-vps-*.timer /etc/systemd/system/

# Reload systemd to recognize new units
systemctl daemon-reload

# Verify units registered
systemctl list-unit-files | grep hermes-vps
```

**Expected output:**
```
hermes-vps-audit-monthly.service       disabled    disabled
hermes-vps-audit-monthly.timer         disabled    disabled
hermes-vps-healthcheck-weekly.service  disabled    disabled
hermes-vps-healthcheck-weekly.timer    disabled    disabled
```

**✅ Step 4 Complete:** Systemd units installed

---

## Step 5: Disable Old Systemd Units (if exist)

```bash
# Stop old units (if they exist from S1 cleanup)
for service in hermes-vps-healthcheck-weekly.timer hermes-vps-audit-monthly.timer; do
    systemctl stop "$service" 2>/dev/null || true
    systemctl disable "$service" 2>/dev/null || true
done

# Verify (should be stopped/disabled)
systemctl status hermes-vps-*.timer
```

**Expected output:**
```
● hermes-vps-healthcheck-weekly.timer - Weekly hermes-vps health check
   Loaded: loaded (...; disabled; ...)
   Active: inactive (dead)
```

**✅ Step 5 Complete:** Old units stopped

---

## Step 6: Enable + Start New Systemd Units

```bash
# Enable timers (will run on schedule)
systemctl enable hermes-vps-healthcheck-weekly.timer
systemctl enable hermes-vps-audit-monthly.timer

# Start timers
systemctl start hermes-vps-healthcheck-weekly.timer
systemctl start hermes-vps-audit-monthly.timer

# Verify status
systemctl status hermes-vps-*.timer
```

**Expected output:**
```
● hermes-vps-healthcheck-weekly.timer - Weekly hermes-vps health check
   Loaded: loaded (...; enabled; ...)
   Active: active (waiting)
   Trigger: Sun 2026-08-24 04:00:00 UTC; 2 days left
```

**Check next scheduled runs:**
```bash
systemctl list-timers --all | grep hermes-vps
```

**✅ Step 6 Complete:** Timers enabled and active

---

## Step 7: Manual Test of Health-Check Script

**Run the quick mode (tests all systems):**

```bash
cd /opt/hermes-vps
source /root/.hermes_vps/.env

# Run health check (quick mode)
./.venv/bin/python3 scripts/audit/hermes_vps_health_check.py --mode quick

# Output should show:
# - findings_log database checks
# - git commits/exports
# - Telegram notification status (if bot configured)
```

**Verify export was created:**

```bash
# Check findings export
ls -la docs/findings_export/
cat docs/findings_export/latest.json | jq . | head -20

# Verify git push happened
cd /opt/hermes-vps
git log --oneline -1
# Should show a "chore: findings export" commit
```

**If script fails:**
- Check Python syntax: `./.venv/bin/python3 -m py_compile scripts/audit/hermes_vps_health_check.py`
- Check database connectivity: `psql "$DATABASE_URL" -c "SELECT 1;"`
- Check Telegram token: verify `TELEGRAM_BOT_TOKEN` in `/root/.hermes_vps/.env`

**✅ Step 7 Complete:** Health-check tested, exports working

---

## Step 8: nginx Configuration Cutover

**⚠️ CRITICAL: This step affects active service. Have rollback plan ready.**

**Backup current config:**

```bash
cp /etc/nginx/sites-enabled/hermes_v2 /etc/nginx/sites-enabled/hermes_v2.bak-s1
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak-s1

# Verify backups exist
ls -la /etc/nginx/sites-enabled/hermes_v2.bak-s1
```

**Create new symlink:**

```bash
# Remove old symlink (if it exists)
[[ -L /etc/nginx/sites-enabled/hermes_v2 ]] && rm /etc/nginx/sites-enabled/hermes_v2

# Create new symlink to VPS project config
ln -s /opt/hermes-vps/deploy/nginx.conf /etc/nginx/sites-enabled/hermes-vps

# Verify symlink
ls -la /etc/nginx/sites-enabled/hermes-vps
```

**Validate nginx configuration:**

```bash
nginx -t
# Expected output: "syntax is ok" and "test is successful"
```

**If nginx -t fails:**
- Check error message
- Compare with backup: `diff /etc/nginx/nginx.conf.bak-s1 /etc/nginx/nginx.conf`
- Rollback: `cp /etc/nginx/sites-enabled/hermes_v2.bak-s1 /etc/nginx/sites-enabled/hermes_v2`

**Reload nginx (LIVE TRAFFIC CHANGE):**

```bash
systemctl reload nginx

# Verify
systemctl status nginx
```

**Test endpoints:**

```bash
# Test app endpoint (adjust domain as needed)
curl -s https://hermes.localdomain/ | head -20

# Test Prometheus (if exposed)
curl -s http://localhost:9090/api/v1/targets | jq . | head
```

**If connectivity breaks:**
- Immediately rollback: `cp /etc/nginx/sites-enabled/hermes_v2.bak-s1 /etc/nginx/sites-enabled/hermes_v2 && systemctl reload nginx`
- Investigate: `journalctl -u nginx -n 50`

**✅ Step 8 Complete:** nginx serving via new config

---

## Step 9: Prometheus + Grafana Path Repoint

**Update Prometheus service to use new path:**

```bash
# Check current Prometheus service
systemctl cat prometheus.service | grep "prometheus.yml"

# If service exists, update it to point to new VPS project:
# Edit: /etc/systemd/system/prometheus.service
# Change: ExecStart=... --config.file=/opt/hermes-vps/deploy/prometheus.yml

# For now, if Prometheus is running, verify it's accessible:
systemctl status prometheus
curl http://localhost:9090/ | grep -i prometheus

# If Prometheus needs restart:
systemctl daemon-reload
systemctl restart prometheus
```

**Verify Prometheus config:**

```bash
cat /opt/hermes-vps/deploy/prometheus.yml | head -20
# Should show: scrape configs pointing to localhost targets
```

**Verify Grafana datasource:**

```bash
# Access Grafana web UI: https://hermes.localdomain:3000 (or localhost:3000 via SSH tunnel)
# Navigate to: Configuration → Data Sources
# Verify "Prometheus" datasource points to http://localhost:9090

# Command-line check (if Grafana API available):
curl -s http://localhost:3000/api/datasources | jq '.[] | {name: .name, url: .url}'
```

**✅ Step 9 Complete:** Prometheus + Grafana repointed

---

## Step 10: Verify Cross-Project Health

**Check hermes_v2 still running:**

```bash
systemctl status hermes_v2.service

# Check logs for any errors
journalctl -u hermes_v2.service -n 20
```

**Verify replication status call (cross-project):**

```bash
cd /opt/hermes-vps
source /root/.hermes_vps/.env

# Call hermes_v2's replication_status() function
psql "$DATABASE_URL" -c "SELECT * FROM hermes_replication_status();" 

# Expected output: replication status details
```

**Check both projects' systemd logs:**

```bash
# VPS health-check (should have run manual test in Step 7)
journalctl -u hermes-vps-healthcheck-weekly.service -n 20

# hermes_v2 app
journalctl -u hermes_v2.service -n 20

# Look for errors (marked with "error", "ERR", "FATAL")
```

**Verify web endpoints:**

```bash
# App endpoint
curl -s https://hermes.localdomain/ | grep -i "hermes\|app" | head

# Prometheus metrics
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].job' | sort -u

# Grafana dashboards
curl -s http://localhost:3000/api/search | jq '.[].title' | head
```

**✅ Step 10 Complete:** Both projects healthy

---

## Step 11 (Optional): Pull hermes_v2 S180 Cleanup

**Update hermes_v2 to remove duplicate VPS-infra files:**

```bash
cd /opt/hermes_v2
git pull origin main

# Verify moved files are gone
ls deploy/hermes-vps-* 2>/dev/null && echo "ERROR: VPS files still present" || echo "OK: VPS files removed"

# Verify S180 commit is present
git log --oneline | grep -E "S180|VPS|split" | head -3
```

**✅ Step 11 Complete:** hermes_v2 cleaned (optional)

---

## Rollback Instructions

If anything goes wrong at any step:

### Before nginx cutover (Steps 1-7):
```bash
# Easy rollback: systemd units are new, can be disabled
systemctl disable hermes-vps-*.timer
systemctl stop hermes-vps-*.timer

# Remove units
rm /etc/systemd/system/hermes-vps-*.service
rm /etc/systemd/system/hermes-vps-*.timer

# Reload systemd
systemctl daemon-reload

# Check if needed: hermes_v2 still untouched, can continue debugging
```

### After nginx cutover (Steps 8-10):
```bash
# CRITICAL: Restore nginx immediately
cp /etc/nginx/sites-enabled/hermes_v2.bak-s1 /etc/nginx/sites-enabled/hermes_v2
rm /etc/nginx/sites-enabled/hermes-vps

# Reload nginx
nginx -t && systemctl reload nginx

# Verify endpoints restored
curl https://hermes.localdomain/

# Investigate failure:
journalctl -u nginx -n 50 | grep error
```

### For Prometheus/Grafana rollback:
```bash
# If Prometheus service was changed, restore:
# (Command depends on how it was modified; check /etc/systemd/system/prometheus.service backup)

# Restart Prometheus with original config
systemctl restart prometheus
```

### Database rollback:
```bash
# If HERMES_VPS_LOG_DB_URL database was created, it's safe to leave
# (No production data loss; health-check can recreate)

# If credentials need reset, update /root/.hermes_vps/.env:
nano /root/.hermes_vps/.env
# Edit values as needed
chmod 600 /root/.hermes_vps/.env

# Restart services to pick up new credentials
systemctl restart hermes-vps-*.service
```

---

## Post-Deployment Verification

After all steps complete:

```bash
# 1. Check all services active
systemctl status hermes-vps-*.timer hermes_v2.service

# 2. Verify timers will run (check next scheduled time)
systemctl list-timers --all | grep hermes

# 3. Check git repos updated
git -C /opt/hermes-vps log --oneline -1
git -C /opt/hermes_v2 log --oneline -1

# 4. Test health-check export path one more time
cd /opt/hermes-vps
source /root/.hermes_vps/.env
./.venv/bin/python3 scripts/audit/hermes_vps_health_check.py --mode quick

# 5. Verify Telegram notification received (if bot configured)
# Check your Telegram chat for "Health Check" message

echo "✅ Server deployment complete"
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `git clone` fails | Check GitHub repo is public; check network; try: `git clone --depth 1 ...` |
| `pip install` fails | Check PyPI access; upgrade pip: `./.venv/bin/pip install --upgrade pip` |
| `.env` file not readable by systemd | Check permissions: `chmod 600 /root/.hermes_vps/.env` |
| Health-check script fails | Check DB connectivity: `psql $DATABASE_URL -c "SELECT 1;"` |
| nginx fails to reload | Check syntax: `nginx -t`; restore backup if needed |
| Hermes_v2 app not responding | Check: `systemctl status hermes_v2.service`; `journalctl -u hermes_v2.service` |
| Prometheus not scraping targets | Check path: `/opt/hermes-vps/deploy/prometheus.yml` exists; restart: `systemctl restart prometheus` |

---

## Timeline

Expected duration: **30-45 minutes**

- Step 1-2 (clone + env): ~5 min
- Step 3 (credentials): ~5 min
- Step 4-5 (systemd): ~5 min
- Step 6 (enable timers): ~2 min
- Step 7 (test health-check): ~5-10 min
- **Step 8 (nginx cutover): ~5-10 min** ⚠️ CRITICAL
- Step 9-10 (verify): ~5 min
- Total: 30-45 min

**Recommended:** Do steps 1-7 first, test thoroughly, then proceed to Step 8 (nginx cutover) once confident.

---

## Completion Checklist

After finishing all steps:

- [ ] `/opt/hermes-vps` cloned and ready
- [ ] Python virtual environment created
- [ ] `/root/.hermes_vps/.env` in place (mode 600)
- [ ] Systemd units installed + enabled
- [ ] Health-check runs successfully
- [ ] nginx serving via new config (hermes_v2 app still accessible)
- [ ] Prometheus + Grafana repointed
- [ ] hermes_v2 app still running (cross-project verified)
- [ ] Both systemd logs clean (no errors)
- [ ] Web endpoints responding

---

**Deployment Date:** 2026-08-22  
**By:** Claude Code S2  
**Next Steps:** Set up RemoteTrigger cloud-review routines (see docs/CLOUD_REVIEW_SETUP.md)

