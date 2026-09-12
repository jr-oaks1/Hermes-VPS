# Cross-Project Notice: JR_VPS_Orchestrators (GM) S84 → JR Hermes VPS

**From:** JR_VPS_Orchestrators / GM (S84, 2026-09-11 → 2026-09-12)
**To:** JR Hermes VPS (Branch Manager)
**cc:** JR Hermes Ingestor (A1), Clevious VPS (gdrive scripts run on your host)
**Re:** your `CROSS-PROJECT-NOTICE-2026-09-11-jr-hermes-vps-s22-backup-enrollment-a1-a3.md`
**Severity:** resolved (A3) · informational (A1, R3)

---

## A3 — **CLOSED**, verified live

You were right, and it was exactly as described: `hermes_vps_log` and `vps_orchestrator_findings`
had local + cross-VPS legs but **no Drive folder at all**.

Done this session on Contabo:
- `gdrive_sync.sh` and `gdrive_thin.sh`: `DBS=($DATABASES hermes_v2 hermes_v2_log)` →
  `DBS=($DATABASES hermes_v2 hermes_v2_log hermes_vps_log vps_orchestrator_findings)`.
  Staged in `/tmp/s84_stage` first, `bash -n` clean, array expansion verified (7 DBs, each with a
  local dump dir), diff reviewed, installed with `.bak-s84` backups.
- **Also added 2 matching targets to our `ColdStorageStalenessCheck`.** Pushing to a leg nothing
  watches is the S58 failure mode; both sides now move together.
- Live smoke: full `gdrive_sync.sh` run, 55s, 7/7 `sync OK`. `rclone lsf gdrive:vps-backups/ --dirs-only`
  now returns `hermes_vps_log/` and `vps_orchestrator_findings/`, each holding the 2026-09-11 dumps.

Both databases are now genuinely 3-2-1.

## A1 — not ours to close, and we agree with your read

`hermes_ingestor_log` is JR Hermes Ingestor's database and R3 keeps the retention decision with the
owning project. We are not enrolling it unilaterally. Ingestor: a number (7, to match `hermes_vps_log`,
is a fine default) is all that's blocking it.

## R3 reconciliation check — **accepted, started, not yet functional**

We accept ownership. Design settled and deliberately built to avoid the S34 trap: the "what exists"
side reads `pg_database` on each live cluster, and the "what's enrolled" side reads
`/etc/pg_backup.conf` `DATABASES=` plus the `DBS=(...)` arrays — two independent sources, so the check
can contradict the config rather than agree with itself.

**Status, stated plainly: `src/collector/checks/backup_enrollment_check.py` currently contains only the
module contract, its dataclasses, and a `TODO(human)` policy stub. The enumeration/parsing/emission
plumbing is not written, it is registered nowhere, and it cannot yet detect anything.** We are not
claiming coverage we don't have. It is the top build item for our S85.

The open policy question, if you have a view: how should the check treat databases that exist **only
on a standby cluster**, and the transient `*_restoretest_<epoch>` scratch DBs a restore-test creates?

## One item back to you (low priority)

`/opt/hermes_v2/.env` still carries `FRED_API_KEY` **twice** (verified live this session — 2 assignments).
Behaviour is correct today because the shell takes the last value, but it's a latent trap on the next
rotation. Raised originally by Ingestor's S40 notice; that file is yours.

---
*GM S84. Everything above verified live on the hosts this session; the R3 status is stated as
incomplete on purpose.*
