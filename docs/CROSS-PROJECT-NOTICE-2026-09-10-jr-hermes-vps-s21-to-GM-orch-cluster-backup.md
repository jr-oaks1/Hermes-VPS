# Cross-Project Notice: JR Hermes VPS S21 → GM (JR_VPS_Orchestrators)

**From:** JR Hermes VPS (S21, 2026-09-10 — deep forensic audit of the Hetzner host)
**To:** JR_VPS_Orchestrators / GM (owns the Hetzner `16/orch:5435` cluster + its backup)
**Severity:** MEDIUM — backup completeness of the `vps_orchestrator` DB is
unverified; possibly fine.

---

## Finding

The Hetzner `16/orch` cluster on `:5435` holds the `vps_orchestrator` DB, which
`pg_database_size()` reports as **~950 MB** live. The only backup of it on the
host is:

```
/opt/backups/vps_orchestrator/vps_orchestrator_20260910_013016.dump   30 MB   01:30 UTC daily
```

**30 MB from a 950 MB database.** That is a 32× ratio — plausible if the DB is
mostly highly compressible text (reasoning logs / report JSON) or mostly bloat,
but also exactly what a `--schema-only` or a `pg_dump` that silently skipped a
large table would look like. This dump is produced by a mechanism **outside**
`/etc/pg_backup.conf` (that job's `DATABASES=` covers `vps_orchestrator_findings`
on `:5432` — a different DB on a different cluster).

## Ask

1. Confirm what writes `/opt/backups/vps_orchestrator/*.dump` (a GM cron/timer?
   `vps-orchestrator-daily`?) and that it is a **full** `-F c` dump, not
   schema-only / filtered.
2. Confirm it has **off-site** coverage (the unified `pg_backup.sh` off-site leg
   only pushes its own 4 DBs; this dump is not in that set).
3. If it turns out uncovered or partial, fold `vps_orchestrator` (:5435) into the
   unified `pg_backup.sh` path — it already supports multiple clusters via
   `PG_PORT` per conf, though a single conf can only name one port today, so this
   may want its own small drop-in.

Also for your awareness: JR Hermes VPS S21 added a pointer to the `:5435` cluster
in `docs/VPS_CONNECTIVITY_REFERENCE.md` §5 (it was covered in §18/§19 but not
cross-linked from the roles section, which S21 reconciled).

---

*Raised by the S21 forensic audit — see `docs/sessions/S21-HANDOFF.md` §4b, finding A2.*
