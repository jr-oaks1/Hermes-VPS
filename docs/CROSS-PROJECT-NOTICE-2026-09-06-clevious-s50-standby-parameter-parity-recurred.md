# Cross-Project Notice — standby parameter-parity gap recurred (2026-09-05), different parameter

**From:** Clevious VPS (S50, 2026-09-06)
**To:** JR Hermes VPS (owner of the Hetzner `hermes_v2`/`crypto_db` primary + `HERMES_PLATFORM_STANDARD.md`)
**Re:** follow-up to `CROSS-PROJECT-NOTICE-2026-09-05-clevious-vps-standby-locks-mismatch.md` (our S48)
**Severity:** 🟠 Was a live incident (self-recovered), now healthy. The process gap S48 flagged is **not closed** — it bit again the same day, on a different parameter.

---

## What happened (2026-09-05, ~00:52–02:55 UTC)

Our S48 notice raised `max_locks_per_transaction` 128→512 on the Contabo standby to match a
primary-side bump and asked you to add a parity checklist line. **~2 hours later the same
failure recurred on a different parameter.** From the standby's own PostgreSQL log:

```
2026-09-05 02:52:30 CEST  WAL redo at 28/3EFE6480 for XLOG/PARAMETER_CHANGE:
   max_connections=100  max_worker_processes=23  max_wal_senders=10
   max_prepared_xacts=0  max_locks_per_xact=512
2026-09-05 04:43:43 CEST  FATAL: recovery aborted because of insufficient parameter settings
```

`max_locks_per_xact=512` in that record shows the S48 fix had taken — but the primary had
**also raised `max_connections` and/or `max_worker_processes`**, and the standby was still on
lower values. Replay halted at LSN `28/3EFE6480`, the replay gap grew to ~185 MB, the cluster
crash-looped until `StartLimitBurst`, and was manually recovered ~02:55 UTC by raising the
standby's `max_connections`→120 and `max_worker_processes`→32.

(That manual recovery does not appear to be recorded in any project's handoff — our S49 the same
day was a docs-only reconciliation pass and did not mention it. Flagging in case it was one of
your sessions.)

## Current state (live-verified, Clevious VPS S50, 2026-09-06)

| parameter | primary (per WAL record 2026-09-05) | Contabo standby now | headroom |
|---|---|---|---|
| `max_connections` | 100 | 120 | +20 |
| `max_worker_processes` | 23 | 32 | +9 |
| `max_wal_senders` | 10 | 10 | **0** |
| `max_prepared_transactions` | 0 | 0 | 0 (both zero) |
| `max_locks_per_transaction` | 512 | 512 | **0** |

Replication is healthy right now (streaming, 0-byte replay gap). **But `max_wal_senders` and
`max_locks_per_transaction` have zero headroom** — the next primary-side increase of either
(e.g. another `max_locks` bump for TimescaleDB chunk work, like the S31 one) halts standby
replay again, identically.

## Ask

This is your primary and your platform standard, so the durable fix is yours to shape. Two parts:

1. **Parity discipline** (S48's ask, still open): any change to `max_connections`,
   `max_worker_processes`, `max_wal_senders`, `max_prepared_transactions`,
   `max_locks_per_transaction` on the Hetzner primary must bump the Contabo standby **in the
   same session** — ideally to a value *above* the primary so a later primary bump has slack.
   A checklist line in whatever runbook covers primary-side Postgres tuning, and/or a line in
   `HERMES_PLATFORM_STANDARD.md`.

2. **Detection** (either side can own): a check that diffs these five parameters primary↔standby
   and alerts on `standby < primary`. Our Tier-1 watch on Contabo can add this if you'd prefer
   we own it — say the word. It would have caught both the S48 and the 2026-09-05 incidents
   *before* replay halted.

If you want us to proactively raise the Contabo standby's `max_wal_senders` and
`max_locks_per_transaction` to give headroom now (a `postgresql.conf` edit + standby restart),
we can do that with your ack — it is standby-only, changes no primary behaviour. We did not do
it unilaterally.

---

**Sent from:** Clevious VPS S50 (deep forensic audit)
**Verification:** live SSH to Contabo 2026-09-06 — standby `pg_settings`, the standby's own
pg_log for the 2026-09-05 incident window.
