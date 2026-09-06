# S16 Handoff — JR Hermes VPS

**Session type:** Close out every remaining pending. Escalate all cross-project
(hermes_v2 / Basic Crypto Signals) items to their owning projects for ownership
transfer. User pre-approved deleting the S14 safety dump with no grace period.

**Date:** 2026-09-06.

**Status:** 🟢 All items that can be closed from this project are closed or escalated.
Three host-side actions are staged and **blocked on SSH** (auto-mode classifier) —
listed in §3, one message sent to the user to unblock.

---

## Quick Resume for whoever opens S17

**Nothing is open that this project can act on without SSH.** Everything is either:
- **escalated** (cross-project ownership transfer notices sent + committed), or
- **staged, SSH-blocked** (§3) — pick these up first in S17 if not done by then.

Cross-project notices sent this session (all committed):

| To | File | Ask |
|---|---|---|
| JR Hermes Ingestor | `.../docs/CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s16-ESCALATION-hermes-v2-teardown-ownership.md` (pushed to `s27-s28-audit-fixes`) | Take ownership of all 5 remaining hermes_v2 teardown items |
| JR Basic Crypto Signals | `.../docs/CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s16-ESCALATION-orphaned-offsite-copy.md` (local commit `c0cac70`) | Delete / authorize / keep `crypto_signals_offsite.orphaned-s59` (1.1 GB) |
| Clevious VPS | `.../CROSS-PROJECT-NOTICE-REPLY-2026-09-06-jr-hermes-vps-s16-standby-parameter-parity.md` (local commit `0d68e59`) | Reply to S50: parity rule codified, Clevious owns detection, headroom bump ack'd |

Copies of all three are also in `JR Hermes VPS/docs/`.

---

## 1. Clevious VPS S50 — standby parameter-parity (🟠) — SHAPED + REPLIED

This was the one item S15 flagged as "JR Hermes VPS's to shape." Done:

1. **Parity discipline codified.** New binding bullet added to
   `HERMES_PLATFORM_STANDARD.md` §3 **R5** (workspace-root copy): any change to
   `max_connections` / `max_worker_processes` / `max_wal_senders` /
   `max_prepared_transactions` / `max_locks_per_transaction` on the Hetzner primary
   must raise the Contabo standby to a matching-or-higher value **in the same
   session**. Includes the failure mode (`FATAL: recovery aborted…`) and the
   2026-09-05 twice-in-a-day incident as rationale.
2. **Detection — accepted, Clevious VPS owns it.** They offered to add a
   primary↔standby diff of the five params to the Contabo Tier-1 watch (alert on
   `standby < primary`). Accepted in the reply. They confirm when live; this project
   then names it as the detection control in R5.
3. **Headroom — ack'd.** Clevious has the go-ahead to raise the standby's
   `max_wal_senders` (10→~16) and `max_locks_per_transaction` (512→~1024) —
   standby-only, no primary impact.

**Residual:** `/opt/HERMES_PLATFORM_STANDARD.md` on the host needs the same R5 edit
synced (footer rule: both copies in step). SSH-blocked — see §3.

## 2. hermes_v2 residue — fully escalated to JR Hermes Ingestor

S13→S15 carried these as "cross-project, not ours." S16 formally hands the whole set
to JR Hermes Ingestor (the designated successor role). Items in the escalation:

1. `/opt/hermes_v2` teardown — blocked on 5 units (`bronze-audit-daily`,
   `funnel_scoring`, `server_health_audit`, `walk_forward_monitor`,
   `prometheus.service`). Each needs migrate-or-retire decision.
2. `hermes_v2` DB (2.7 GB) — drop candidate, Ingestor's confirmation + call.
3. `sentiment` grant (S15's manual `GRANT SELECT … TO hermes_v2`) — fold into
   Ingestor's role/migration definitions or retire `walk_forward_monitor`.
4. `/opt/hermes-ingestor.backup-pre-s{25-phase0,27,27b,28}` (~1.76 GB) — Ingestor's
   own snapshots, safe to prune.
5. `prometheus.service` dead config-path reference — likely just delete the unit.

Asked for acknowledgement + rough sequencing in Ingestor's next session so these can
be struck from this project's open-items list.

## 3. Staged but SSH-BLOCKED (auto-mode classifier)

All three need `ssh root@100.97.62.7`. The `Bash` SSH call was denied by the
auto-mode classifier this session. One message sent to the user to disable auto mode
(per the AUTO-MODE BLOCK ground rule). Pick these up once unblocked:

1. **Delete `/root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump` (1.2 GB).**
   **User pre-approved this session — no grace period.** Command:
   ```bash
   rm -f /root/pre-drop-safety/temp_recovery_s23-pre-drop-s14.dump
   # then: rmdir /root/pre-drop-safety 2>/dev/null || true   # if now empty
   ```
2. **Sync `/opt/HERMES_PLATFORM_STANDARD.md`** with the R5 parity bullet added to
   the workspace-root copy this session (diff is the one new bullet between the
   "superuser identity…" line and `### R6`).
3. **Final host verification pass** for this handoff (not yet done this session):
   `systemctl is-system-running`, `systemctl --failed`, `df -h /`,
   replication state. S15 left it `running` / 58% / `streaming/async/0`.

## 4. Session side effects (disclosure)

- No host changes (SSH blocked). No DB changes. No reboots.
- `HERMES_PLATFORM_STANDARD.md` (workspace root, OneDrive-synced, not git-tracked) —
  R5 parity bullet added.
- 3 cross-project commits in sibling repos. The Basic Crypto Signals commit
  (`c0cac70`) also swept in two pre-existing untracked inbound notice files
  (`...2026-09-04-findings-log-practice.md`, `...2026-09-05-hermes-ingestor-S31-ownership-change.md`)
  that were sitting uncommitted in its `docs/` — benign (they belong in the repo),
  disclosed here for the record.
- Did **not** push Clevious VPS or Basic Crypto Signals — both had unpushed commits
  from concurrent sessions and OneDrive propagation is sufficient for notice
  delivery. Only JR Hermes Ingestor was pushed (my commit was the only unpushed one).

## 5. Open items for S17

- **§3 items 1–3** — the moment SSH is available.
- **Await replies:** Ingestor escalation (5 items), BCS escalation (orphaned-s59),
  Clevious detection-live confirmation.
- Once Clevious confirms the diff-check is live, add it to `HERMES_PLATFORM_STANDARD.md`
  R5 as the named detection control (currently written as "accepted S16").

## 6. Standing backlog surfaced from the platform standards (S16, logged not actioned)

User reviewed `ORGANIZATIONAL_STRUCTURE.md`, `VPS_CONNECTIVITY_REFERENCE.md`,
`GLOBAL_GROUND_RULES.md`, `CONTINUOUS_IMPROVEMENT_STANDARD.md` and asked what's still
unimplemented. These are **separate from the S13→S16 cleanup chain** — they've been
carried as "partial" since S71 and were logged here (user chose "log for S17", not
"action now"). None were verified live this session (SSH blocked); status is from the
standards docs + repo inspection + S13–S15 handoffs.

### 6a. Continuous Improvement Standard — tier rollout incomplete for JR Hermes VPS
`CONTINUOUS_IMPROVEMENT_STANDARD.md` §3 grades this project **"T1–T3 partial · T4 ❌"**.

| Gap | State | Action for S17+ |
|---|---|---|
| **Tier 4 — durable escalation** | ❌ not built | Add an `action_status` escalation ladder over `hermes_vps_log.findings_log` per Rules T4.1–T4.3 (CRITICAL unacked >2h → GM bot `@JRCleviousVPSBot`, >24h → CEO; state in the row, re-derived each cycle). **Biggest gap.** Design can be done without SSH. |
| **Tier 3 — full cadence** | ⚠️ weekly/monthly only | Standard wants boot-time + every 5–10 min read-only guardrail + success-heartbeat files (T3.10/T3.11). Currently only the weekly/monthly audit units. |
| **Tier 0 / Rule T0.2** (start limits) | ❓ unverified | All `deploy/*.service` are oneshot timer services → likely N/A, but confirm with a live `systemctl` pass that no long-running unit lacks `StartLimitIntervalSec`/`Burst`. |
| **Rule T-LOG.1** (log-as-you-go) | ⚠️ partial | Health check dual-writes via GM's `log_operational_finding.py`; no `log_finding.py`-equivalent for ad-hoc findings during live work. Low priority. |
| §3 row's S71 "severity-labelling + decommissioned-service defects" note | likely **stale** | S13-HANDOFF.md says fixed (hermes_v2 out of `SYSTEMD_SERVICES`, `disabled`-state handled, all-INFO exit 0). Update the standard's §3 row to match — needs a live health-check re-run to confirm before editing. |
| `/opt/CONTINUOUS_IMPROVEMENT_STANDARD.md` sync | recurring | Keep in step with root copy. |

### 6b. Hetzner Branch Manager self-report endpoint — doesn't exist
`ORGANIZATIONAL_STRUCTURE.md` §"Two-Channel Alert Escalation" line ~194: Contabo projects
POST alerts to `http://100.121.245.4:8002/self-report`; **"Hetzner projects: equivalent
Branch Manager endpoint (future)."** No Hetzner equivalent exists. Ownership is ambiguous
— JR Hermes VPS is the Hetzner Branch Manager, but the collector backing Contabo's
endpoint is GM-owned (JR_VPS_Orchestrators). **S17: send GM a one-line clarification
notice — who builds it — before anyone specs it.**

### 6c. Standing tri-copy sync obligations (recurring housekeeping)
- `HERMES_PLATFORM_STANDARD.md` — root (edited S16) + `/opt/` (Hetzner). `/opt/` sync in §3.
- `CONTINUOUS_IMPROVEMENT_STANDARD.md` — root + `/opt/` (Hetzner).
- `VPS_CONNECTIVITY_REFERENCE.md` — root + `JR Hermes VPS/docs/` + `/opt/` (Hetzner).

`GLOBAL_GROUND_RULES.md` — nothing to implement (behavioral); this session complies.
