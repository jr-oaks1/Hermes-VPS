# Cross-Project Notice: JR Hermes VPS S21 → JR Hermes Ingestor

**From:** JR Hermes VPS (S21, 2026-09-10)
**To:** JR Hermes Ingestor
**Severity:** INFO — housekeeping done on your behalf, on explicit user
authorization. Nothing broken; recording it so you're not surprised.

---

## What was deleted on the Hetzner host (user-approved disk cleanup, S21)

**1. Stale Ingestor deploy-rollback snapshots under `/opt/` (~2.6 GB):**

| Removed | Date |
|---|---|
| `/opt/hermes-ingestor.backup-before-s25-phase0` | Aug 31 |
| `/opt/hermes-ingestor.backup-pre-s27` | Aug 31 |
| `/opt/hermes-ingestor.backup-pre-s27b` | Sep 4 |
| `/opt/hermes-ingestor.backup-pre-s28` | Sep 4 |
| `/opt/hermes-ingestor-pre-s14` | Aug 27 |
| `/opt/hermes-ingestor-pre-s16-health` | Aug 30 |

Rationale: all superseded, your live deploy `/opt/hermes-ingestor` is clean at
`f064750` (`main`, in sync with origin) and every one of these predates it — a
rollback target is `git checkout`, not a 440 MB tree copy. **`/opt/hermes-ingestor-staging`
was NOT touched** (it was modified today — active worktree).

This was the item escalated to you in JR Hermes VPS S16 (~1.76 GB then, grown
since). Consider it closed.

**2. `/opt/backups/hermes_v2/manual/` (~2.4 GB) — your S68 repair safety dumps:**

| Removed | Date |
|---|---|
| `pre-s68-repair.dump` (1.25 GB) | Sep 2 |
| `s68-verified-checkpoint-20260902_080313.dump` (1.24 GB) | Sep 2 |
| `raw_onchain_pre_widen_20260812_010225.dump` + `.csv` | Aug 12 |

Rationale: the S68 `hermes_v2` DB repair is 8 days done and has its own
`verified-checkpoint`; the routine automated backup covers `hermes_v2` with
**7 daily dumps locally + 7 off-site on Contabo**. The `manual/` subdir is now
empty and removed. If you still want a frozen pre-repair snapshot, re-dump from
the current DB or pull the Sep 2 automated dump from Contabo before its 7-day
window rolls.

## Recommendation

Going forward, drop deploy-rollback snapshots into `/opt/backups/` under a
retention-managed path, or skip them entirely and rely on git — a bare
`/opt/hermes-ingestor.backup-pre-sNN` with no cleanup is what accumulated 6 deep.

---

*S21 forensic-audit cleanup — see `docs/sessions/S21-HANDOFF.md` §4b (B1/B2).*
