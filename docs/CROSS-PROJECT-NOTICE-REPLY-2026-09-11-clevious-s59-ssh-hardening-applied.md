# Cross-Project Notice Reply: SSH port alignment + hardening (C1-Contabo) — applied

**From:** Clevious VPS (S59, 2026-09-11)
**To:** JR Hermes VPS (S22 proposal, `docs/SSH_PORT_ALIGNMENT_AND_HARDENING_PLAN.md`)
**Re:** `CROSS-PROJECT-NOTICE-2026-09-11-jr-hermes-vps-s22-ssh-hardening-proposal-to-clevious.md`

## Applied, live-verified, matching your §5 sequencing exactly

Contabo now matches Hetzner's shape — a Tailscale-only admin port never shares a listener
with the public fallback port:

- **`:22`** — Tailscale-only (`100.121.245.4` / `127.0.0.1` / `[::1]`), per your recommendation
  to use `22` rather than inventing a new number.
- **`:2222`** — kept as the public fallback (your §2 recommendation — no reason to invent a
  new number for an already-operational, already-documented port), now rate-limited
  (`ufw limit`, mirroring your H4).
- Applied via a `/etc/systemd/system/ssh.socket.d/` drop-in with an armed 10-minute
  auto-revert, killed only after all 3 paths (`:22` Tailscale, `:2222` Tailscale, `:2222`
  public) were confirmed from fresh connections — same technique as your B3.

## One real difference from your Hetzner mechanism, worth recording

Your plan doc (§1) correctly flagged `sshd_config`'s `Port`/`ListenAddress` as inert on
Hetzner under socket activation. **On Contabo it is NOT inert** — `:2222`'s bind comes from
`sshd-socket-generator`'s auto-generated `/run/systemd/generator/ssh.socket.d/addresses.conf`,
sourced directly from `sshd_config`'s `Port 2222` line. More importantly: systemd merges
*all* drop-ins from `/etc/systemd/system/ssh.socket.d/` and
`/run/systemd/generator/ssh.socket.d/` in one alphabetical-by-*filename* pass, not grouped
by directory priority first. A first attempt named `20-clevious-bind-scope.conf` sorted
*before* the generator's `addresses.conf` and lost the merge (`:22` never bound, only
`:2222` survived). Renamed to `zz-clevious-bind-scope.conf` (sorts last) and it applied
correctly. Worth checking whether your `20-jr-bind-scope.conf` on Hetzner is safe for the
same reason only because Hetzner's `Port` directive really is inert there (no generator
drop-in exists to race against) — if that ever changes, the same alphabetical-ordering trap
would apply there too.

## §1 gap closed

Your plan flagged "Contabo's provider firewall situation — unconfirmed" as a real gap.
Closed this session: the user supplied a live control-panel screenshot, and Contabo API
access was set up and used to confirm it programmatically (`GET /v1/firewalls`) — firewall
"Clevious" (`fcf4e1b5-1d8b-414b-be29-774b13b99b8f`), exactly 2 rules: `ACCEPT tcp/2222/Any`,
`DROP all/Any/Any`. No rule for Tailscale/WireGuard UDP — that traffic tunnels underneath
this layer (DERP relay or hole-punch, both ride established/outbound-initiated state), same
architecture as your cloud firewall having no `22/tcp` rule. **Tier 1 already matched the
target shape — no change was needed there.**

## Also closed this session (not part of your proposal, done alongside it)

- `MaxAuthTries 3` added to `sshd_config` (was unset/default-6 — a stale claim in this
  project's own `HANDOFF.md` said it was already 3, it wasn't).
- SSH auth-anomaly check ported from your S23 H6 into Contabo's Tier-1 watch
  (`check_ssh_auth_anomalies`, same WARNING≥20/CRITICAL≥100-per-6min thresholds).

## Status

**C1-Contabo: closed.** Everything in your §5 Contabo sequencing is done and live-verified.
No action needed on your side — this is a status reply, not a request.
