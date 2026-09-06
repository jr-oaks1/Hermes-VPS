# S13 Handoff — JR Hermes VPS

**Session type:** Deep forensic audit of the Hetzner host + remediation, working
top-down by criticality. **Both P1 (High) items are fixed and live-verified.**
Everything still open is either user-gated (a reboot), cross-project, or low-value
P3 polish — see §4.

**Date:** 2026-09-05 (audit ran against host clock 2026-09-06 ~01:00–03:35 UTC).

---

## 1. What was fixed and verified live this session

### P1-1 · Host health monitoring was crying wolf for ~10 days — FIXED
`hermes-vps-healthcheck-weekly.service` + `hermes-vps-audit-monthly.service` had
been in a permanent systemd `failed` state (host `is-system-running` = **degraded**)
since ~2026-08-26. Root cause was **not** infra — the underlying checks were all
green. It was `hermes_vps_health_check.py` emitting ≥1 false CRITICAL every run,
forcing a non-zero exit:

| False finding | Fix (commit `a3cc7d2`) |
|---|---|
| `CRITICAL service.hermes_v2: inactive` | `SYSTEMD_SERVICES` `"hermes_v2"` → `"hermes-ingestor"` |
| `CRITICAL api.health: {'fred_data': 'disabled'}` | added `"disabled"` to `check_api_health`'s benign-state set |

Also removed `check_git_sync("/opt/hermes_v2")` and `export_hermes_v2_findings()`
entirely (both targeted the decommissioned `hermes_v2` repo).

**Verified:** manual `--mode deep` and a real `systemctl start` of the weekly unit
both → **all findings INFO, exit 0**. `systemctl is-system-running` = **running**,
`systemctl --failed` = **empty**. Weekly timer re-armed for Sun 04:00 UTC, monthly
for Oct 1 04:15 UTC.

### P1-2 · Both server git clones badly diverged + self-worsening — FIXED
`/opt/hermes-vps` and `/opt/hermes_v2` were each ahead 6 / behind 7 with dirty
trees. `_commit_and_push_export()` auto-committed + pushed every run; both pushes
were rejected (non-fast-forward), so each cycle added another unpushable commit.
The S11 daily-digest fix was stranded as an uncommitted on-disk edit.

- Both clones hard-reset to `origin/main` (guarded: only reset when every
  local-only commit is an export chore — verified true).
- `export_hermes_vps_findings()` now calls `_sync_repo_to_origin()` **before**
  writing (hard-resets to origin/main with the same guard), and
  `_commit_and_push_export()` rolls its own commit back on push failure. The
  clone can no longer diverge. Commit `a3cc7d2`.
- **Verified:** post-run `git status` clean, `ahead/behind 0/0`, findings export
  committed **and pushed** cleanly (`26e1dc1`, `fdc25e2`).

### Deliverables (workspace three-tier convention)
- **Artifact report:** <https://claude.ai/code/artifact/dbc35a1d-6cb7-4d9d-b15f-4976057186ae>
  — severity-ranked forensic report. Source committed at
  `docs/audits/S13-forensic-audit.html` (`7d79486`).
- **Handoff:** this file.
- **Memory:** `memory/s13_forensic_audit_p1_remediation.md` + `MEMORY.md` index;
  new cross-project `ground_rule_auto_mode_block_ping_first.md` propagated to all
  14 project memory dirs + workspace `CLAUDE.md`; `ground_rule_interaction_numbering.md`
  re-affirmed and propagated to the last 3 dirs that lacked a local copy.
- **Obsidian:** `ObsidianVault/Projects/JR Hermes VPS.md` — S13 section appended.

### Bonus (safe, self-contained)
- `hermes-vps-*.service` (all 3 units): dropped the fragile secondary
  `EnvironmentFile=…/opt/hermes_v2/.env`. **Verified live** that
  `/root/.hermes_vps/.env` alone yields working `DATABASE_URL`,
  `HERMES_VPS_LOG_DB_URL`, `HERMES_LOG_DB_URL`; `hermes_replication_status()` =
  `(1, 0)`. `After=` repointed `hermes_v2.service` → `hermes-ingestor.service`.
  Commits `a3cc7d2`, `a3cabe4`.
- `.gitignore`: added `logs/` + `*.bak-s*` (the runtime log dir was showing as an
  untracked-changes INFO on every deep run). `.bak-s12` deleted from the server.
- `CLAUDE.md`: corrected the monitoring-stack scope — **netdata is the live stack**
  (`127.0.0.1:19999`); Prometheus is installed-but-disabled+inactive, Grafana is
  **not installed**. In-repo `deploy/prometheus.*` / `deploy/grafana/` kept as
  future infra-as-code, flagged as not-live.
- `journalctl --vacuum-size=800M` — one-time, freed 543 MB (disk 71 % → 70 %).
  No journald.conf cap was added (that's a config change; deferred).

### Audit correction
Original audit finding "P2-3: `/etc/pg_backup.conf` structurally corrupted" was
**wrong**. The interleaved `ALERT_ENV_<DB>=…` lines are **valid per-DB alert
routing** — `pg_backup.sh:138` builds `ALERT_ENV_${db^^}` for each DB in
`DATABASES`. They're just poorly grouped visually. **No change made** — backups
run clean (Sep 5 02:42, "all databases OK — integrity verified", off-site synced).

---

## 2. Full live health snapshot (verified S13, all GREEN)

- **PostgreSQL** main (`5432`) + orch (`5435`): replication `streaming`, **0 bytes
  lag**, slot `contabo_replica` active; 13/100 conns; no blocked locks; no
  wraparound risk (xid age ~22 M); WAL 721 MB.
- **Backups:** `pg_backup.service` — all 4 DBs OK + integrity-verified + off-site
  synced to Contabo over 2 paths. S10 corruption crisis closed in practice.
- **nginx** `-t` clean & active; **TLS** `artek-studio.com` valid to Oct 19 (43 d);
  certbot timer healthy.
- **Ingestion:** `ohlcv_1m` 11/11 symbols current; `/health` ok, 11 agents healthy
  (fred_data intentionally disabled).
- **Security:** SSH key-only (`permitrootlogin without-password`, `passwordauth no`,
  `maxauthtries 3`); UFW active default-deny, 80/443 scoped to Cloudflare;
  WireGuard `jr-wg0` + Tailscale both up, recent handshakes; 0 failed SSH in 24 h;
  fail2ban sshd jail active.
- **Host:** CPU ~93 % idle, 0 steal / ~0 iowait; no OOM kills; no zombies; NTP
  synced; unattended-upgrades working. Uptime 24 d.
- **daily-digest:** fixed unit smoke-tested via systemd → "digest sent (36
  findings)" (down from 112 — the false-critical spam is gone). Timer armed 09:00.

---

## 3. Session side effects (disclosure)
- The audit + smoke tests fired several **Telegram messages** to `@JRHermesVPSBot`
  (2 false CRITICALs early on from the pre-fix script; then all-clear summaries;
  2 daily-digests today instead of 1).
- Several `chore: findings export` commits landed on `origin/main` from the
  server smoke-test runs (`26e1dc1`, `fdc25e2`). This git-churn on `main` is
  inherent to the findings-export-into-git design (see §4).
- Wrote/propagated a new cross-project ground rule (auto-mode-block → ping to
  disable auto mode; see workspace `CLAUDE.md` + every project's `memory/`).

---

## 4. Open items for S14 — NOT started (each needs a decision or is cross-project)

### 4a. Reboot required — USER-GATED (highest-impact remaining)
Running kernel `6.8.0-137`; `-138` **and** `-139` installed. `openssh-server`
auto-upgraded Sep 5 → old binary in memory. netdata raises a `post_update_reboot`
WARNING. This host runs Ingestor ingestion, is the **replication primary**, serves
`artek-studio.com` via nginx, and hosts 6+ other projects' timers — so a reboot is
a **scheduled maintenance window**, not an ad-hoc action. Recommended procedure:
1. Announce; pause `pg_backup.timer` if it'd overlap.
2. `systemctl stop hermes-ingestor` (clean ingestion stop).
3. `reboot`; on return verify: `hermes-ingestor` active, replication streaming
   (`pg_stat_replication` on Contabo side too), nginx serving, all timers armed,
   `:5432` bound to `127.0.0.1` + Tailscale IP.
4. Contabo (Clevious VPS) standby has its own post-reboot `:5432 missing 127.0.0.1`
   history — coordinate so both aren't down together.

### 4b. Disk cleanup (~7 GB; disk at 70 %) — mostly cross-project / needs go-ahead
| Item | Size | Owner / action |
|---|---|---|
| `temp_recovery_s23` DB (main cluster) | 2.6 GB | **Ask user/Ingestor** — only a Timescale bg-worker is "connected", no real users; leftover from S23 recovery. `DROP DATABASE` once confirmed unneeded. |
| `/opt/hermes-ingestor.backup-pre-s{14,16,25,27,27b,28,…}` | ~3.5 GB | **JR Hermes Ingestor's** — notify, don't delete from here. |
| `/opt/backups/crypto_signals_offsite.orphaned-s59` | 1.1 GB | **JR Basic Crypto Signals / backup job** territory — notify. |
| `/opt/backups/cyclestation/manual/` (empty) | — | stray; whoever added it should remove. |

### 4c. `/opt/hermes_v2` decommission — CROSS-PROJECT, multi-service
`/opt/hermes_v2` is still load-bearing for these **live systemd units** (not this
project's): `bronze-audit-daily`, `funnel_scoring`, `server_health_audit`,
`walk_forward_monitor` (all run hermes_v2 scripts w/ its `.env`), and
`prometheus.service` (`--config.file=/opt/hermes_v2/deploy/prometheus.yml`, but
prometheus is disabled). Plus the `hermes_v2.service` + `.pre-phase2*` unit files
themselves. This needs a dedicated hermes_v2-teardown effort coordinating with
whoever owns those jobs (likely Ingestor / JR_VPS_Orchestrators). This project's
own references are now clean.

### 4d. P3 polish (low urgency)
- Persistent journald cap: add `/etc/systemd/journald.conf.d/` drop-in with
  `SystemMaxUse=800M` (config change → stage + smoke-test).
- `/swapfile2` (8 GB, added Jun 19) on top of `/swapfile` (2 GB) — 10 GB swap,
  105 MB used, on a 75 GB disk. Ask user whether `/swapfile2` is still wanted.
- Outdated: cloudflared `2026.7.3`→`.8.3` (WARNs daily), tailscale `1.102.2`→`.3`,
  timescaledb `2.29.1`→`.2`, 28 apt pkgs (0 security-flagged). Bundle with 4a.
- fail2ban: only `sshd` jail, `Total banned: 0` ever despite public `:52222`; no
  `recidive` jail though UFW comments imply layered defense.
- `contabo-findings-sync` duplicate `[FINDING]` Telegram messages (S12 note) —
  **not reproduced** this session; "no new rows since id=135" every 15 min.
- The findings-export-into-git design churns `chore:` commits onto `main` and
  forces rebases on local pushes. Consider moving the export to a dedicated
  branch, an artifact store, or dropping it (the DB is already the source of
  truth). Self-healing fix is in place, but the design is still noisy.

---

## Quick resume for whoever opens S14
P1 is done — the host's own monitoring works again and the deploy clones can't
re-diverge. Start S14 by picking one of: **4a (reboot, needs your window)**,
**4c (hermes_v2 teardown, cross-project)**, or **4b (`temp_recovery_s23` drop,
needs a yes)**. 4d is a grab-bag of low-priority polish. Nothing is on fire.
