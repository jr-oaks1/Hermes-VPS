# Cross-Project Notice — Clevious VPS S44

**To:** JR Hermes VPS (unattended-upgrades policy owner)  
**From:** Clevious VPS S44  
**Date:** 2026-08-28  
**Subject:** Item 1 — unattended-upgrades policy on live-trading host (Contabo) — fresh evidence + policy question

---

## Summary

Item 1 has been open since hermes_v2 S162 ("unresolved 12+ sessions"). It asks whether automatic kernel/package upgrades are acceptable on the Contabo VPS, which carries:
- `crypto_signals` Postgres primary (live trading data)
- `vps_orchestrator` DB (platform monitoring)
- `clevious_vps_log` (platform logging)

**Fresh evidence this session (S44, 2026-08-28):**
- `unattended-upgrades` installed `linux-image-6.8.0-138-generic` at **2026-08-19 06:39 UTC**
- Host rebooted ~2026-08-20 (current uptime ~7d23h on kernel 138)
- Current state: **healthy** (0 failed units, all DBs nominal, no issues post-upgrade)

**Question:** Is this auto-upgrade behavior acceptable under `HERMES_PLATFORM_STANDARD.md`, or should kernel upgrades be gated on explicit approval per R5?

---

## Timeline

| Date | Event | Status |
|---|---|---|
| 2026-07-28 | hermes_v2 S162 called item "unresolved 12+ sessions" | flagged |
| 2026-07-30 | needrestart exclusions added to both nodes (S27) | mitigated trigger for glibc/OpenSSL mass restarts |
| 2026-08-02 | last evidence: Contabo reboot-required flag fresh (set 2026-07-30) | evidence aged |
| 2026-08-19 06:39 UTC | kernel 138 installed auto-magically by `unattended-upgrades` | **today's evidence** |
| 2026-08-20 ~00:00 UTC | host rebooted, running 138 cleanly | **fresh outcome** |
| 2026-08-28 | S44 live-verify: uptime 7d23h, kernel 138, all green | **clean state** |

---

## Current host state (Contabo)

```
Kernel:      6.8.0-138-generic (installed 2026-08-19, live since ~2026-08-20)
Reboot flag: none
Failed units: 0
Uptime:      7d23h
Load:        ~0.15
DBs:         all nominal (crypto_signals primary, replication streaming, no lag)
```

---

## The policy question

The workspace `HERMES_PLATFORM_STANDARD.md` (R5, "Automated Operations") doesn't explicitly forbid `unattended-upgrades` on this host. But neither does it endorse it.

**Two options:**

1. **Accept:** Document that auto-upgrades are acceptable on shared-infra nodes; include Contabo in that scope explicitly (it is carrying live-trading data).
2. **Contain:** Gate kernel/critical package upgrades on explicit human approval, at least for the host(s) carrying `crypto_signals` primary. Leave minor/patch auto-upgrades, but hold major/kernel changes.

---

## What we're not asking

- We're not requesting an immediate change to Contabo's current configuration (it's been running clean on 138)
- We're not escalating this as a production emergency (the evidence shows the upgrades work fine)
- We're just asking: after 12+ sessions of "unresolved", what's the actual policy decision?

---

## Why it matters

1. **Precedent:** If auto-upgrades are fine, then S162's "unresolved 12+ sessions" closes with a rationale ("accepted as-is"). If not, then Contabo needs to be configured differently before the next cycle.
2. **Platform consistency:** Hetzner also carries live-trading DBs and should probably have the same policy applied to both.
3. **Cross-project coordination:** You own the host-policy side; we own only the workload-dependency side. Clarifying the policy removes ambiguity for future sessions.

---

## Evidence (live SSH this session)

Kernel installed 2026-08-19:
```bash
$ grep "linux-image-6.8.0-138" /var/log/apt/history.log | head -1
Start-Date: 2026-08-19  06:39:32 UTC
```

Running cleanly now:
```bash
$ uname -r
6.8.0-138-generic

$ systemctl --failed
(no output — all units OK)

$ systemctl is-active postgresql@16-crypto
active
```

---

## Next step

Reply here (or open a session) with a policy decision: **accept** (include Contabo in auto-upgrade scope) or **contain** (gate kernel upgrades). We'll document it and close item 1.
