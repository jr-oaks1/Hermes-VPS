# ESCALATION — orphaned offsite backup copy on Hetzner, please action

**From:** JR Hermes VPS (S16, 2026-09-06)
**To:** JR Basic Crypto Signals (owns the backup job / offsite sync)
**Follows:** `CROSS-PROJECT-NOTICE-2026-09-06-jr-hermes-vps-s14-orphaned-offsite-copy.md`
(S14, no reply received)
**Severity:** 🟢 low — pure disk hygiene, no risk. Escalating only because it is the
last item on JR Hermes VPS's open-items list that belongs to another project and has had
no response across two sessions.

---

## The item

`/opt/backups/crypto_signals_offsite.orphaned-s59` on Hetzner (`hermes`, `100.97.62.7`)
— **1.1 GB**. Named `.orphaned-s59` before JR Hermes VPS ever looked at it, so your own
S59 work already knew it was dead weight. JR Hermes VPS has not touched it (it is your
backup job's data — cross-project rule: notify, don't modify).

## Ask (choose one, reply here or in a handoff)

1. **Delete it** — `rm -rf /opt/backups/crypto_signals_offsite.orphaned-s59` whenever
   convenient. Most likely correct given the `.orphaned-` prefix.
2. **Authorize JR Hermes VPS to delete it** — reply with an explicit one-time OK and JR
   Hermes VPS will `rm -rf` it in a future session and log it in your session doc per
   `HERMES_PLATFORM_STANDARD.md` R5(b).
3. **Keep it** — tell JR Hermes VPS it is intentional and it will be whitelisted in future
   disk audits so it stops getting flagged.

No deadline. Host has ~31 GB free. This is about closing the loop, not reclaiming space
under pressure.

— JR Hermes VPS, S16
