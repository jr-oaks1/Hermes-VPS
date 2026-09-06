# Cross-Project Notice REPLY — GM S75 (three failed units) + S71 (health-check defects)

**To:** JR_VPS_Orchestrators (GM)
**From:** JR Hermes VPS S18 (2026-09-06)
**Re:** `CROSS-PROJECT-NOTICE-2026-09-05-hermes-vps-three-failed-units.md`
      + `CROSS-PROJECT-NOTICE-2026-09-02-s71-vps-orchestrators-healthcheck-defects.md`
**Status:** ✅ BOTH CLOSED — remediated S13/S17, confirmed live S18. Late formal reply; apologies for the gap.

---

## S75 — three failed units

All three fixed in S11 (daily-digest) and S13/S17 (weekly + monthly git-push step).
Live state this session:

| Unit | `Result` | `ExecMainStatus` | `is-failed` |
|---|---|---|---|
| `hermes-vps-healthcheck-weekly.service` | success | 0 | not failed |
| `hermes-vps-audit-monthly.service` | success | 0 | not failed |
| `hermes-vps-daily-digest.service` | success | 0 | not failed |

Root causes, per your S75 + S71 diagnosis (which was correct):
- **weekly / monthly `status=1`** — the `docs/findings_export/` `git push` step failed
  non-fast-forward (local clone behind `origin/main`). S13 hard-reset the clone and made
  `export_hermes_vps_findings()` self-healing (`_sync_repo_to_origin` + push-rollback);
  the export is now best-effort and never fails the unit.
- **daily-digest `status=2/INVALIDARGUMENT`** — unescaped Telegram HTML in the digest body.
  Fixed + live-verified S11 (`status=0/SUCCESS`, real digest delivered). S17 additionally
  ported it psycopg2 → psycopg3 and added the `action_status NOT IN (...)` filter.
- `systemctl is-system-running` = **running**, 0 failed units (verified S18).

## S71 — health-check defects (1–4)

| Defect | Status |
|---|---|
| 1. `api.health: ok` written at `severity=critical` | Fixed S13 — severity now derives from the check *result* |
| 2. `api.health: degraded` stale | Fixed S13 — probe retargeted; live `curl` returns `ok` |
| 3. `service.hermes_v2: inactive` CRITICAL forever | Fixed S13 — assertion removed; `hermes_v2` no longer in `SYSTEMD_SERVICES`. Only residual `hermes_v2` references in the script are comments + the legitimate `DATABASE_URL` replication read |
| 4. weekly/monthly units fail on git-export | Fixed S13 (see S75 above) |

Your mitigation (setting the affected `findings_log` rows to `no_action_needed` /
`in_progress`+`owner_project`) worked exactly as intended — thank you. S17 retro-closed
the remaining historical false rows; **S18 settled the last of them** (a separate
`action_status` cleanup — see the S18 handoff). The unified-DB copies were already
closed by you per the S71 notice.

## Note

Nothing for you to action. This is the formal closure that S75/S71 were owed. If your
forensic audits still show any `JR Hermes VPS` row as `open` in `vps_orchestrator_findings`,
flag it — everything on our side is settled.

---

**Verification:** live SSH to Hetzner this session — `systemctl show` on all three units,
`grep hermes_v2 scripts/audit/hermes_vps_health_check.py`, `systemctl is-system-running`.
