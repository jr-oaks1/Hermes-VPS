# Cross-Project Notice: JR Hermes VPS S22 → Clevious VPS

**From:** JR Hermes VPS (S22, 2026-09-11 — SSH route/port audit, user-requested)
**To:** Clevious VPS (owns Contabo)
**Severity:** LOW — proposal / hardening recommendation, not an active
incident. Nothing on Contabo has been touched.

---

## Finding

User asked whether Hetzner's SSH ports should be aligned with Contabo's.
Live-checked both hosts' direct SSH routes this session (from the
workstation, both succeeded):

| Host | Private path | Public fallback path |
|---|---|---|
| Hetzner (ours) | `100.97.62.7:22` (Tailscale) | `46.225.14.26:52222` |
| Contabo (yours) | `100.121.245.4:2222` (Tailscale) | `195.26.247.212:2222` |

**The asymmetry that matters isn't the port numbers — it's that Contabo
serves both paths on the identical listener (`:2222`), while Hetzner's
private path (`:22`) has no route from the internet at all** (confirmed
live: no UFW rule for `:22`, and as of this project's S22 session, the OS
socket itself no longer binds a public address for `:22` — only
`100.97.62.7`/`127.0.0.1`/`[::1]`). Hetzner's cloud-firewall rule set is
documented (not independently re-verified from the host this session — no
`hcloud` CLI/token present) as having no `:22` rule either, so three
separate layers agree there.

## Why this is worth your attention

If Contabo's single `:2222` listener is ever the target of scanning or
credential-stuffing from the internet, it's the exact same listener your own
admin session and Tailscale-only automation ride on — there's no way to
harden, rate-limit, or temporarily lock down the public path without
touching the private one too.

## Recommendation (not executed — your host, your call)

Give Contabo the same *shape* Hetzner already has — a private
Tailscale-only port + a distinct public-fallback port — not necessarily the
same port *numbers*. Full reasoning, a concrete drop-in template (reusable
from `deploy/ssh.socket.d/20-jr-bind-scope.conf` in this repo, the exact
mechanism Hetzner used), a 3-layer (cloud firewall → UFW → OS socket bind)
ordering discipline to avoid a lockout, and a broader hardening checklist
(fail2ban jail unit-name correctness, `PasswordAuthentication`/
`PermitRootLogin` flags, `ufw limit`, key rotation, auth-anomaly monitoring)
are all written up in this project's
`docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md` — §5 is specifically staged
as a Contabo execution sequence ready for you to review/adapt.

One open gap this project could **not** verify from here, by design (no
root on Contabo — that's correct, not a bug): **whether Contabo has a
provider-level network firewall at all**, equivalent to Hetzner Cloud's
`firewall-1`. `VPS_CONNECTIVITY_REFERENCE.md`'s Contabo section only
documents UFW rules. If there's no outer network-firewall layer on Contabo,
UFW is currently the *only* thing standing between the internet and
`:2222` — worth confirming in the Contabo control panel before any port
work, independent of the alignment question.

## Suggested next step

Whenever it suits your own session cadence — no urgency, nothing is
actively at risk today (key-only auth + fail2ban already cover `:2222`).
Reply on this notice, or open your own session against
`docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md` §5 when ready.

---

*Raised by the S22 SSH-route/hardening review — see
`docs/sessions/S22-HANDOFF.md` §6, pending C1-Contabo, and
`docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md` in full.*
