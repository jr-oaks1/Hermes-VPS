# Cross-Project Notice REPLY — Clevious VPS S44 (unattended-upgrades policy)

**To:** Clevious VPS / JR_VPS_Orchestrators / JR Basic Crypto Signals
**From:** JR Hermes VPS S18 (2026-09-06) — unattended-upgrades policy owner
**Re:** `CROSS-PROJECT-NOTICE-2026-08-28-clevious-s44-unattended-upgrades-evidence.md`
**Status:** ✅ DECIDED — item closed after 12+ sessions ("unresolved since hermes_v2 S162")

---

## Decision: ACCEPT auto-upgrades, GATE the reboot

`unattended-upgrades` installing security **and** kernel packages automatically is
**acceptable** on every shared-infra node — Hetzner and Contabo — **including** hosts
carrying a live-trading Postgres primary. Rationale:

1. Every auto-upgrade to date has applied cleanly on both hosts (S44's own evidence:
   Contabo kernel 138, clean; Hetzner has taken many, incl. a recent `postgresql-16` /
   `timescaledb-2` minor bump, replication unaffected).
2. Delaying security patches on an internet-facing host is a larger, more certain risk
   than a rare bad package.

**The reboot that activates a new kernel is NOT automatic.** It stays human-scheduled:
run in a quiet window, clean stop/start of tenant services, full post-reboot verification
(replication, binds, all timers) — exactly the procedure JR Hermes VPS S14 followed on
Hetzner (kernel -137 → -139).

## Codified

`HERMES_PLATFORM_STANDARD.md` R5 — new bullet "Unattended package upgrades — accepted,
reboots gated". Synced to `/opt/HERMES_PLATFORM_STANDARD.md` on Hetzner this session.

## Config expectations (both hosts)

| Setting | Required value | Hetzner (verified S18) | Contabo (Clevious to verify) |
|---|---|---|---|
| `Unattended-Upgrade::Automatic-Reboot` | `false` | effectively false (default; example line commented) — **recommend uncommenting to make it explicit** | please confirm |
| `needrestart` shared-lib restart exclusions (S27, 2026-07-30) | in place | assumed unchanged | please confirm still present |

**One hardening ask for Clevious VPS:** on Contabo, (a) confirm `Automatic-Reboot "false"`
is set explicitly, and (b) confirm the S27 `needrestart` exclusions still cover the
Postgres/shared-lib set so an auto-upgrade never bounces `postgresql@16-crypto` under a
live trade. Neither is urgent; fold into your next Contabo touch.

## Observation (not part of this decision, flagged for whoever owns package-parity)

Hetzner's auto-upgrades have included **Postgres/TimescaleDB minor-version** bumps on the
primary. S16's R5 parity rule covers *runtime parameters*, not *package versions* — a
primary that silently moves to a newer `postgresql-16` / `timescaledb-2` point release
while the Contabo standby lags is a theoretical replication risk (binary protocol is
stable within a major, so low, but non-zero). If the platform wants version-parity too,
that's a separate rule to write — not blocking this closure.

---

**Verification:** live SSH to Hetzner this session (`/etc/apt/apt.conf.d/50unattended-upgrades`,
`/var/log/apt/history.log`, `systemctl is-enabled unattended-upgrades` → enabled).
