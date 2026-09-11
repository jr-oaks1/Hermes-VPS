# SSH Port Alignment + VPS Hardening Plan — Hetzner ↔ Contabo

**Status:** 🟡 PROPOSAL — nothing in this document has been applied. Hetzner
sections are ours to execute (JR Hermes VPS) on explicit go-ahead, staged +
smoke-tested per the SMOKE-TEST BINDING RULE. Contabo sections are **not
ours to touch** — Contabo is Clevious VPS's host; this plan proposes what
that project should pick up, and a cross-project notice should carry this
document over once reviewed here.
**Origin:** S22 (2026-09-11) forensic-audit follow-up, user question: "should
Hetzner's SSH ports be aligned with Contabo's?"
**Verified this session:** everything under §1 (Hetzner) is live-checked.
Contabo facts are a mix of live-checked (as the unprivileged `clevious` user
— no root available from here, by design; Contabo is another project's host)
and doc-sourced (`docs/VPS_CONNECTIVITY_REFERENCE.md`) — each is labeled.

---

## 1. Current state, verified

### Hetzner (`hermes`, ours)

| Layer | Config | Verified how |
|---|---|---|
| Cloud network firewall (`firewall-1`, Hetzner Cloud console) | 5 inbound rules: ICMP, `80/tcp`, `443/tcp`, `41641/udp`, `52222/tcp`. No `22/tcp` rule at all — the cloud firewall itself never lets port 22 traffic reach the host from the internet. | **Doc-sourced only** (`VPS_CONNECTIVITY_REFERENCE.md` §13.2, dated S28) — no `hcloud` CLI or API token exists on the host itself (checked this session), so this could not be independently re-verified live. Recommend a 2-minute console check before relying on this for a decision. |
| Host firewall (UFW) | `:22` — no explicit allow rule at all (relies on the `tailscale0`-interface catch-all, not a `:22`-specific rule); `:52222` — explicit `ALLOW IN` on both IPv4 and IPv6, tagged "S27 public SSH fallback". | ✅ Live, `ufw status verbose`, this session. |
| Socket bind (the actual OS-level listener) | `:22` → `100.97.62.7` + `127.0.0.1` + `[::1]` only (no `0.0.0.0`/`[::]`). `:52222` → `0.0.0.0` + `[::]`. | ✅ Live, `ss -tlnpe`, this session (this is the S22 `ssh.socket.d/20-jr-bind-scope.conf` change). |
| Auth | key-only, `fail2ban` jail `sshd` watching `_SYSTEMD_UNIT=ssh.service` (the S26 fix — the pre-S26 filter watched the wrong systemd unit and could never ban), 0 banned, 0 failures/recent. | ✅ Live, `fail2ban-client status sshd`, this session. |

**Net effect on Hetzner: three independent layers already narrow `:22` to
nothing the internet can reach** — no cloud-firewall rule, no UFW rule, and
now (S22) not even an OS socket bound to a public address. `:52222` is the
sole internet-facing SSH surface, and it's the *only* one that needs to
carry the weight of "what if `:22`/Tailscale is ever compromised or down."

### Contabo (`clevious-vps`, **Clevious VPS's host, not ours**)

| Layer | Config | Verified how |
|---|---|---|
| Cloud/provider network firewall | Not established this session. Contabo's control panel does offer a network-level firewall on some plans, but nothing found in this workspace's docs confirms one is configured for this VPS specifically — `VPS_CONNECTIVITY_REFERENCE.md`'s Contabo section only documents UFW rules, no provider-firewall row. | ❌ **Unverified — this is a real gap in the picture, not an answer.** Needs checking directly in the Contabo control panel (not SSH-visible) or confirmation from Clevious VPS's own docs. **Do not assume Contabo has an equivalent outer layer to Hetzner's cloud firewall until this is confirmed.** |
| Host firewall (UFW) | Not independently re-verified this session (no root — see below). Per `VPS_CONNECTIVITY_REFERENCE.md`: `2222/tcp` allowed on **both** `tailscale0` and `eth0` (i.e. both the private and the public path), key-only + fail2ban (`bantime=3600`, `maxretry=4`). | Doc-sourced (S27). |
| Socket bind | `ssh.socket` confirmed `enabled` + active, `ssh.service` confirmed `disabled` (same socket-activation architecture as Hetzner — meaning `sshd_config`'s `Port`/`ListenAddress` are almost certainly inert here too, same as the Hetzner lesson from S22). No `/etc/systemd/system/ssh.socket.d/` override directory exists — so whatever puts `:2222` on both interfaces is either baked into a full replacement `ssh.socket` unit, or a vendor-path drop-in this session didn't check. | ✅ Partially live (socket-activation fact) — the exact bind mechanism needs root to confirm (`ss -tlnpe`), which this session correctly does not have on another project's host. |
| Auth | Key-only, `clevious` user; root access requires a password this session doesn't have (as it should — self-containment). | ✅ Live (this session's own connection attempt confirmed key-only + a non-root low-priv user is the normal login identity). |

**The one fact that matters most for your question: Contabo really does put
its private (Tailscale) and public (internet) SSH paths on the identical
port, `2222`, with no OS-level separation between them** — that's the live
architecture, not a doc artifact.

---

## 2. The actual asymmetry, and my recommendation

Port-number *sameness* across the two hosts is not itself a security
property — nothing reads worse because Hetzner says `52222` and Contabo says
`2222`. What matters is whether **the port serving internet traffic is a
distinct listener from the port serving only trusted-network (Tailscale)
traffic.** On that axis:

- **Hetzner already has the safer shape**: `:22` is Tailscale-only at three
  independent layers (cloud firewall has no rule for it, UFW has no rule for
  it, and the socket doesn't even bind a public address); `:52222` is the
  sole internet-facing listener and can be tightened, rate-limited, or killed
  outright without touching the admin path.
- **Contabo has the riskier shape**: one listener, `:2222`, serves both. If
  that listener needs hardening (say, a stricter `fail2ban` policy, or a
  temporary lockdown during an incident), there is no way to do it for the
  public path without also affecting the private one — and if that port is
  ever the target of a credential-stuffing run from the internet, the exact
  same listener is what your own admin session rides on.

**My recommendation: harden Contabo to match Hetzner's *shape* (a
Tailscale-only private port + a separate public-fallback port), not
necessarily Hetzner's *numbers*.** Collapsing Hetzner down to Contabo's
single-port model (Option B) would be a real regression — it throws away
work this project already did (S22) and the separation of concerns it
buys, purely for cross-host cosmetic symmetry. Symmetry that matters is
**"both hosts separate private-from-public SSH,"** not "both hosts use the
digit `2222`."

Suggested target state:
- **Contabo private path**: `22/tcp`, Tailscale-only (mirrors Hetzner's
  convention exactly — same runbook muscle-memory: "22 is always the
  Tailscale-only admin port on either host").
- **Contabo public fallback**: keep `2222/tcp` (already the operational
  reality, already in every doc, no reason to invent a new number) — but
  bound only on the public interface, with no `:22` overlap.
- **Hetzner**: unchanged (already in the target shape as of S22).

This is a proposal for Clevious VPS to evaluate and own the execution of —
their host, their session, their smoke-test. What follows is written so that
document can be handed over largely as-is.

---

## 3. Two-tier firewall — confirm before touching anything

You're right that both hosts have two layers, and any port change must be
staged through *both*, in the right order:

1. **Network/cloud firewall (outermost, first point of contact)** — Hetzner
   Cloud's `firewall-1` (console-edited); Contabo's equivalent is
   **unconfirmed** (§1). A port must be open here *and* in UFW for external
   traffic to arrive at all — closing here without also handling UFW is
   pointless (traffic already can't arrive); opening a new port here before
   sshd is listening on it is safe (nothing behind it yet) — so this is the
   layer to open **first**, then bind, then verify, then close the *old*
   port here **last**, after the new one is proven.
2. **Host firewall (UFW)** — mirrors the network firewall's rule set; same
   ordering logic (open new, prove it, close old).
3. **OS socket bind** (the actual listener, not a firewall at all) — this is
   the layer S22 discovered was the *real* control on Hetzner
   (`sshd_config`'s `Port`/`ListenAddress` are dead weight under socket
   activation; `ssh.socket`'s `ListenStream=` is truth).

**Any port change is a 3-layer, ordered operation on each host — get any
one layer wrong (e.g. close the network firewall before the new listener is
proven) and you lock yourself out with no path back except out-of-band
console access.**

---

## 4. Proposed hardening checklist (both hosts, beyond ports)

| # | Item | Hetzner (ours) | Contabo (Clevious VPS's) |
|---|---|---|---|
| H1 | Confirm the cloud/network firewall config directly in each provider's console (not from docs) before any port work | Recommended pre-check | Recommended pre-check — **also first establish whether Contabo has a provider firewall layer at all** |
| H2 | `fail2ban`: confirm the `sshd` jail watches the correct systemd unit under socket activation on **both** hosts (Hetzner's S26 fix: `_SYSTEMD_UNIT=ssh.service`, not `sshd.service`) | ✅ already correct (verified S22 audit) | Needs a live check — same failure mode is plausible if Contabo's jail filter was copied from an older template |
| H3 | `sshd_config`: `PasswordAuthentication no`, `PermitRootLogin` scoped to key-only (`prohibit-password`, not bare `yes`) | Needs a explicit live re-check (not done this session) | Needs a live re-check |
| H4 | Rate-limit / connection-count on the public SSH port at the UFW layer (`ufw limit`) in addition to fail2ban | Not currently using `ufw limit` on `:52222` (plain `ALLOW`) — worth adding | Same recommendation once the port split lands |
| H5 | SSH key rotation cadence — no expiry policy currently documented for either host's admin keys | Open question, no current policy | Same |
| H6 | Auth-anomaly monitoring folded into the existing Tier 3/4 observability stack (this project already has `hermes_vps_guardrail.py` / `hermes_vps_escalation_check.py`) — a new check counting recent SSH auth failures per source could feed `findings_log` the same way | Natural fit, low effort, this project owns the mechanism | Clevious VPS would need its own equivalent hook, or feed Hetzner's if a cross-host pattern already exists |
| H7 | Document the *shape* (not just the numbers) as a binding convention once agreed — add a short rule to `HERMES_PLATFORM_STANDARD.md` or a new cross-project doc: "SSH: Tailscale-only admin port never shares a listener with the public fallback port, on any host" | Codify here or workspace-root | Same document, shared |

---

## 5. Execution sequencing (if approved)

**Contabo (not ours — proposal only, hand to Clevious VPS):**
1. Confirm/establish the provider firewall situation (§1 gap).
2. Stage a `ssh.socket.d` drop-in (same technique as `deploy/ssh.socket.d/20-jr-bind-scope.conf` in this repo — reusable template) binding `:22` to Contabo's Tailscale IP + loopback only, leaving `:2222` on the public interface.
3. Open `22/tcp` on Contabo's UFW for `tailscale0` only (parallel rule, don't touch `:2222` yet).
4. Apply the socket drop-in with an armed auto-revert (mirror the S22 runbook), verify **both** a fresh `:22`-via-Tailscale connection and the existing `:2222` connection succeed, then disarm.
5. Only after that holds for a burn-in period, decide whether to also narrow `:2222`'s UFW rule to public-only (dropping its Tailscale duplicate, now redundant since `:22` covers that path) — this step is optional and lower priority.

**Hetzner (ours — already in target shape):**
- No port change needed. Optional hardening items from §4 (H3 explicit re-check, H4 `ufw limit`, H6 auth-anomaly check) can be scheduled as their own small, independently smoke-tested changes whenever you want them — none are urgent given the current three-layer posture.

**Cross-project step:** once you're happy with this document, the natural
next move is a cross-project notice to Clevious VPS handing over §2's
recommendation, §3's ordering discipline, and §5's Contabo sequencing as a
ready-to-review starting point — mirroring how the S16 Clevious-parity rule
and the S20 `parity_reader` role were handed across projects previously.

---

## 6. Open questions for you before anything is finalized

1. Confirm you want **Contabo's private port to become `22`** (matching
   Hetzner's convention) rather than some other non-default number — some
   would argue *any* non-well-known port for the private path adds a
   trivial layer of obscurity even though it's Tailscale-only; I don't think
   that's worth the inconsistency, but it's your call.
2. Do you want this plan hardened first as a doc-only cross-project notice
   (Clevious VPS reviews and executes on their own timeline), or do you want
   me to also do the Hetzner-side confirmation work (H3, live re-check of
   `sshd_config` hardening flags) as a small follow-up in this project now?
