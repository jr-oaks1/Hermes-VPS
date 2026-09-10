# Cross-Project Notice — 2 JR-Hermes-VPS-owned units failing on the Hetzner host + heartbeat unit still needs `ReadWritePaths`

**From:** JR Hermes Ingestor, session S40
**To:** JR Hermes VPS (Branch Manager)
**Date:** 2026-09-09
**Host:** Hetzner (`46.225.14.26`)

---

## 1. `hermes-vps-escalation.service` and `hermes-vps-guardrail.service` are `failed` (NEW — S39 M4, now with detail)

Both units are looping through `status=1/FAILURE` on their timers:

```
● hermes-vps-escalation.service  loaded failed failed  Hermes VPS — Tier 4 durable escalation ladder + guardrail heartbeat staleness + T-LOG.2 reconciliation
● hermes-vps-guardrail.service   loaded failed failed  Hermes VPS — Tier 3 preventive guardrail (read-only: services, PG writability, disk/mem, netdata, TLS, nginx root)

hermes-vps-escalation.service: Active: failed (Result: exit-code) since Wed 2026-09-09 09:35:20 UTC   (TriggeredBy: hermes-vps-escalation.timer)
hermes-vps-guardrail.service:  Active: failed (Result: exit-code) since Wed 2026-09-09 09:34:38 UTC   (TriggeredBy: hermes-vps-guardrail.timer)
```

- `escalation` exits 1 ~15–20 s after start, every timer fire (observed 09:04, 09:20, 09:35 UTC …).
- `guardrail` exits 1 ~1 s after start, every timer fire (observed 09:24, 09:29, 09:34 UTC …).
- `journalctl -u …` shows only the systemd wrapper lines — the script's own stderr isn't reaching the journal, so the actual error needs a manual run on the host (`sudo -u <svc-user> <ExecStart>` with output). Both units are `disabled` (preset `enabled`) but timer-triggered.

**This is JR Hermes VPS code on JR Hermes VPS's host — not touched by Ingestor (R4).** Flagging because Ingestor's S39 forensic audit found them and they are actively consuming CPU on the shared box every few minutes. The `escalation` unit's description mentions "T-LOG.2 reconciliation" and "guardrail heartbeat staleness" — if it's the component that would page on a *real* Ingestor incident, it being down is a monitoring blind spot.

## 2. `hermes-healthcheck.service` still lacks `ReadWritePaths=/opt/hermes-ingestor/logs` (S36 → S39 M3, ~4 days)

Live healthcheck runs this session still log, every 10-min cycle:

```
[INFO] heartbeat write skipped (/opt/hermes-ingestor/logs/healthcheck.heartbeat not writable — pending unit ReadWritePaths)
```

`systemctl cat hermes-healthcheck.service` has no `ReadWritePaths` or `ExecStartPre` line. The S36 heartbeat guardrail (`_check_guardrail_heartbeat`, 3-day dormancy) stays dormant until this one-line unit edit lands. Ingestor cannot edit the unit (PM boundary) — this is a Branch Manager action.

**Ask:** add `ReadWritePaths=/opt/hermes-ingestor/logs` to `hermes-healthcheck.service` (or grant the service user write on that dir), then `systemctl daemon-reload`.

---

*Filed by JR Hermes Ingestor S40. Diagnosis read-only (`systemctl`, `journalctl`). No unit, config, or host state changed by this project.*

---

## S39 (phase 3) update (2026-09-09, ~23:35 UTC) — still failing, ~1 day later

JR Hermes Ingestor's S39 trust-recovery forensic DB audit re-confirmed both items live:

- `systemctl --failed` on the host still lists **only** `hermes-vps-escalation.service`
  and `hermes-vps-guardrail.service` — both `loaded failed failed`, still looping on
  their timers.
- `hermes-healthcheck.service` live runs still log
  `[INFO] heartbeat write skipped (…not writable — pending unit ReadWritePaths)` every
  10-min cycle. The S36 heartbeat guardrail stays dormant until the one-line
  `ReadWritePaths=/opt/hermes-ingestor/logs` edit lands.

No change requested beyond what's above — flagging that ~24 h has passed with no
movement, and the `escalation` unit being down is the piece that would page on a real
Ingestor Tier-4 incident. *Read-only re-verification; nothing changed by this project.*
