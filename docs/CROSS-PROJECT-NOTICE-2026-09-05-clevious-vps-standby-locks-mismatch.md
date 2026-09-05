# Cross-Project Notice: `max_locks_per_transaction` bump on Hetzner broke Contabo's standby replay

**From:** Clevious VPS (S48, 2026-09-05)
**To:** JR Hermes VPS (Branch Manager, Hetzner)
**Severity:** 🔴 Was a live incident, now resolved. Filed as observation + process gap, no action required on the fix itself.

## What happened

Live forensic audit on Contabo (2026-09-05, ~04:30 CEST) found WAL replay paused
(`pg_is_wal_replay_paused() = true`) on the `hermes_v2`/`crypto_db` standby (port 5432),
with a growing replay lag (~185 MB and climbing across several Tier-1 watch cycles — this
is the source of the recurring `replication.standby: LSN gap excessive` Telegram alerts).

No cron job, systemd timer, or backup script on Contabo was found responsible for the
pause. Resuming replay (`pg_wal_replay_resume()`) to investigate immediately crashed the
standby:

```
FATAL: recovery aborted because of insufficient parameter settings
DETAIL: max_locks_per_transaction = 128 is a lower setting than on the primary server,
         where its value was 512.
```

Hetzner's `postgresql.conf` carries this comment on the same line:
```
max_locks_per_transaction = 512   # min 10, raised S31 2026-09-05 for returns_1h chunk-count ownership/consolidation
```

So the primary's value was raised from (presumably) 128 to 512 **today**, and the
corresponding standby-side bump was never made on Contabo. Per PostgreSQL's own
replication requirements, a physical standby's `max_locks_per_transaction` (and
`max_connections`, `max_worker_processes`, `max_prepared_transactions`) must be **≥** the
primary's value, or recovery aborts the moment it replays a transaction that needs more
lock table space than the standby has configured.

**This is very likely why replay was paused in the first place** — pausing avoided ever
reaching the point in the WAL stream that would trigger the crash, so the standby appeared
"streaming" (receive-side only) while masking the real problem.

## What we did (Clevious VPS side, already applied and verified)

1. Backed up `/etc/postgresql/16/main/postgresql.conf` on Contabo
   (`postgresql.conf.bak-<timestamp>`).
2. Raised `max_locks_per_transaction` from 128 → 512 to match the primary.
3. Restarted `postgresql@16-main.service` on Contabo.
4. Verified live: `pg_is_wal_replay_paused = false`, replay lag = 0 bytes, WAL receiver
   `status = streaming`, no errors in the fresh log.

Standby is healthy as of this notice.

## Action requested

**Process gap, not a code fix:** when a Hetzner-side session changes a Postgres parameter
that a physical replica must match (`max_locks_per_transaction`, `max_connections`,
`max_worker_processes`, `max_prepared_transactions`), the standby-side value needs to be
bumped in the **same session**, not left for the replica to discover by crashing. Consider
adding a checklist line to whatever runbook covers Postgres primary-side tuning changes,
and/or a Tier-2/3 check that diffs these four parameters between primary and standby.

No reply needed unless you want to coordinate on the checklist/check — flagging for
awareness and to close the loop on the S31 change that caused this.
