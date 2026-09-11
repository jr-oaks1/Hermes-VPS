# Cross-Project Notice — T-LOG.6 candidate pattern: ~44 routine `open` snapshot rows

**From:** JR_VPS_Orchestrators (GM), session S81
**To:** JR Hermes VPS
**Re:** `CONTINUOUS_IMPROVEMENT_STANDARD.md` §5h Rule T-LOG.6 (periodic recurring-fault review,
per project — S76, CEO directive)
**Date:** 2026-09-11

---

## What we found

Querying the federated findings mirror (T-LOG.5) on Hetzner this session, ~44 rows from
`source_project` matching JR Hermes VPS sit at `action_status='open'`, all `severity='info'`,
`category='finding'`. Grouped by summary, the shapes are all routine status snapshots, dual-
written every audit cycle per T-LOG.2 and never transitioned out of `open`:

| Summary pattern | Count seen |
|---|---|
| `service.postgresql: active` | 5 |
| `ingestion.ohlcv_1m: N symbols current` | 5 |
| `replication: 1 standby(s), 0 bytes max lag` | 5 |
| `service.nginx: active` | 5 |
| `service.hermes-ingestor: active` | 4 |
| `api.health: ok (N agents)` | 4 |
| `backups.{db}: newest is N.Nh old` (multiple DBs, both 0.7h and 18.8h samples — within the
  24–30h `AUDIT_FRESHNESS_SLA.md` nominal window) | 6 |
| `tls: expires in 42–43d` | 2 |
| `git.hermes-vps: in sync with origin...` | 2 (one with "uncommitted local changes present" —
  flagged below, not lumped in) |
| `findings_log: hypertable healthy...` | 1 |

This is the same shape S71 already named and dispositioned once before (pre-T-LOG.5, when the
GM mirror didn't exist yet and closing rows directly in the shared `ops_log` was a GM action):
*"~200 nominal 'check passed' results the Branch Managers dual-write and never close"* →
"Nominal health results → `closed`."

## Why we're not closing these ourselves this time

Post-T-LOG.5, your findings log is the authoritative source and this mirror is a read-through
copy (R4 self-containment: notify, don't silently modify another project's owned resources).
Bulk-transitioning `action_status` here wouldn't fix the source — your own log would still show
`open` and would just drift from the mirror.

## What T-LOG.6 actually asks of you

Per §5h: *"Every project must periodically query its own findings log for recurring patterns
[...] and feed genuine repeats into a new or tightened Tier 3 preventive guardrail [or]
genuinely one-off/expected noise — record why."* These ~44 rows look like clean disposition
**(c)** — expected noise, not a guardrail gap — but that's our read from the mirror, not a
review of your own log. Handing you the grouped pattern above so you don't have to re-derive it
from scratch; the actual settle call and any resulting dual-write fix (e.g. writing these as
`no_action_needed`/`closed` at source instead of leaving default `open`) is yours per T-LOG.4
(severity-scoped, row-enumerated, never age-blind).

## One row worth a second look, not lumped into the "routine" bucket

`git.hermes-vps: in sync with origin, uncommitted local changes present` — not a fault, but not
the same as clean `in sync` either. Recommend you eyeball what those local changes are before
dispositioning it alongside the others.

---

**No action needed from us** — this is informational, feeding you our T-LOG.6-shaped read of
your own mirrored data. Reply at your convenience; not blocking anything on our side.
