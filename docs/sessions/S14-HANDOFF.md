# S14 Handoff — JR Hermes VPS

**Session type:** Close out all S13 open pendings (4a–4d) with explicit
user go-ahead on every gated item. All four items actioned; host rebooted,
verified healthy end-to-end.

**Date:** 2026-09-06.

---

## Quick Resume for whoever opens S15

Everything in this project's own control from S13 is closed. What's left is
**cross-project only**:

1. **`walk_forward_monitor.service` DB grant** (§1, §4) — `hermes_v2` role
   lost SELECT on `sentiment` table (now owned by `hermes_ingestor`). This is
   why the host still shows `degraded`. Notice already sent to JR Hermes
   Ingestor (`docs/CROSS-PROJECT-NOTICE-2026-09-06-...` in that repo, on its
   `s27-s28-audit-fixes` branch) — check there for a reply before re-raising.
2. **`/opt/hermes_v2` teardown** — unchanged blocker list from S13 (§4c).
3. **Disk items owned elsewhere** — Ingestor's `backup-pre-s*` dirs (~1.76 GB),
   Basic Crypto Signals' orphaned offsite copy (1.1 GB) — notices sent, no
   action expected from this project.
4. **`/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump`** (1.2 GB on
   the Hetzner host) — safety copy of the dropped DB, fine to delete after a
   grace period (a few weeks from 2026-09-06) once confident it's not needed.

Nothing is on fire. Live state as of session close (verified 2026-09-06
04:25 UTC, ~14 min post-reboot): `is-system-running` = `degraded` (the one
`walk_forward_monitor.service` failure only), disk 58% (31 GB free), uptime
14 min post-reboot, kernel `6.8.0-139-generic`.

---

## 1. What was done and verified live this session

### 4b · Dropped `temp_recovery_s23` — 2.6 GB reclaimed
Confirmed only a TimescaleDB background worker was attached (no real user
sessions). Took a full `pg_dump -Fc` safety copy first — **1.2 GB, saved to
`/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump` on the Hetzner
host** — then `DROP DATABASE`. Verified: DB gone from `pg_database`, system
`running`, replication still streaming with 0 practical lag afterward.
Disk went 70% → 57% at that point (larger than the 2.6 GB DB size alone,
because dropping also freed associated WAL/temp space building up from the
S13 git-loop era).

### 4b (extra, user-approved) · Removed unused `/swapfile2` — 8 GB reclaimed
`/swapfile2` (8 GB, added 2026-06-19) had 0 B in use against 165 MB actually
used on the primary `/swapfile` (2 GB). `swapoff` → removed the `/etc/fstab`
line → deleted the file. Verified `swapon --show` now lists only `/swapfile`,
and that it **survived the reboot** correctly (still 2G, 0B used post-reboot).

### 4d · Persistent journald cap
Added `/etc/systemd/journald.conf.d/size-cap.conf` (`SystemMaxUse=800M`) —
journald was at 778.6 MB with no cap. Restarted `systemd-journald` cleanly,
verified again post-reboot (`780.3M`, cap in effect).

### 4d · fail2ban `recidive` jail added
S13 flagged fail2ban running only the `sshd` jail despite UFW comments
implying layered defense. Added `/etc/fail2ban/jail.d/98-jr-hermes-vps-recidive.conf`
(re-bans repeat offenders across jails, 7-day bantime) as a **separate file**
rather than editing `99-jr-sshd.conf` (owned by JR_VPS_Orchestrators, S27).
`fail2ban-client -t` passed, reload succeeded, `fail2ban-client status` now
shows 2 jails (`recidive`, `sshd`) — **verified again post-reboot**, both
still active.

### 4d · Package updates
Ran `apt-get dist-upgrade` (29 packages, 2 security-flagged): `postgresql-16`
16.15-0ubuntu→16.15-1.pgdg, `timescaledb-2-postgresql-16` 2.29.1→2.29.2,
`cloudflared` 2026.7.3→2026.8.3, `tailscale` 1.102.2→1.102.3, plus python3.12,
krb5, procps, etc. `postgresql-common`'s trigger auto-restarted the live
Postgres instance — **verified replication stayed `streaming` immediately
after** (no lag beyond expected). `cloudflared` restart was deferred by
needrestart; restarted manually and verified active. Kernel packages
(`6.8.0-139`) were already staged, addressed by the reboot below.

### 4a · Reboot — done, full window executed
Pre-flight: `pg_backup.timer` next run was 22h out (no overlap), replication
lag negligible (23 KB), `hermes-ingestor` active. Procedure: `systemctl stop
hermes-ingestor` (clean stop, verified inactive) → `shutdown -r now` → polled
until SSH answered (back in ~1 min) → full verification pass:

| Check | Result |
|---|---|
| Kernel | `6.8.0-139-generic` (was `-137`) |
| `/var/run/reboot-required` | gone |
| `hermes-ingestor` | active, `/health` → `status: ok`, all agents healthy/starting (fred_data intentionally disabled) |
| nginx | active, `nginx -t` clean |
| Postgres bind | `100.97.62.7:5432`, `127.0.0.1:5432`, `[::1]:5432` all listening |
| Replication (primary side) | `streaming`, `async`, lag negligible |
| Timers | `pg_backup`, `hermes-vps-daily-digest`, `hermes-healthcheck`, `hermes-vps-healthcheck-weekly`, `hermes-vps-audit-monthly` all armed with correct next-run times |
| journald cap / fail2ban / swap | all survived reboot correctly (see above) |

**One real failure surfaced by the reboot, not fixed here (cross-project):**
`walk_forward_monitor.service` (hermes_v2-owned) failed twice — first with a
genuine boot-order race ("database system is starting up", expected and
harmless), then on manual retry with `psycopg.errors.InsufficientPrivilege:
permission denied for table sentiment`. Diagnosed live: `public.sentiment` in
the `hermes_v2` DB is now owned by `hermes_ingestor` (apparent side effect of
the DB role least-privilege split), and the `hermes_v2` role has no SELECT on
it. **Not fixed** — this is a DB-role decision spanning hermes_v2 and
Ingestor, flagged in a new cross-project notice (see below), not something
JR Hermes VPS should silently grant. `hermes-healthcheck.service` also failed
once at boot (ingestor health endpoint not yet warm) — retried clean once
`hermes-ingestor` settled, confirmed a pure boot race, no fix needed.

**Post-reboot `systemctl is-system-running` = `degraded`** solely because of
the one real `walk_forward_monitor.service` failure above — everything else
is green. This is expected to stay `degraded` until whoever owns that DB
grant fixes it; it is not this project's health check crying wolf again (S13
already confirmed the health-check script itself is clean).

### Cross-project notices written
- **JR Hermes Ingestor:** `docs/CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s14-cleanup-and-teardown-items.md`
  — carries forward the S13 backup-dir sizes (~1.76 GB, unchanged), flags
  `hermes_v2` DB (2.7 GB) as a possible dead-weight candidate pending
  confirmation, restates the `/opt/hermes_v2` teardown blockers, and reports
  the new `sentiment` table grant issue found this session.
- **JR Basic Crypto Signals:** `docs/CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s14-orphaned-offsite-copy.md`
  — reports the still-present 1.1 GB `crypto_signals_offsite.orphaned-s59`,
  no action taken.

---

## 2. Disk before/after
| Stage | Used | % |
|---|---|---|
| Start of S14 | 51 GB | 70% |
| After `temp_recovery_s23` drop | 41 GB | 57% |
| After `/swapfile2` removal | — | ~-8GB nominal, folded into next |
| Post-reboot, all settled | 42 GB | **58%** |

(31 GB free.) Net: ~9 GB reclaimed this session on top of S13's 543 MB
journald vacuum.

---

## 3. Session side effects (disclosure)
- The reboot sent `hermes-ingestor` offline for ~1 minute (planned, clean
  stop/start).
- `hermes-vps-daily-digest.service` fired again at boot via its timer,
  sending an extra Telegram digest (42 findings) outside its normal 09:00 UTC
  slot — timer re-triggers on the next scheduled boundary after downtime is
  expected behavior, not a bug.
- Two Telegram alerts likely fired for the transient `hermes-healthcheck` and
  `walk_forward_monitor` failures at boot before the retry/diagnosis settled
  which one was real.

---

## 4. Open items for S15

### 4a (residual) — `walk_forward_monitor.service` DB grant (cross-project)
See cross-project notice to Ingestor above. Host will show `degraded` until
this is resolved by whoever owns the `hermes_v2`/`hermes_ingestor` DB role
split. Not this project's fix to make unilaterally.

### 4c — `/opt/hermes_v2` teardown — still open, still cross-project
Unchanged from S13: still load-bearing for `bronze-audit-daily`,
`funnel_scoring`, `server_health_audit`, `walk_forward_monitor`, and
`prometheus.service`'s config path. No progress possible from this project
alone.

### 4b (residual) — items explicitly left to other projects
- `hermes-ingestor.backup-pre-s{25-phase0,27,27b,28}` (~1.76 GB) — Ingestor's.
- `crypto_signals_offsite.orphaned-s59` (1.1 GB) — Basic Crypto Signals'.
- `hermes_v2` DB itself (2.7 GB) — flagged as a possible drop candidate,
  pending confirmation it's fully superseded by Ingestor's own schema.

### 4d (residual) — low-value, deferred by choice
- `/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump` (1.2 GB) — keep
  for a grace period (a few weeks) then delete; not urgent given 31 GB free.
- No further outdated-package sweep needed this cycle — dist-upgrade cleared
  the S13 list (cloudflared, tailscale, timescaledb, kernel all current).

**Nothing else from S13's list remains open except the two cross-project
items above (4c, and the new sentiment-grant finding).** All user-gated
decisions from this session's go-ahead are closed.
