# S22 Handoff — JR Hermes VPS

**Date:** 2026-09-11
**Session type:** Close both S21 low-priority owned items (B8, B3), sweep every
cross-project pending for replies, confirm host health.
**Numbering:** verified against `docs/sessions/` on disk (newest was
`S21-HANDOFF.md`) → this session is **S22**. **Next handoff = S23.**

**Status:** 🟢 DONE (B8/B3 close) → 🟡 **continued same session**: a follow-up
deep forensic audit, a full doc audit of `VPS_CONNECTIVITY_REFERENCE.md`, a
live confirmation of the VPS/DB backup setup, an SSH direct-route check
(Hetzner vs. Contabo), and a drafted SSH-port-alignment + hardening plan —
all at the user's request, same conversation, so still **S22** per the
session-numbering rule. Host `running`, 0 failed units, 0 open/in_progress
findings, replication `streaming/async/0` (424-byte lag), disk 46-47%,
`deploy_guardrail.sh` 9/9. `/opt/hermes-vps` deploy clone synced through
this session's final commit.

## 8. Continued this session: forensic audit, doc audit, backup confirmation, SSH plan

**Forensic audit (read-only, live):** no CRITICAL/HIGH. All green — system,
replication (996 MB `:5435` orch DB confirmed via live size query), UFW,
fail2ban (jail correctly watches `_SYSTEMD_UNIT=ssh.service`, 0 banned),
Tailscale, unattended-upgrades, netdata (0 non-clear of 102 alarms), TLS
(valid to 2026-10-19).

**Doc audit of `docs/VPS_CONNECTIVITY_REFERENCE.md`:** §5 (roles/databases,
`pg_hba`) — accurate, matches live exactly. §4 (firewall ports) — accurate
but doesn't yet note the S22 `:22` bind-scope change (cosmetic gap). **§7
"Active Services by Node" is stale and self-contradicts the rest of the
doc** — lists `hermes_v2.service` as active (live: `disabled`/`inactive`,
decommissioned) and `crypto-health-monitor.service` as a live alerting
service (**that unit no longer exists on the host at all**); its backup
description ("2 local dumps kept... `ALERT_ENV` → `/opt/crypto-health-monitor/.env`")
predates the Phase 8 convergence (live: `LOCAL_RETENTION_COUNT=7`,
`ALERT_ENV=/root/.hermes_vps/.env`). **Not fixed this session** — flagged as
a finding, rewrite needs its own pass.

**Backup setup confirmed live** (`/etc/pg_backup.conf` + `gdrive:vps-backups/`):
full 3-2-1 (local + Contabo off-site + Google Drive) genuinely holds for
`hermes_v2`, `crypto_signals`, `clevious_vps_log`, `hermes_v2_log`,
`vps_orchestrator`. Gaps found: `hermes_ingestor_log` has **zero** coverage
(A1, unchanged); `hermes_vps_log` and `vps_orchestrator_findings` have
local+off-site but **no Drive leg** (new — **A3**). One restore-test ever
run on Hetzner (`hermes_v2`, 2026-09-02, PASS, 14,509 tables) — none for any
other DB. See §6 "Backup design note" for the enrollment recommendation.

**SSH direct-route check:** confirmed live, both hosts have two independent
routes each (Hetzner: Tailscale `:22` + public `:52222`; Contabo: Tailscale
`:2222` + public `:2222`) — neither host depends on the other to be
reachable. The one documented "jump via Contabo to reach Hetzner" case
(`JR Hermes Ingestor/docs/sessions/S10-HANDOFF.md`) was a **failed**
last-resort attempt during a real historical outage, not a working or
relied-upon route.

**SSH port alignment + hardening plan drafted:** `docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md`.
Key finding: Hetzner's `:22`/`:52222` split (private Tailscale-only +
separate public fallback) is the *safer* shape of the two hosts — Contabo's
identical port (`:2222`) for both paths is the real asymmetry. Recommended
Contabo be hardened to match Hetzner's shape, not the reverse. Nothing
applied — proposal only, Contabo section is Clevious VPS's to execute.

---

## Quick resume for next session (S23)

**Nothing owned is open.** Sanity checks:
```
systemctl is-system-running                         # running
systemctl --failed                                  # empty
bash /opt/hermes-vps/scripts/deploy_guardrail.sh    # all 9 green
psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT action_status,count(*) FROM findings_log WHERE action_status IN ('open','in_progress') GROUP BY 1"   # 0 rows
sudo -u postgres psql -tAc "SELECT rolname FROM pg_roles WHERE rolname='crypto_platform';"  # 0 rows — stays dropped
ss -tlnpe | grep -E ':22 |:52222 '                  # :22 only on 100.97.62.7/127.0.0.1/[::1]; :52222 unchanged
```
Then look at **§4 pendings table** — everything left is another project's.

---

## 1. B8 — dropped the orphaned `crypto_platform` role

Live-verified before touching anything: LOGIN role, 0 rows in
`pg_stat_activity`, 0 table/sequence grants in `hermes_v2` (relacl scan
empty), no `crypto*` database on the cluster, no `/opt/crypto_platform/` on
the host, no systemd unit references it, nothing in current Postgres logs.
The only surviving references are documentation: this repo's own
`VPS_CONNECTIVITY_REFERENCE.md`, and the `crypto_data` project (workspace
`CLAUDE.md`: "Legacy/superseded — do not build on this"), whose
`.env.template` / `sql/01_create_user_db.sql` still name the role but whose
database (`crypto_db`) and `/opt/crypto_platform/` deploy dir are both gone
(the dump S21 deleted was the last surviving copy).

**Sequence (all live, this session):**
1. `sudo -u postgres pg_dumpall --roles-only` → `/opt/backups/manual/pg_globals_pre-s22.sql` (19 roles captured, `crypto_platform` line present).
2. `BEGIN; REVOKE …; DROP ROLE crypto_platform; ROLLBACK;` — smoke test, clean, no error.
3. `deploy/sql/S22_drop_crypto_platform_role.sql` applied for real via `sudo -u postgres psql -f -`. Its own hard gate — a `pg_shdepend` scan across the **whole cluster** for any ownership/ACL/default-ACL dependency on the role — returned **0 rows** before the `DROP ROLE` ran.
4. Verify query: 0 rows. Role is gone.
5. `docs/VPS_CONNECTIVITY_REFERENCE.md` §5 updated — row removed, login-role count 18→17, dated note added.

No rollback needed; the snapshot at `/opt/backups/manual/pg_globals_pre-s22.sql` is the recovery path if ever needed (recreate: `CREATE ROLE crypto_platform LOGIN; GRANT CONNECT ON DATABASE hermes_v2 TO crypto_platform;`).

## 2. B3 — sshd `:22` bind-scope hardening, applied live

Investigated first: `sshd_config`'s `ListenAddress` is inert on this host
(ssh is socket-activated; `Port`/`ListenAddress` in `sshd_config` are
ignored). The real bind lives in `ssh.socket` drop-ins. Staged
`deploy/ssh.socket.d/20-jr-bind-scope.conf` — a single empty `ListenStream=`
resets the vendor unit's accumulated `0.0.0.0:22`/`[::]:22` list, then rebuilds
it as `100.97.62.7:22`, `127.0.0.1:22`, `[::1]:22`, leaving `10-jr-extra-port.conf`'s
`0.0.0.0:52222`/`[::]:52222` untouched.

**Applied with a real auto-revert, not just a plan:**
1. Copied the drop-in to the host, `systemd-analyze verify` clean.
2. Armed a detached 10-minute auto-revert (`nohup … &`, PID recorded) **before** reloading.
3. `systemctl daemon-reload && systemctl restart ssh.socket`.
4. `ss -tlnpe` confirmed: `:22` now **only** on `100.97.62.7` / `127.0.0.1` / `[::1]`; `:52222` unchanged on `0.0.0.0`/`[::]`.
5. From the workstation, in fresh separate connections: `ssh … root@100.97.62.7` (Tailscale `:22`) **succeeded**; `ssh -p 52222 … root@46.225.14.26` (public fallback) **succeeded**.
6. Only then: `kill` on the armed revert PID — confirmed disarmed (no `AUTO-REVERT FIRED` log line).

Drop-in moved from `deploy/_staged/` to `deploy/ssh.socket.d/` (now describes
itself as applied, not staged) and committed. `UFW` eth0 default-deny is
still in place as the outer layer — this is defense-in-depth, not a
replacement for it.

## 3. Cross-project pending sweep (read-only, no other project's resources touched)

Read the newest handoff/notice in each sibling repo before updating our own
table:

| # | Item | Finding this session |
|---|---|---|
| **Y1** | Wire `parity_reader` into `contabo_tier1_watch.py` | ✅ **CLOSED** — Clevious VPS S53 added the `psql_remote()` helper + the 5-GUC query; S57 confirms live and quiet ("GUC parity check … ✅ live and quiet … running against the primary via `parity_reader` each time, ending `all checks clear`"). |
| **Y2** | Raise Contabo standby `max_wal_senders` 10→16 + `max_locks_per_transaction` 512→1024 + restart | ✅ **CLOSED** — Clevious VPS S53 applied both, S57 re-confirms live: `max_wal_senders=16`, `max_locks_per_transaction=1024` on Contabo, both above the Hetzner primary's 10/512 per R5. |
| **A1** | Register `hermes_ingestor_log` in the backup job | Still open. Ingestor's newest handoff (S42, same day) predates or doesn't mention our notice; no reply file exists in Ingestor's `docs/`. Since S21 (2026-09-10). |
| **A2** | Verify `:5435` `vps_orchestrator` dump completeness | Still open. GM's newest handoff (S77, 2026-09-08) predates our S21 notice (2026-09-10) — GM hasn't had a session touch it yet. Since S21. |
| **X1** | GM bulk-triage mirrored S19b storm CRITICALs, close S41 escalation | Still open, same reason as A2 — GM's S77 predates the S19b storm (2026-09-10). Since S19b. |
| **X3** | `/opt/hermes_v2` teardown + stale `FRED_API_KEY` | Still open. Ingestor S42 confirms explicitly: "`/opt/hermes_v2` teardown remains the open cross-project item … Nothing owed our side yet." Since S16. |
| **P3** | GM commit of the S19b reply notice | Still open — verified live: `docs/CROSS-PROJECT-NOTICE-REPLY-2026-09-10-s19b-to-ingestor-gm-deadlock-fixed.md` sits **untracked** (`git status` `??`) in `JR_VPS_Orchestrators`. Not our repo to commit into. Since S19b. |
| **Y3 / B7** | Cross-host TimescaleDB pkg divergence (2.29.2 Hetzner / 2.29.1 Contabo, latent at next PG restart) | Still open. GM S77 explicitly carries it as P1 #2, "Awaiting their remediation" (Ingestor owns the Hetzner side). Since S19. |
| **Y4** | Clevious S50 R5 detection-control naming confirmation | Effectively addressed in passing — Clevious S57 corrected the systemd **unit name** (`clevious-vps-tier1-watch.timer`, not `contabo_tier1_watch`) in its own docs; no separate reply notice seen. Leaving open but low-priority/cosmetic. |

Nothing on another project's host, DB, or repo was modified. The one write
this session made to a shared resource was our own role/network change on
the host **we** own outright.

## 4. Health / audit pass (all green, host `hermes`)

| Check | Result |
|---|---|
| `systemctl is-system-running` | `running` |
| `systemctl --failed` | empty |
| Uptime / load | 4d19h, load 0.12/0.17/0.15 |
| Disk `/` | 46% (39G free / 75G) — down slightly from S21's 47%, expected drift |
| Replication | `streaming`/`async`, 424-byte lag (~0) |
| `deploy/hermes-vps-{guardrail,escalation}` last run | `ExecMainStatus=0` both |
| `deploy_guardrail.sh` | **9/9 assertions PASS** (re-run after the B8/B3 changes — unaffected, as expected) |
| `findings_log` open/in_progress | **0 rows** |
| `findings_log` total / newest | 40,137 rows (was 40,113 at S21 close; +24 over ~24h, matches the S18 steady-state emission rate) |
| netdata alarms | 0 non-CLEAR |
| `certbot.timer` | active, last ran 2026-09-10 14:06 UTC |
| `pg_backup.service` | `ExecMainStatus=0` |
| `/opt/hermes-vps` deploy clone | fast-forwarded to this session's HEAD after push (see commits below) |

## 5. Commits (all on `main`, pushed, deploy clone synced)

```
6a2071d S22: drop orphaned crypto_platform role (B8) + sshd bind-scope hardening (B3)
```

## 6. Pendings for S23

### JR Hermes VPS owned
| # | Item | State |
|---|---|---|
| C1 | **SSH port alignment + hardening plan** — `docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md` (drafted this session, post-handoff). Hetzner is already in the recommended target shape (no action needed); the Hetzner-side follow-up items are H3 (`sshd_config` `PasswordAuthentication`/`PermitRootLogin` live re-check — not yet done), H4 (`ufw limit` on `:52222`), H6 (fold SSH auth-anomaly counts into the Tier 3/4 guardrail). None urgent — current 3-layer posture on `:22`/`:52222` is already sound. | Proposal written, no execution yet — needs a go-ahead per item. |
| C2 | **Universal 3-2-1 backup enrollment** — extend the *existing* nightly `pg_backup.sh` + `gdrive_sync.sh` pipeline (no new mechanism) to the 3 databases currently short a leg: `hermes_ingestor_log` (0 of 3 legs — this is A1, unchanged), `hermes_vps_log` and `vps_orchestrator_findings` (2 of 3 — missing only the Google Drive cold-storage leg). All three are small; assessed this session as genuinely low-cost to close, not "too much." The `DATABASES=` edit is ours to apply on the owning project's go-ahead (A1's existing pattern); the `gdrive_sync.sh` DB-list edit lives on Contabo — not ours to make. | New this session — see §"Backup design note" below. |

### Waiting on other projects
| # | Item | Owner | Since |
|---|---|---|---|
| A1 | Register `hermes_ingestor_log` in the backup job (now also tracked under C2) | Ingestor + GM | S21 |
| A2 | Verify `:5435` `vps_orchestrator` dump is full + off-sited | GM | S21 |
| A3 | Add `hermes_vps_log` + `vps_orchestrator_findings` to `gdrive_sync.sh`'s DB list (now also tracked under C2) | GM / Clevious VPS (owns `gdrive_sync.sh` on Contabo) | S22 |
| C1-Contabo | Contabo SSH port split (private Tailscale-only port + kept `2222` as public-only) per `docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md` §5 | Clevious VPS | S22 |
| X1 | Bulk-triage `vps_orchestrator_findings` for mirrored S19b storm CRITICALs, close S41 escalation | GM | S19b |
| X3 | `/opt/hermes_v2` teardown + stale `FRED_API_KEY` | Ingestor | escalated S16 |
| P3 | GM commit of the S19b reply notice (currently untracked in their repo) | GM | S19b |
| Y3/B7 | Cross-host TimescaleDB pkg divergence — latent at next PG restart | GM (Ingestor remediates) | escalated S19 |
| Y4 | Clevious S50 R5 naming confirmation (cosmetic; unit name already self-corrected in their docs S57) | Clevious VPS | S16 |

### Backup design note (this session)
Asked whether full 3-2-1 for every database is overkill vs. a simpler
"local + cold-storage rotation" scheme. Assessment: **don't simplify away
from 3-2-1** — the local+off-site+Drive pipeline already exists and runs
nightly; the only gap is 3 small findings/log DBs not enrolled in all its
legs (table above). Enrolling them is a few config-list lines in tooling
that already runs, not new infrastructure — genuinely cheap, so closing the
gap is the right call over inventing a lighter-weight scheme for "small" DBs.

### Closed this session (were open at S21 close)
- **B8** `crypto_platform` orphan role — dropped, verified gone, doc updated. See §1.
- **B3** sshd `:22` bind-scope hardening — applied live with a verified auto-revert, both paths confirmed. See §2.
- **Y1** `parity_reader` wiring into `contabo_tier1_watch.py` — confirmed done by Clevious S53/S57. See §3.
- **Y2** Contabo standby GUC headroom bump — confirmed done and holding by Clevious S53/S57. See §3.

---

## 7. Interaction / numbering / ground-rule notes

`#Interaction NN` opener + hallucination-zone flagging observed throughout
S22. Session = **S22** (disk-verified against `docs/sessions/`). Next = **S23**.
**Smoke-test binding rule** honoured for both B8 (BEGIN/ROLLBACK dry-run
before the real DROP) and B3 (staged file + `systemd-analyze verify` +
armed auto-revert + dual-path confirmation before disarming). No auto-mode
block encountered this session — SSH worked directly throughout.
