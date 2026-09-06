# S15 Handoff — JR Hermes VPS

**Session type:** Close out all S14 residual pendings. User gave explicit
one-time authorization to apply the cross-project `sentiment` grant fix
directly and to action every other open item.

**Date:** 2026-09-06 (host clock at session close: `2026-09-06 ~05:14 UTC`).

**Status:** 🟢 Host back to `running`. The one live `degraded` cause is fixed.
Everything else on the list is either genuinely blocked (load-bearing) or
correctly deferred (fresh safety copy) — documented below, not left ambiguous.

---

## Quick Resume for whoever opens S16

**Nothing is open that this project can act on.** Host is healthy:
`is-system-running` = `running`, disk 58% (31 GB free), replication
`streaming/async/0` lag.

Remaining items, all genuinely not-this-project-to-force:

1. **`/opt/hermes_v2` teardown** — still hard-blocked. Verified live this
   session: `bronze-audit-daily`, `funnel_scoring`, `server_health_audit`,
   `walk_forward_monitor` and `prometheus.service` all still run out of
   `/opt/hermes_v2`. All four timers armed, last runs `ExecMainStatus=0`.
   Cannot be removed without migrating or retiring those units — a
   hermes_v2/Ingestor decommission decision, not a VPS one.
2. **Disk items owned elsewhere** — Ingestor `backup-pre-s*` (~1.76 GB),
   Basic Crypto Signals `crypto_signals_offsite.orphaned-s59` (1.1 GB),
   `hermes_v2` DB itself (2.7 GB, possible drop candidate). Notices already
   sent in S14; no reply yet as of this session.
3. **`/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump`** (1.2 GB) —
   created 2026-09-06 04:05, i.e. *hours* before this session. Keep the full
   grace period; revisit end of September 2026.

---

## 1. What was done and verified live this session

### `walk_forward_monitor.service` — FIXED (host no longer `degraded`)

**Root cause (confirmed live):** `public.sentiment` in the `hermes_v2` DB is
owned by `hermes_ingestor` (from the DB least-privilege split). When ownership
moved, `crypto_signals_research`, `cyclestation` and `audit_reader` were
re-granted `SELECT` but the `hermes_v2` role was **missed**.
`walk_forward_monitor.service` runs as `User=hermes_v2` and its script
(`scripts/research/walk_forward_signal_analysis.py`) does `FROM sentiment` →
`psycopg.errors.InsufficientPrivilege: permission denied for table sentiment`.

**Scope check (live):** Of the 22 `hermes_ingestor`-owned tables in the
`hermes_v2` DB, the `hermes_v2` role can `SELECT` only `raw_ohlcv`. That looks
alarming but is **not** a fleak of live failures: `bronze-audit-daily` (ran
03:15 today) and `funnel_scoring` (ran 04:00 today) both exited `0` — they
don't touch the ingestor-owned tables `hermes_v2` lost. `sentiment` was the
only table any *surviving* hermes_v2 unit actually reads without access.
Deliberately did **not** blanket-grant the other 20 tables — minimal fix only.

**Fix applied:**
```sql
-- on hermes, hermes_v2 DB, as postgres
GRANT SELECT ON public.sentiment TO hermes_v2;
```

**Verified live after the grant:**
| Check | Result |
|---|---|
| `\dp public.sentiment` | now shows `hermes_v2=r/hermes_ingestor` |
| `information_schema.role_table_grants` | `hermes_v2 \| SELECT` present |
| `systemctl start walk_forward_monitor.service` | `code=exited, status=0/SUCCESS`, CPU 2.96s |
| `systemctl is-system-running` | `degraded` → **`running`** |
| `systemctl --failed` | empty |
| replication (primary side) | `streaming / async / 0` lag |

`walk_forward_monitor.timer` next run 2026-09-06 06:00 UTC — will now pass on
its own schedule.

### Other S14 residuals — actioned by decision, not by change

- **`/opt/hermes_v2` teardown** — re-verified the blocker list live (see Quick
  Resume §1). Still load-bearing. No safe action; left in place intentionally.
- **Cross-project disk items** — confirmed still present, still owned
  elsewhere, S14 notices already delivered. Nothing to do from here.
- **`temp_recovery_s23-pre-drop-s14.dump`** — 1.2 GB, dated hours before this
  session. Far too fresh to delete. Kept.

---

## 2. Cross-project notice written

**JR Hermes Ingestor** —
`docs/CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s15-sentiment-grant-applied.md`
(placed on the `s27-s28-audit-fixes` branch, alongside the S14 notice).
Informs Ingestor that JR Hermes VPS applied `GRANT SELECT ON public.sentiment
TO hermes_v2` directly (with the user's explicit one-time authorization) to
clear a live `degraded` host state, and asks Ingestor to fold that grant into
its own role/migration definitions so it isn't lost on the next ownership or
restore operation, and to decide whether the other 19 live `hermes_ingestor`-
owned tables `hermes_v2` can no longer read should be re-granted or left
(recommendation: leave — nothing surviving needs them).

---

## 3. Session side effects (disclosure)

- One manual `systemctl start walk_forward_monitor.service` run — produced its
  normal research output into `/opt/hermes_v2/data/research`, ~1 min of work,
  exit 0. No Telegram alert expected (success path).
- No reboot, no package changes, no config changes. Single SQL `GRANT`.

---

## 4. Open items for S16

All cross-project or time-gated — none actionable from JR Hermes VPS alone:

- **`/opt/hermes_v2` teardown** — needs a hermes_v2/Ingestor decommission
  decision to migrate/retire `bronze-audit-daily`, `funnel_scoring`,
  `server_health_audit`, `walk_forward_monitor`, `prometheus.service`.
- **Ingestor to absorb the `sentiment` grant** into its role definitions
  (notice sent) so it survives future restores.
- **Cross-project disk reclaim** (~5 GB total across Ingestor + Basic Crypto
  Signals + `hermes_v2` DB) — awaiting those projects.
- **`temp_recovery_s23-pre-drop-s14.dump`** — delete after end-of-September
  2026 grace period if still unneeded.
