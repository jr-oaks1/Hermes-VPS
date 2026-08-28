# Cross-Project Notice — Hermes VPS (S40)

**To:** JR Hermes VPS  
**From:** Clevious VPS S40  
**Date:** 2026-08-28  
**Priority:** P2 (Tier-3 preventive guardrail verification)  
**Action:** Verify readiness gates for `postgresql@16-crypto` on Contabo; test at next reboot

---

## Summary

The `postgresql@16-crypto` cluster (the `:5434` primary on Contabo, owned by JR Basic Crypto Signals
with readiness gates built by JR Hermes VPS S27) has **ExecStartPre gates configured in systemd
but never proven at runtime** (no reboot test since deployment).

This is a **Tier-3 preventive guardrail verification gap** in the Continuous Improvement Standard (S94).

---

## What exists

- `/etc/systemd/system/postgresql@16-crypto.d/99-readiness.conf` exists with `wait-for-ip.sh` gate
- The gate is supposed to ensure the cluster starts bound to the right addresses (`127.0.0.1`, `172.20.0.1`, `100.121.245.4`, `10.77.0.2`, `::1`)
- No forced-to-localhost regression documented

---

## What needs verification

At the next planned reboot of Contabo (tracking item P1-2, currently overdue):
1. Reboot the host
2. Monitor the boot: `journalctl -u postgresql@16-crypto.service | grep -E "ExecStartPre|Started|failed"` to confirm the gate ran and passed
3. After boot, verify the bind-address:
   ```
   ss -tlnp | grep -E '5434|5432'
   ```
   Confirm `:5434` is NOT bound to 127.0.0.1 only (no localhost-only regression).
4. Run a test write to confirm the DB accepted connections post-boot:
   ```
   psql -U crypto_writer -d crypto_signals -c "INSERT INTO ... VALUES (...)"
   ```
5. Document the result in a handoff or update to this notice.

---

## Tier-3 context

Part of the preventive guardrails slice of the CI Standard (Tier 3):
- Boot-time checks should catch infrastructure broken at startup *before* it cascades
- Readiness gates (ExecStartPre) + systemd dependency ordering are examples
- Verification = running the check (reboot) and confirming it works

---

## Background

- **S27 readiness gates deployed:** JR_VPS_Orchestrators S27 added `wait-for-ip.sh` gate to both Postgres clusters, designed to catch post-reboot localhost-only mis-bind (VPS_CONNECTIVITY_REFERENCE §12.3)
- **Never tested at runtime:** Contabo hasn't been rebooted since deployment, so the gate's actual behavior is unverified
- **S40 CI Standard adoption:** bringing this gap to your attention as part of the Tier-3 verification pass
