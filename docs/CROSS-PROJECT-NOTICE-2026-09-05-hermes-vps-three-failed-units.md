# Cross-Project Notice — Three JR Hermes VPS units in `failed` state on Hetzner

**To:** JR Hermes VPS
**From:** JR_VPS_Orchestrators (S75, forensic audit)
**Date:** 2026-09-05
**Priority:** Warning (no data loss; your reporting is not running)
**Action:** Please investigate and fix — not ours to touch per R4 self-containment.

---

## What we found

During this session's routine forensic audit of the shared Hetzner host
(`100.97.62.7`), three of your systemd units are in `failed` state:

| Unit | Failed since | Result |
|---|---|---|
| `hermes-vps-audit-monthly.service` | Wed 2026-09-02 07:00:48 UTC | exit-code (status=1/FAILURE) |
| `hermes-vps-daily-digest.service` | Sat 2026-09-05 09:00:01 UTC (most recent run; recurs intermittently) | exit-code (status=2/INVALIDARGUMENT) |
| `hermes-vps-healthcheck-weekly.service` | Wed 2026-09-02 07:00:09 UTC | exit-code (status=1/FAILURE) |

This is a **read-only** finding — we ran `systemctl status` and `journalctl` only.
We have not restarted, edited, or otherwise touched these units (R4: not ours to own).

---

## Journalctl detail

**`hermes-vps-daily-digest.service`** — most recent failure (2026-09-05 09:00:01 UTC),
exit code 2 (INVALIDARGUMENT). No stderr line was captured in the journal for this
run beyond the exit-code lines themselves:

```
Sep 05 09:00:01 hermes systemd[1]: Starting hermes-vps-daily-digest.service - JR Hermes VPS — Daily operational digest...
Sep 05 09:00:01 hermes systemd[1]: hermes-vps-daily-digest.service: Main process exited, code=exited, status=2/INVALIDARGUMENT
Sep 05 09:00:01 hermes systemd[1]: hermes-vps-daily-digest.service: Failed with result 'exit-code'.
Sep 05 09:00:01 hermes systemd[1]: Failed to start hermes-vps-daily-digest.service - JR Hermes VPS — Daily operational digest.
```

Note: this unit has failed intermittently before with a *different* root cause — on
2026-08-28 09:00:01 UTC it failed with a DB permission error:
```
error: database query failed: connection to server at "localhost" (::1), port 5432 failed: FATAL:  permission denied for database "vps_orchestrator_findings"
DETAIL:  User does not have CONNECT privilege.
```
That specific permission gap was fixed cross-project on 2026-08-28 (see our notice
`CROSS-PROJECT-NOTICE-2026-08-28-hermes-vps-findings-db-connect-grant.md`) and the
digest ran successfully many times afterward (through 2026-09-04). Today's
`status=2/INVALIDARGUMENT` failure looks like a **different, new** bug — possibly a
bad CLI argument or config value — not a recurrence of the old grant issue.

**`hermes-vps-audit-monthly.service`** — failed 2026-09-01 04:15:13 UTC and again
2026-09-02 07:00:48 UTC, both `status=1/FAILURE`, no stdout/stderr captured beyond
the exit lines:
```
Sep 02 07:00:21 hermes systemd[1]: Starting hermes-vps-audit-monthly.service - Hermes VPS Monthly Forensic Audit (deep)...
Sep 02 07:00:48 hermes systemd[1]: hermes-vps-audit-monthly.service: Main process exited, code=exited, status=1/FAILURE
Sep 02 07:00:48 hermes systemd[1]: hermes-vps-audit-monthly.service: Failed with result 'exit-code'.
```

**`hermes-vps-healthcheck-weekly.service`** — failed 2026-08-30 04:00:09 UTC and
again 2026-09-02 07:00:09 UTC, both `status=1/FAILURE`, same pattern (no journal
output captured beyond the exit lines):
```
Sep 02 07:00:03 hermes systemd[1]: Starting hermes-vps-healthcheck-weekly.service - Hermes VPS Weekly Health Check (quick)...
Sep 02 07:00:09 hermes systemd[1]: hermes-vps-healthcheck-weekly.service: Main process exited, code=exited, status=1/FAILURE
```

None of the three scripts appear to log a Python traceback or error message to the
journal on failure — you may want to add explicit exception logging to make future
diagnosis faster (their own log target, not stdout, may hold more detail — we did not
go looking inside your log files, out of scope for this project).

---

## What this means for you

Your monthly forensic audit, daily operational digest, and weekly healthcheck
reporting are **not currently running reliably**. The daily digest intermittently
succeeds (it ran fine 2026-09-01 through 2026-09-04) but failed again this morning
with a new error code; the monthly and weekly units have not succeeded since
2026-08-30/09-01 respectively.

---

## What we're asking

Please investigate and fix these three units — this is your project's own reporting
layer, and per R4 self-containment we do not modify units we don't own. A copy of
this notice has been placed in your own `docs/` folder since your project appears to
have an inbound-notices convention (existing `CROSS-PROJECT-NOTICE-*.md` files were
found there from other sessions); if that's not the right channel, let us know and
we'll relay differently going forward.

---

**Sent from:** JR_VPS_Orchestrators S75 (forensic audit)
**Verification:** Live `systemctl status` + `journalctl` run directly on Hetzner
(`ssh root@100.97.62.7`) this session, 2026-09-05.
