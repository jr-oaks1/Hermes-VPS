# JR Hermes VPS — Session 1 Handoff

**Date:** 2026-08-22  
**Session:** S1 (project genesis — VPS-infra split from hermes_v2)  
**Status:** ✅ Local scaffolding complete; server-side deployment pending

---

## What This Session Did

Created a brand-new project to own everything about the Hetzner host
(`hermes`, `46.225.14.26` / `100.97.62.7`) as infrastructure independent of
applications. Split out of `hermes_v2` because VPS-level health-check tooling
had been built directly inside the app's repo (S178/S179) simply because this
project didn't yet exist.

### 1. Scope Defined

**Moves to this project:**
- systemd units: `hermes-vps-healthcheck-weekly.*`, `hermes-vps-audit-monthly.*`
- host-level health check: `scripts/audit/hermes_vps_health_check.py`
- monitoring: `deploy/prometheus.service`, `deploy/prometheus.yml`, `deploy/prometheus_rules.yml`
- Grafana: `deploy/grafana/` (full provisioning directory)
- nginx config: `deploy/nginx.conf` (single host-wide file; hermes_v2's app-specific
  `location` blocks stay inline)
- UFW snapshots: `deploy/firewall/` (4 snapshot files)
- install script: `deploy/setup_monitoring.sh`
- reference doc: `docs/VPS_CONNECTIVITY_REFERENCE.md` (canonical copy, moved from
  hermes_v2; workspace-root and server copies kept in sync)

**Stays in hermes_v2** (app-level, unchanged by this split):
- `hermes_v2.service`, `hermes_v2_backup.service/.timer`, `hermes_v2_compute.service`
- `market-watcher.*`, `walk_forward_monitor.*`, `funnel_scoring.*`,
  `bronze-audit-*`, `server_health_audit.*`
- `deploy.sh` (entirely `/opt/hermes_v2`-anchored app deploy)
- `deploy/replication_status_function.sql` (postgres function, granted to hermes_v2
  role, stays; VPS health check calls it remotely)
- app-level findings/export: `docs/findings_export/`, existing `RemoteTrigger`
  cloud-review routines

### 2. Code Changes

**`hermes_vps_health_check.py`** — refactored for split exports:
- `check_git_sync(repo_dir)` now accepts a parameter (called twice in deep mode:
  `/opt/hermes_v2` and `/opt/hermes-vps`) with per-repo labeling
- Split exports: `export_hermes_v2_findings()` continues pointing at hermes_v2
  repo for `hermes_v2_log` (existing cloud-review routines unchanged);
  `export_hermes_vps_findings()` exports to this project's own repo for
  `hermes_vps_log` (new cloud-review routine forthcoming)
- Added helper `_fetch_findings_window()` and `_commit_and_push_export()` to reduce duplication

**systemd units** — all paths repointed to `/opt/hermes-vps`:
- `WorkingDirectory=/opt/hermes-vps`
- `ExecStart=/opt/hermes-vps/.venv/bin/python3 /opt/hermes-vps/scripts/audit/...`
- Logs to `/opt/hermes-vps/logs/...`
- **Two EnvironmentFile entries** (new):
  - Primary: `/root/.hermes_vps/.env` (this project's own credentials)
  - Secondary: `/opt/hermes_v2/.env` (read-only, only for `HERMES_LOG_DB_URL`
    — needed for hermes_v2_log findings export, avoids duplicating that credential
    in this project's .env per `HERMES_PLATFORM_STANDARD.md` self-containment)

**`prometheus.service` + `prometheus.yml`:**
- Config file path: `/opt/hermes-vps/deploy/prometheus.yml`
- Rule file path: `/opt/hermes-vps/deploy/prometheus_rules.yml`

**`setup_monitoring.sh`:**
- Variable `HERMES_DIR` renamed to `VPS_DIR` for clarity
- Uses `/root/.hermes_vps/.env` instead of `/opt/hermes_v2/.env`
- nginx symlink target updated to `/opt/hermes-vps/deploy/nginx.conf`
- **Note:** this is a one-time install script, not auto-run; manual review needed
  before running on the server during deployment (paths, user assumptions, etc.)

**`nginx.conf`:**
- Moved whole to this project (host-wide service, VPS-owned)
- hermes_v2's two app-specific `location` blocks stay inline (`root /opt/hermes_v2/public`)
- nginx symlink on server will change from `/etc/nginx/sites-enabled/hermes_v2`
  to `/etc/nginx/sites-enabled/hermes-vps`

### 3. Local Scaffolding

- New git repo initialized at `C:\Users\jr250\OneDrive\Personales\AI Projects\JR Hermes VPS`
- Created: `CLAUDE.md`, `README.md`, `.gitignore`, `docs/VPS_CONNECTIVITY_REFERENCE.md`
- First commit (`37e851e`): all files, ready for deployment

**NOT YET DONE** (scheduled for next session if proceeding):
- Actual server-side `/opt/hermes-vps` checkout + configuration
- systemd unit redeployment + test
- nginx cutover
- Prometheus/Grafana path repoint
- New cloud-review routine setup for hermes_vps_log findings
- DNS/GitHub setup (remote URL, etc.)

### 4. Parallel Work: hermes_v2 Cleanup

Removed moved files from hermes_v2, now at commit `d42e994` (S180):
- All 18 files that moved
- Cleaned `.env.template` (removed GRAFANA_ADMIN_PASSWORD comment, now in JR
  Hermes VPS .env)

hermes_v2 is now conceptually "JR Hermes Ingestor" (ingestion + trading logic).
The rename is a labeling change, not a code change — same repo, same folder.

---

## Design Decisions Confirmed with User

1. **Findings export split:** separate cloud-review routine for this project (hermes_vps_log
   export), rather than continuing to piggyback hermes_v2's existing routines
2. **nginx.conf ownership:** whole file to this project (VPS-owned), app-specific
   blocks inline (no split)
3. **Server install path:** `/opt/hermes-vps` (parallel to `/opt/hermes_v2`)
4. **Environment file strategy:** two `EnvironmentFile=` entries in systemd units,
   per HERMES_PLATFORM_STANDARD.md self-containment

---

## Current Local State (Verified 2026-08-22, This Session)

| Component | Status |
|---|---|
| Git repo initialized | ✅ `https://github.com/jr-oaks1/Hermes-VPS` (DNS not yet wired) |
| Files staged/committed | ✅ `37e851e` S1 initial commit, 21 files |
| hermes_vps_health_check.py refactored | ✅ Split exports + dual git sync working locally |
| systemd units updated | ✅ Paths repointed to `/opt/hermes-vps` |
| nginx.conf moved | ✅ In `deploy/`, ready for symlink |
| Prometheus config updated | ✅ Paths repointed |
| setup_monitoring.sh updated | ✅ Variable rename, path updates |
| CLAUDE.md (new project) | ✅ Scope, goals, session tracking |
| .env.template (hermes_v2) | ✅ GRAFANA_ADMIN_PASSWORD cleaned up |
| VPS_CONNECTIVITY_REFERENCE.md | ✅ Moved, will become canonical for this project |

---

## Server-Side Deployment (Next Session)

If proceeding, the sequence (from plan):

1. Create GitHub remote: `jr-oaks1/Hermes-VPS`, push local repo
2. SSH to Hetzner: `mkdir /opt/hermes-vps`, `git clone ...`
3. Copy systemd units to `/etc/systemd/system/`, `daemon-reload`
4. Stop/disable old units (still pointing at `/opt/hermes_v2`)
5. Enable + start new units; live-test both modes
6. nginx cutover (validate, back up old config, cut over, reload)
7. Prometheus/Grafana path repoint + restart
8. Remove migrated files from `/opt/hermes_v2` (after hermes_v2 S180 commit is
   pulled on server)
9. New cloud-review routine for hermes_vps_log (via `RemoteTrigger`)

**Deployment carries live-service risk** (nginx cutover, systemd unit swaps, path
changes). See rollback pointers below.

---

## Rollback

- Local: `git revert 37e851e` in this repo
- Local hermes_v2: `git revert d42e994` (if needed before server deploy)
- Server (if deployed):
  - Systemd: old `*.bak-s1` files kept, restore with `cp ... /etc/systemd/system/`
  - nginx: old config backed up before cutover, `reload` with backup restores
  - Paths: individual `git reset` at `/opt/hermes-vps` or `/opt/hermes_v2`

---

## Pending Items

1. **GitHub remote + DNS:** Create `jr-oaks1/Hermes-VPS` repo, push local code,
   verify push credentials on server
2. **Server-side deployment:** Full sequence above (10 steps), with live testing
   after systemd + nginx cutovers
3. **Cloud-review routine:** New `RemoteTrigger` for hermes_vps_log findings
   (weekly triage + monthly deep, same pattern as hermes_v2's existing routines)
4. **GRAFANA_ADMIN_PASSWORD migration:** Ensure it's in `/root/.hermes_vps/.env`
   before `setup_monitoring.sh` runs (not stored in git; manually manage on server
   or via vault)
5. **Cross-project doc sync:** Keep workspace-root + Hetzner `/opt/VPS_CONNECTIVITY_REFERENCE.md`
   in sync with this project's copy (ongoing maintenance)

---

## Commits

- **JR Hermes VPS S1:** `37e851e` — Initial commit, all files, scaffolding complete
- **hermes_v2 S180:** `d42e994` — Remove VPS-infra split to new project

---

## Session Length & Complexity

This session was a structural split involving:
- 21 files moved (local copy + git add)
- 18 files removed from hermes_v2 (git rm)
- 3 files refactored (hermes_vps_health_check.py, systemd units, scripts)
- 5 doc updates (CLAUDE.md, README, .env.template, .gitignore, VPS_CONNECTIVITY_REFERENCE.md)
- Two separate git repos (new project + cleanup in existing)

**Local work complete.** Server-side deployment deferred (highest risk, best done
with explicit user confirmation and thorough pre-deployment review).
