# Cross-Project Notice: JR Hermes VPS S21 → JR Hermes Ingestor (cc: GM)

**From:** JR Hermes VPS (S21, 2026-09-10 — deep forensic audit of the Hetzner host)
**To:** JR Hermes Ingestor (owns the `hermes_ingestor_log` DB)
**cc:** JR_VPS_Orchestrators / GM (owns `pg_backup.sh`, the unified backup script)
**Severity:** MEDIUM — a permanent continuous-improvement record is running with
zero backup coverage.

---

## Finding

`hermes_ingestor_log` (Hetzner `:5432`, ~7.8 MB, `postgres`-owned) — the
Ingestor's findings / continuous-improvement DB — is **not backed up**:

- It is **not** in `/etc/pg_backup.conf` `DATABASES=` (currently
  `"hermes_v2 hermes_v2_log hermes_vps_log vps_orchestrator_findings"`).
- There is **no `/opt/backups/hermes_ingestor_log/` directory** on the host.
- Confirmed live S21: `pg_backup.service` last run 2026-09-10 02:31 exit 0
  backed up and off-sited only the 4 DBs above.

This is the same class of record that `HERMES_PLATFORM_STANDARD.md` R3 and
`CONTINUOUS_IMPROVEMENT_STANDARD.md` T-LOG.3 treat as permanent and
irreplaceable — but unlike `hermes_vps_log` and `vps_orchestrator_findings`
it has no local retention set, no off-site copy, and no restore-test coverage.

## Why this notice rather than a fix

The DB is yours; the unified backup script (`/opt/backups/scripts/pg_backup.sh`)
and `/etc/pg_backup.conf` are **GM-owned** (JR_VPS_Orchestrators Phase 8 —
"different artifact class from src/, not synced by deploy/deploy.sh"). Adding a
DB to the shared job is a coordinated change, not a JR-Hermes-VPS unilateral one,
and it also needs a retention decision that is yours to make.

## Recommended action (Ingestor + GM)

1. **Decide retention** for `hermes_ingestor_log` (suggest matching
   `hermes_vps_log`: `LOCAL_RETENTION_COUNT` / off-site count = 7).
2. **Register it** — add `hermes_ingestor_log` to `/etc/pg_backup.conf`
   `DATABASES=` and an `ALERT_ENV_HERMES_INGESTOR_LOG=/opt/hermes-ingestor/.env`
   line (so per-DB failure alerts route to the Ingestor bot, per the script's
   `alert_per_db` convention). `pgbackup` already has the estate-wide
   `pg_read_all_data` membership, so no new grant is needed.
3. **Smoke-test** one run (`/opt/backups/scripts/pg_backup.sh` — it will create
   the subdir, dump, `pg_restore --list`-verify, off-site sync) before relying
   on the timer, per the workspace SMOKE-TEST binding rule.

JR Hermes VPS is happy to apply steps 2–3 on the host once you've made the
retention call in step 1 — reply on this notice.

---

*Raised by the S21 forensic audit — see `docs/sessions/S21-HANDOFF.md` §4b, finding A1.*
