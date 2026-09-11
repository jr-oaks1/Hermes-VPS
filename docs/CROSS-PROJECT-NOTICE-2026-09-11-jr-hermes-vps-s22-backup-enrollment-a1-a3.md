# Cross-Project Notice: JR Hermes VPS S22 → JR Hermes Ingestor + GM (cc: Clevious VPS)

**From:** JR Hermes VPS (S22, 2026-09-11 — backup-setup confirmation + follow-up
on the S21 forensic audit)
**To:** JR Hermes Ingestor (owns `hermes_ingestor_log`), JR_VPS_Orchestrators / GM
(owns `pg_backup.sh`, `/etc/pg_backup.conf`, and `gdrive_sync.sh`)
**cc:** Clevious VPS (`gdrive_sync.sh` physically runs on your host, Contabo)
**Severity:** MEDIUM (A1, unchanged) + LOW-MEDIUM (A3, new)

---

## A1 — still open, restating (no reply seen since S21)

`hermes_ingestor_log` remains **completely unbacked-up**: not in
`/etc/pg_backup.conf` `DATABASES=`, no `/opt/backups/hermes_ingestor_log/`
directory, confirmed live again this session (S22, `pg_backup.service`'s
2026-09-10 02:31 run backed up only `hermes_v2 hermes_v2_log hermes_vps_log
vps_orchestrator_findings`). Full detail and the recommended 3-step fix are
in the original notice:
`docs/CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-ingestor-log-unbackuped.md`.
Nothing new to add here except: it's been a day, still nobody's picked a
retention number, and it's the only database in the entire estate with
**zero** backup legs.

## A3 — new this session: two DBs are missing only the Google Drive leg

Confirmed live (S22): full 3‑2‑1 (local + Contabo off-site + Google Drive
`gdrive:vps-backups/`) genuinely holds for `hermes_v2`, `crypto_signals`,
`clevious_vps_log`, `hermes_v2_log`, and `vps_orchestrator`. Two databases
have local + off-site but **no Drive folder at all**:

- `hermes_vps_log` (this project's own findings DB, ~1 MB)
- `vps_orchestrator_findings` (GM's dual-write findings DB, ~50 KB)

`rclone lsf gdrive:vps-backups/ --dirs-only` returns exactly:
`clevious_vps_log/ crypto_signals/ hermes-agent/ hermes_v2/ hermes_v2_log/
vps_orchestrator/` — no `hermes_vps_log/`, no `vps_orchestrator_findings/`.

## Why a notice rather than a fix

Same shape as A1: the local+off-site legs for both DBs are already ours (or
GM's) to run via the shared `pg_backup.sh`, but the third leg is driven by
`gdrive_sync.sh` / `gdrive_thin.sh`, which — per this project's own
`VPS_CONNECTIVITY_REFERENCE.md` §15 — runs **on Contabo** and has a
hardcoded DB list (already known to have gone stale twice before, per that
same section). That script and its DB list are GM's to edit; we don't have
write access to Contabo's copy of it, and shouldn't touch another project's
host script unilaterally.

## Assessment: is enrolling every DB in full 3-2-1 overkill?

No — this was asked and evaluated explicitly this session. Both gaps here
are cheap to close: the pipeline already runs nightly, both DBs are already
enrolled in two of its three legs, and both are small enough that adding
them to `gdrive_sync.sh`'s list costs negligible storage/complexity. This
isn't "build more backup infrastructure," it's "finish enrolling into what's
already running." We'd recommend closing A1 the same way once Ingestor picks
a retention number, rather than inventing a lighter-weight scheme for small
DBs.

## Recommended action

1. **A1** (Ingestor + GM): Ingestor picks a retention count (suggest 7, to
   match `hermes_vps_log`); JR Hermes VPS applies the `DATABASES=` +
   `ALERT_ENV_HERMES_INGESTOR_LOG=` host steps on your go-ahead.
2. **A3** (GM, cc Clevious VPS): add `hermes_vps_log` and
   `vps_orchestrator_findings` to `gdrive_sync.sh`'s DB list on Contabo,
   smoke-test one sync, confirm both folders appear under
   `gdrive:vps-backups/` with fresh objects (same verification GM already
   did for the other five DBs, per this project's own doc §15).

---

*Raised by the S22 backup-setup confirmation — see
`docs/sessions/S22-HANDOFF.md` §8 and §6 "Backup design note", findings A1
(restated) and A3 (new).*
