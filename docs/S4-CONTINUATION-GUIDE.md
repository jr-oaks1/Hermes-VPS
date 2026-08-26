# JR Hermes VPS — S4 Continuation Guide for S5

**Document Purpose:** Complete reference for S5 session continuation. All links, credentials references, monitoring points, and known issues consolidated here.

**Created:** 2026-08-22 (end of S4)  
**For:** S5 and beyond  
**Last Updated:** 2026-08-22

---

## Quick Status Summary

| Component | Status | Last Verified |
|-----------|--------|----------------|
| Server deployment | ✅ Live | S3 (2026-08-22) |
| Health-check pipeline | ✅ Working | S4 manual test (2026-08-22) |
| Git SSH credentials | ✅ Fixed | S4 (2026-08-22) |
| Findings export to GitHub | ✅ Working | S4 (2026-08-22) |
| Weekly cloud-review routine | ✅ Scheduled | S4 (2026-08-22) |
| Monthly cloud-review routine | ✅ Scheduled | S4 (2026-08-22) |
| Prometheus | ⏳ Deferred | — |
| Grafana | ⏳ Deferred | — |

---

## What's Happening Automatically (No Manual Work Needed)

### Weekly Cycle (Every Sunday)
1. **04:00 UTC (systemd timer)** → Health-check quick mode runs → exports 8-day findings to GitHub
2. **06:00 UTC (RemoteTrigger)** → Weekly findings triage cloud agent runs → reads export, opens PRs, writes report
3. **Telegram alert** → Sent for both health-check and (if configured) cloud agent

### Monthly Cycle (1st of month)
1. **04:15 UTC (systemd timer)** → Health-check deep mode runs → exports 35-day findings to GitHub
2. **06:00 UTC (RemoteTrigger)** → Monthly deep review cloud agent runs → analyzes patterns, opens PR, writes comprehensive report
3. **Telegram alert** → Sent for both audit and cloud agent

---

## Where Everything Lives

### On Server (Hetzner)
```
/opt/hermes-vps/                          # Project root
├── scripts/audit/hermes_vps_health_check.py  # Health-check script
├── deploy/                                # systemd units, configs
│   ├── hermes-vps-healthcheck-weekly.{service,timer}
│   ├── hermes-vps-audit-monthly.{service,timer}
│   └── nginx.conf
├── docs/findings_export/                 # Exports (git-tracked)
│   ├── latest.json                       # Current export
│   └── reviews/                          # Cloud agent reports (written here)
└── .env.template, CLOUD_REVIEW_SETUP.md, etc.

/root/.hermes_vps/.env                    # Credentials (mode 600, not in git)
```

### On GitHub
- Repository: `https://github.com/jr-oaks1/Hermes-VPS`
- Branch: `main`
- Findings exports: `docs/findings_export/latest.json`
- Cloud agent reports: `docs/findings_export/reviews/weekly-*.md`, `monthly-*.md`

### In Anthropic Cloud (RemoteTrigger)
- **Weekly routine:** https://claude.ai/code/routines/trig_01Ex2dEGsJg4YCNzWscRZfGw
- **Monthly routine:** https://claude.ai/code/routines/trig_016aXg9fzixrsnk7kgV7dUh4

---

## How to Verify Things Are Working

### Before First Automated Run (Now until Sun 2026-08-23 04:00 UTC)

```bash
# SSH into Hetzner
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7

# Check systemd timers are scheduled
systemctl list-timers | grep hermes-vps

# Check git remotes are SSH (not HTTPS)
cd /opt/hermes-vps && git remote -v
# Should show: git@github.com:jr-oaks1/Hermes-VPS.git

# Check credentials file exists
ls -la /root/.hermes_vps/.env

# Check cloud routines exist (in web UI)
# Visit: https://claude.ai/code/routines
# Search for: hermes-vps-weekly or hermes-vps-monthly
```

### After First Automated Run (Sun 2026-08-23 06:00 UTC)

```bash
# Check health-check ran
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "journalctl -u hermes-vps-healthcheck-weekly.service -n 30"

# Check findings were exported to GitHub
curl https://raw.githubusercontent.com/jr-oaks1/Hermes-VPS/main/docs/findings_export/latest.json | jq .

# Check weekly review cloud agent ran
# Visit: https://claude.ai/code/routines/trig_01Ex2dEGsJg4YCNzWscRZfGw
# Click "Runs" tab — should show one run from Sunday

# Check for PR opened
# Visit: https://github.com/jr-oaks1/Hermes-VPS/pulls
# Look for: [automated-review] label or recent PR

# Check report was written
# Visit: https://github.com/jr-oaks1/Hermes-VPS/blob/main/docs/findings_export/reviews/
# Should have: weekly-*.md file from Sunday
```

---

## Monitoring & Debugging

### Health-Check Logs
```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7 \
  "journalctl -u hermes-vps-healthcheck-weekly.service -n 100 --no-pager"

# Or for monthly deep audit:
journalctl -u hermes-vps-audit-monthly.service -n 100 --no-pager
```

### Cloud Agent Run Logs
1. Go to: https://claude.ai/code/routines/trig_01Ex2dEGsJg4YCNzWscRZfGw
2. Click "Runs" tab
3. Click on a run session ID
4. View full execution log

### GitHub Findings Export
- **Latest export:** `https://github.com/jr-oaks1/Hermes-VPS/blob/main/docs/findings_export/latest.json`
- **Cloud reports:** `https://github.com/jr-oaks1/Hermes-VPS/tree/main/docs/findings_export/reviews/`

---

## Known Issues & Workarounds

### 1. GitHub Branch Default (Minor)
**Issue:** Repository's default branch on GitHub is `master`, not `main`.  
**Impact:** If someone clones without `-b main`, they get 3 old commits instead of current code.  
**Workaround:** Use `git clone ... -b main` or change repo default branch in GitHub settings.  
**Status:** ⏳ Deferred (cosmetic, doesn't affect automation)

### 2. Cloud Agent Git Push (Potential)
**Issue:** RemoteTrigger cloud agents run in Anthropic's cloud sandbox with no persistent SSH keys. If routine tries `git push origin main` directly, it will fail with auth error.  
**Impact:** Cloud agent may fail to push reports or PRs.  
**Mitigation:** Routine prompt uses `gh pr create` (doesn't need SSH), and reports are pushed via GitHub API or stored in DB.  
**Status:** ⏳ Monitor Sunday's first run; if git push fails, update routine to use `gh pr create` exclusively.  
**Fix:** Edit routine prompt in https://claude.ai/code/routines/trig_01Ex2dEGsJg4YCNzWscRZfGw → Update → Change prompt to use `gh` CLI instead of `git push`.

### 3. Findings Export Window Timing
**Issue:** Health-check runs at 04:00 UTC, cloud agent reads export at 06:00 UTC. If health-check is delayed, agent may read stale data.  
**Impact:** Weekly review might analyze older-than-8-day findings.  
**Mitigation:** 2-hour buffer is usually sufficient. Monitor first run to confirm timing.  
**Status:** ⏳ Check systemd log timing vs. cloud agent run time.

---

## Pending Items (For S5 and Beyond)

### High Priority
1. **[S5] Monitor First Automated Run**
   - When: Sun 2026-08-23 (health-check 04:00 UTC, cloud review 06:00 UTC)
   - What: Verify health-check ran, export created, cloud agent executed, report written
   - Where: Check systemd logs + GitHub + RemoteTrigger dashboard
   - If fails: Diagnose from cloud agent run log + update prompt if needed

2. **[S5 or S6] Install Prometheus (Optional but Recommended)**
   - Why: Get CPU/mem/disk metrics in Grafana dashboards
   - How: See `deploy/setup_monitoring.sh` (incomplete; needs finishing)
   - Not critical for S5 — findings export works without metrics
   - Deferred because: Focus on cloud-review automation first

3. **[S5 or S6] Set Up Grafana (Depends on Prometheus)**
   - Credentials: `GRAFANA_ADMIN_PASSWORD=<redacted 2026-08-26>` (in `/root/.hermes_vps/.env`)
   - Config: `deploy/grafana/` folder (prometheus.yaml, dashboard configs)
   - Not critical for S5 — findings export and cloud review work without dashboards

### Important (Post-Automation Verification)
4. **Verify git credentials persist across multiple runs**
   - Check: After second automated run (Sep 1), both exports push successfully
   - If fails: May need to set up git credentials caching on server

5. **Verify Telegram alerts work consistently**
   - Check: Receive messages for both health-check and cloud agent execution
   - If fails: Check `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `/root/.hermes_vps/.env`

6. **Monitor cloud agent PR opening success rate**
   - Check: After first weekly run, PR should open on GitHub
   - If fails: Cloud agent may need auth fix (SSH key or `gh` CLI token)

### Optional (Nice-to-Have)
7. **Add RemoteTrigger failure alerts to Telegram**
   - Currently: Only health-check alerts go to Telegram
   - Future: Cloud agent failures could also send alerts
   - Status: ⏳ Document the alert routing if needed

8. **Create Grafana dashboard for findings trends**
   - What: Visualize finding severity over time (8-day / 35-day windows)
   - Requires: Prometheus + custom metrics (query findings_log table)
   - Status: ⏳ Depends on Prometheus setup

---

## Credentials Reference (For This Session)

**Note:** All credentials live in `/root/.hermes_vps/.env` (mode 600, not in git). Backup reference at `/root/.hermes_vps_credentials/CREDENTIALS.md` (also secure, root-only).

| Variable | Type | Used By | Notes |
|----------|------|---------|-------|
| `DATABASE_URL` | PostgreSQL | health-check (replication lag, ingestion) | hermes_v2 main DB |
| `HERMES_VPS_LOG_DB_URL` | PostgreSQL | health-check (findings write) | hermes_vps_log findings export |
| `HERMES_LOG_DB_URL` | PostgreSQL | health-check (cross-project read) | hermes_v2_log findings (read-only) |
| `TELEGRAM_BOT_TOKEN` | String | health-check (alerts) | @JRHermesVPSBot (Clevious_Hermes_Bot) |
| `TELEGRAM_CHAT_ID` | String | health-check (alerts) | Private group chat ID |
| `GRAFANA_ADMIN_PASSWORD` | String | (not yet deployed) | `<redacted 2026-08-26>` |
| `PROMETHEUS_RETENTION_DAYS` | Integer | (not yet deployed) | 90 days |

**Do NOT commit these to git.** `.gitignore` has `/root/` excluded already.

---

## Document References

- **Project guide:** `CLAUDE.md` (in repo root) — project scope, cross-project coupling
- **Server connectivity:** `docs/VPS_CONNECTIVITY_REFERENCE.md` — SSH, Tailscale, network info
- **Health-check script:** `scripts/audit/hermes_vps_health_check.py` (complete, working)
- **Cloud-review setup:** `docs/CLOUD_REVIEW_SETUP.md` — routine prompts, scheduling details
- **S1 handoff:** `docs/sessions/S1-HANDOFF.md` — project creation, what moved from hermes_v2
- **S2 handoff:** `docs/sessions/S2-HANDOFF.md` — GitHub setup, pre-deployment docs
- **S3 handoff:** `docs/sessions/S3-HANDOFF.md` — server deployment details, all 10 steps
- **S4 handoff:** `docs/sessions/S4-HANDOFF.md` — git SSH fix, RemoteTrigger setup
- **This guide:** `docs/S4-CONTINUATION-GUIDE.md` — everything you need to continue from S5

---

## Ground Rule: Interaction Numbering (Effective S4+)

**For all projects going forward:**

Every response starts with `#Interaction NN` (zero-padded two digits, counted from session start).

**Example:**
```
#Interaction 01
First response in a session.

#Interaction 02
Second response, separate turn.
```

**Why:**
- Provides transparent progress tracking
- Prevents context window saturation without notice
- Creates a clear marker for where hallucination zone begins (user can see interaction count and token budget)
- Applies globally to all projects (hermes_v2, cyclestation, PionexBots, JR Hermes VPS, etc.)

**Hallucination Zone Flag:**
Before stating anything not directly verified in THIS session (pulled from memory, inferred beyond checked state, unread file contents), flag it explicitly:

**Good:**
> Flag: The S3 handoff (not read this session) says Prometheus isn't installed yet. [Confirmed by git showing no prometheus.* files]

**Not OK:**
> Prometheus wasn't installed in S3. [← No flag, assumed from memory, risky]

---

## Quick Links (For Copypaste)

### Server Access
```bash
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7
```

### GitHub Repository
- Repo: https://github.com/jr-oaks1/Hermes-VPS
- Latest findings: https://raw.githubusercontent.com/jr-oaks1/Hermes-VPS/main/docs/findings_export/latest.json
- Cloud reports: https://github.com/jr-oaks1/Hermes-VPS/tree/main/docs/findings_export/reviews/

### Cloud Routines
- Weekly triage: https://claude.ai/code/routines/trig_01Ex2dEGsJg4YCNzWscRZfGw
- Monthly review: https://claude.ai/code/routines/trig_016aXg9fzixrsnk7kgV7dUh4

### Logs & Status
```bash
# Systemd timers
systemctl list-timers | grep hermes-vps

# Health-check logs (weekly)
journalctl -u hermes-vps-healthcheck-weekly.service -n 50

# Health-check logs (monthly)
journalctl -u hermes-vps-audit-monthly.service -n 50

# Credentials location
cat /root/.hermes_vps/.env
```

---

## Next Steps for S5

1. **Wait for Sunday 2026-08-23 04:00 UTC** → First automated health-check
2. **Monitor health-check execution** → Verify systemd logs show success
3. **Monitor cloud agent execution** → Check RemoteTrigger dashboard for run
4. **Verify GitHub export + PR** → Check repo for new files and PRs
5. **If all succeeds:** Celebrate automation working, plan Prometheus for S6
6. **If any failures:** Debug from cloud agent logs, update routine if needed

---

**Created by:** Claude Code (S4)  
**For:** S5 and beyond  
**Status:** Ready for seamless continuation
