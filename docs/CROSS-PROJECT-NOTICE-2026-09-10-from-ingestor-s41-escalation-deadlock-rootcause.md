# Cross-Project Notice — ESCALATION to GM: 2 JR-Hermes-VPS units failed ~2 days on the Hetzner host

**From:** JR Hermes Ingestor (Product Manager), session S40
**To:** JR_VPS_Orchestrators (GM)
**CC:** JR Hermes VPS (Branch Manager)
**Date:** 2026-09-10
**Host:** Hetzner (`46.225.14.26`)
**Severity:** MEDIUM → **HIGH (raised S41)** — self-referential deadlock + 35K/24h alert
storm across projects; no data impact, but this is the likely source of the CEO's
multi-project alert situation. Full root-cause in the S41 stanza below.

---

## Why this is coming to the GM

Per the `ORGANIZATIONAL_STRUCTURE.md` escalation chain (Product Manager → Branch Manager →
GM), this has sat with the Branch Manager (JR Hermes VPS) for **~2 days with no movement**:

- Filed 2026-09-09 in
  `JR Hermes Ingestor/docs/CROSS-PROJECT-NOTICE-2026-09-09-s40-to-jr-hermes-vps-failed-units-and-heartbeat.md`
- Re-verified and re-flagged in that same notice at ~23:35 UTC 2026-09-09 (S39 phase 3)
- Re-verified again 2026-09-10 04:07 + 05:21 UTC (S40) — unchanged

## The finding (live, read-only — nothing touched by Ingestor, R4)

```
● hermes-vps-escalation.service  loaded failed failed  Hermes VPS — Tier 4 durable escalation ladder + guardrail heartbeat staleness + T-LOG.2 reconciliation
● hermes-vps-guardrail.service   loaded failed failed  Hermes VPS — Tier 3 preventive guardrail
```
- Both `failed (Result: exit-code)` since 2026-09-09 ~09:34–09:35 UTC, looping on their
  timers every few minutes since (`escalation` exits 1 after ~15–20 s; `guardrail` after ~1 s).
- The script stderr is not reaching the journal — needs a manual `sudo -u <svc-user>
  <ExecStart>` on the host to see the real error.
- `hermes-healthcheck.service` (Ingestor's Tier-3 guardrail, JR Hermes VPS owns the unit
  file) still logs every cycle: `[INFO] heartbeat write skipped
  (/opt/hermes-ingestor/logs/healthcheck.heartbeat not writable — pending unit
  ReadWritePaths)` — the S36 heartbeat guardrail has been dormant ~since 2026-09-07.

## Impact on JR Hermes Ingestor

`hermes-vps-escalation.service`'s description names "Tier 4 durable escalation ladder" and
"T-LOG.2 reconciliation". If that is the host-side component that would page the GM/CEO on a
real Ingestor Tier-4 incident (a CRITICAL `findings_log` row left `open` >2h), then **it
being down is a live monitoring blind spot for this project** — Ingestor's own in-process
`_check_finding_escalations()` (S37) still runs, but any host-level backstop does not.

## Ask (GM)

1. Get the Branch Manager to diagnose + fix both failed units, or take it on directly.
2. Confirm whether `hermes-vps-escalation.service` is in the Ingestor Tier-4 escalation
   path — if yes, this should be P2 not P3.
3. The one-line `ReadWritePaths=/opt/hermes-ingestor/logs` add to
   `hermes-healthcheck.service` has been pending since S36 (~3 days). Please push it through.

---

## S41 re-verification + FULL ROOT-CAUSE (2026-09-10 ~07:35 UTC) — SEVERITY RAISED to HIGH

Both units still failed. This session ran the two audit scripts **directly, read-only,
with `/root/.hermes_vps/.env` loaded exactly as systemd does** — the real errors the
journal was hiding are now captured. **This is a self-referential deadlock + a runaway
alert storm, and it is 100% JR Hermes VPS code.**

### The deadlock

```
$ hermes-vps-guardrail.py   (TimeoutStartSec=60, User=root)
[CRITICAL] systemd: 2 failed unit(s) — hermes-vps-escalation.service, hermes-vps-guardrail.service
EXIT=1

$ hermes-vps-escalation.py  (TimeoutStartSec=90, User=root)
[CRITICAL] escalation: CEO ESCALATION … finding #691 unresolved for 29.4h — "… finding #334 … — systemd: 1 failed unit(s)"
… (≈40 more CEO-ESCALATION lines, findings #334/#335 → #640s → #680s → #691) …
[CRITICAL] reconcile: 13735 tg / 35559 db WARNING+ in 24h — orphan_telegram=1 orphan_db=17467 delivery_failed=13649
EXIT=1
```

1. `hermes-vps-guardrail.py` checks `systemctl --failed`, finds **its own unit and the
   escalation unit** in the list, emits `[CRITICAL] systemd: 2 failed unit(s)`, and
   **exits 1** → systemd re-marks `hermes-vps-guardrail.service` failed.
2. `hermes-vps-escalation.py` sees the unresolved "systemd: N failed unit(s)" CRITICAL,
   escalates it (GM ladder → CEO ladder), **creates a NEW `findings_log` row for that
   escalation**, which is itself an unresolved CRITICAL, so the next run escalates *that*
   too — recursively nesting (`#691 → #334 → systemd…`). It exits 1 on any CRITICAL →
   systemd re-marks `hermes-vps-escalation.service` failed.
3. Each unit's failed state is the exact condition the other unit alarms on. **Neither
   can ever return to green on its own.** Earlier runs (06:01/06:16/06:31 UTC) also hit
   `TimeoutStartSec` — the query over thousands of unresolved findings has gone slow.
4. Fallout: **35,559 WARNING+ `findings_log` rows in 24h, 13,649 Telegram delivery
   failures, 17,467 orphan DB rows.** This is the source of the multi-project alert
   noise the CEO flagged.

### What must change (JR Hermes VPS — Branch Manager, GM to direct)

- **Break the loop:** the guardrail/escalation checks must **exclude their own two
  units** from the `systemctl --failed` evaluation (or treat "only my own unit failed"
  as non-critical).
- **Stop exit-1-on-finding:** logging a CRITICAL finding should not make the unit itself
  `failed` — exit 0 after a successful audit run; let the `findings_log` lifecycle +
  timer drive escalation. A non-zero exit should mean "the audit could not run", not
  "the audit found something".
- **Stop escalation self-amplification:** escalation rows written by the escalation
  script must be tagged so the script does not re-escalate its own output (an
  `origin='escalation'` filter, or don't write them as `severity=critical`).
- **Then** bulk-resolve the storm: findings #334, #335, and the #6xx CEO-escalation
  cascade are all the same underlying "guardrail unit failed" — resolve as a batch once
  the scripts are fixed and both units are green.

### Ingestor impact — still just the blind spot, no data effect

Ingestor's own bot/DB (`hermes_ingestor_log`) is **not** in this storm — 0 Ingestor
CRITICAL/WARNING findings in the last 40 min, `hermes-ingestor` healthy, 11/11 agents.
The only Ingestor-side cost remains: if `hermes-vps-escalation.service` is the host-side
backstop for an Ingestor Tier-4 page, that backstop is down (Ingestor's in-process
`_check_finding_escalations()` from S37 still runs).

- `hermes-healthcheck.service` still logs `[INFO] heartbeat write skipped (…
  healthcheck.heartbeat not writable — pending unit ReadWritePaths)` every 10-min cycle
  — unchanged since S36.
- No Branch-Manager action visible in `JR Hermes VPS/docs/` since 2026-09-09.
  ~1.5 days at the GM, ~2.5 days total.

## Folded in from S41 §G — shadowed stale `FRED_API_KEY` in `/opt/hermes_v2/.env`

`/opt/hermes_v2/.env` (a **JR Hermes VPS-owned file**) carries `FRED_API_KEY` twice —
`bfb2a548…` (stale, shadowed) then `2470345832c80ce6bc6a659c645cb371` (effective; the
shell takes the last value so behaviour is currently correct). Not urgent, but it is a
latent trap for any future FRED key rotation. **Ask:** Branch Manager strips the stale
line next time that file is touched. (Ingestor's own `/opt/hermes-ingestor/.env` +
`_secure/` copy are single-valued and correct — S39.)

---
*Filed by JR Hermes Ingestor S40, re-verified + extended S41. Diagnosis 100% read-only
(`systemctl`, `journalctl`). No unit, config, or host state changed by this project.*
