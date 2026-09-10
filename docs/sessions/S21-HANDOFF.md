# S21 Handoff — JR Hermes VPS

**Date:** 2026-09-10
**Session type:** Close the last owned pending (P2) → deep forensic audit →
user-authorized host disk cleanup.
**Numbering:** user first said "session 20"; `S19-HANDOFF.md` + `S20-HANDOFF.md`
already existed on disk (2026-09-07, the Clevious-driven `parity_reader`
sessions), and `S19b-HANDOFF.md` (2026-09-10) said to verify disk and expect S21
— confirmed with the user → **this session is S21**. `S19`/`S20` untouched.
**Next handoff = S22.**

**Status:** 🟢 DONE. **No JR-Hermes-VPS-owned pending remains open.**
Host `running`, 0 failed units, **0 open/in_progress findings**, replication
`streaming/async/0`, disk **47%** (was 54%), `deploy_guardrail.sh` 9/9.
`/opt/hermes-vps` deploy clone synced to `main` HEAD (`b2bf521`).

---

## Quick resume for next session (S22)

**Nothing owned is open.** Sanity checks:
```
systemctl is-system-running                         # running
systemctl --failed                                  # empty
bash /opt/hermes-vps/scripts/deploy_guardrail.sh    # all 9 green
psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT action_status,count(*) FROM findings_log WHERE action_status IN ('open','in_progress') GROUP BY 1"   # 0 rows
```
Then look at the **pendings table in §4** — every item is another project's or
needs a user decision.

---

## 1. P2 — PostgreSQL roles table reconciled (the S19b pending)

Rewrote `### PostgreSQL roles` in `docs/VPS_CONNECTIVITY_REFERENCE.md` §5 (was
~9 mixed-host rows, self-admittedly stale since S20) from a **live read-only
inventory of both hosts** (`pg_roles` / `pg_database` / `pg_hba_file_rules` /
`information_schema.role_table_grants`, `sudo -u postgres`). Now contains:

- **Databases mini-table** — 6 Hetzner `:5432` DBs + owners.
- **Full Hetzner `:5432` roles table** — 18 login roles + `vps_orchestrator`
  (NOLOGIN); columns Role / Scope / Privilege / Owns / Used-by-provenance.
- **`:5435` orch cluster** pointer (added as an audit follow-up — see §3).
- **Contabo `:5434`** crypto_signals-primary role list (compact; Clevious/
  PionexBots/GM are authority).
- **Cross-host `pg_hba` grant matrix** (8 error-free rules into the primary).
- Dated "reconciled live S21" note replacing the stale footnote.

### Inventory captured (record)

| | |
|---|---|
| **Hetzner `:5432` login roles (18)** | ag_btc_reader, audit_reader, crypto_platform, crypto_signals_research, cyclestation, findings_reader, findings_writer, hermes_ingestor, hermes_log_writer, hermes_v2, hermes_v2_writer, hermes_vps, hermes_vps_writer, market_sentinel_reader, parity_reader (conn-limit 3), pgbackup, postgres (SUPERUSER), replicator (REPLICATION). **NOLOGIN:** vps_orchestrator. No `VALID UNTIL` anywhere. |
| **Memberships** | `audit_reader`→`pg_read_all_stats`; `pgbackup`→`pg_read_all_data`. All other custom roles: none. |
| **DBs / owners (`:5432`)** | hermes_v2 (postgres), hermes_v2_log (hermes_v2_writer), hermes_vps_log (hermes_vps_writer), hermes_ingestor_log (postgres), vps_orchestrator_findings (vps_orchestrator), parity (postgres). |
| **`hermes_v2` DB table ownership** | `public`: hermes_v2 ×34 (+2 views, +3 seq), hermes_ingestor ×18 (+3 seq), crypto_signals_research ×4; schema `cyclestation` (owner cyclestation) ×7 (+7 seq). |
| **Contabo `:5432`** | physical streaming replica of Hetzner — identical globals, not independently writable. |
| **Hetzner `:5435` `16/orch`** | 2nd local cluster; only role `postgres`; DB `vps_orchestrator` (~950 MB). `listen_addresses` includes the Tailscale IP but every `pg_hba` rule is localhost-only → not remotely reachable. GM-owned. |
| **Contabo `:5434`** (separate crypto_signals primary) | audit_reader, clevious_audit_reader, clevious_writer, crypto_user, cs_admin, cs_reader, cs_writer, findings_reader, orch_reader, orch_replicator, orch_writer, pgbackup, pionex_reader, pionex_writer. DBs: crypto_signals (cs_admin), clevious_vps_log (clevious_writer), vps_orchestrator (postgres). |

---

## 2. Deep forensic audit (read-only sweep of the Hetzner host)

**No CRITICAL or HIGH findings. The host is genuinely healthy.**

**S19b deadlock fix verified holding:** 0 unit failures since 10:00 UTC 2026-09-10,
guardrail + escalation cycles all `Deactivated successfully` / `ExecMainStatus=0`,
`deploy_guardrail.sh` all 9 assertions pass, steady-state emission back to ~1
row/hr (hourly all-clear roll-ups only).

**Green confirmations:** `is-system-running`=running, 0 failed units, replication
`streaming/async/0` + `contabo_replica` slot `reserved`+active, `findings_log`
0 open/in_progress (40,113 rows total — ~39,772 `no_action_needed` W/C are S19b
storm residue kept by design, T-LOG.3 no-retention, stable/not growing).
Backups: `pg_backup.service` 02:31 exit 0, 4 configured DBs OK + off-sited to
Contabo, 7-dump retention enforced, restore-test logic present. netdata 102
alarms all CLEAR. TLS `artek-studio.com` → 2026-10-19, `certbot.timer` active
(renewed 08:14). UFW active (Cloudflare + tailscale0 + 41641/udp + 52222/tcp),
fail2ban 2 jails 0 banned, 3 auth failures/24h. Tailscale key-expiry disabled
both server nodes, Docker `masked`, NTP synced. unattended-upgrades on,
`Automatic-Reboot=false` (matches Clevious S44 R5 decision).

### MEDIUM findings (both → cross-project notices written S21)

| # | Finding | Owner | Notice |
|---|---|---|---|
| **A1** | **`hermes_ingestor_log` DB (Ingestor's permanent findings record) has zero backup coverage** — not in `/etc/pg_backup.conf` `DATABASES=`, no `/opt/backups/` dir, no off-site copy. `pg_backup.sh` + the conf are **GM-owned**; the DB is Ingestor's; retention is Ingestor's call. JR Hermes VPS offered to apply the host steps (add to `DATABASES=` + `ALERT_ENV_HERMES_INGESTOR_LOG=` + smoke-test one run) once Ingestor picks retention. | Ingestor + GM | `docs/CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-ingestor-log-unbackuped.md` |
| **A2** | **`:5435` orch `vps_orchestrator` DB (~950 MB) dumps to only a ~30 MB file** (`/opt/backups/vps_orchestrator/…_013016.dump`, 01:30 daily) via a mechanism outside `/etc/pg_backup.conf`. 32× ratio — could be normal compression, could be schema-only/filtered. Off-site coverage unconfirmed. | GM | `docs/CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-to-GM-orch-cluster-backup.md` |

### LOW findings — still open (not independently actionable)

| # | Finding | Why not done |
|---|---|---|
| **B3** | `sshd` binds `0.0.0.0:22` (+ `:52222`) though design intends port 22 Tailscale-only; only UFW's eth0 default-deny protects `:22`, with `permitrootlogin without-password`. Consider `ListenAddress 100.97.62.7` + `127.0.0.1`. | Host change, lock-out risk, no urgency (UFW covers it). User to green-light + smoke-test. |
| **B5** | Stale ~4-day-idle root SSH session from `jrminipc` (`100.113.177.23`, `root@notty` — likely a leftover ControlMaster/forward). | On the user's own machine. |
| **B7** (=Y3) | TimescaleDB runtime 2.29.0 vs installed pkg 2.29.2 (Hetzner) / 2.29.1 (Contabo), different apt repos; 2 pkgs held back. Latent divergence at next PG restart. | GM, escalated S19. |
| **B8** | `crypto_platform` — login role with `CONNECT` + `public` `USAGE` on `hermes_v2`, **zero table grants**, no active connections. Candidate `DROP ROLE`. | Needs confirmation no `crypto_data`-style consumer expects it; DROP is destructive. |
| — | `pg_backup.sh` (`/opt/backups/scripts/pg_backup.sh`) is **GM-owned (JR_VPS_Orchestrators Phase 8) and in no git repo** — only lives on the two hosts. | GM's to vendor into its repo. |

---

## 3. Actioned this session

### Independent (no dependency, no date gate)
- **P2** — roles table reconciled (§1). Commits `025c2b6`, `b026634`.
- **Audit follow-up** — added the `:5435` orch-cluster pointer to §5 (was covered
  in §18/§19 but not cross-linked from the reconciled roles section). `b026634`.
- **B6** — `telegram_outbox.jsonl.1.pre-s19b` + `.storm-s19b-archive` **gzipped**
  on the host (13 MB → 0.9 MB). Active `telegram_outbox.jsonl` untouched; verified
  no code references those names; `deploy_guardrail.sh` re-run 9/9, heartbeat
  fresh. `3ff3aff`.
- **`/opt/hermes-vps`** deploy clone kept fast-forwarded to HEAD after every push.
- **A1 / A2** cross-project notices written (see §2 table).

### User-authorized host disk cleanup (disk 54% → 47%, ~5.6 GB freed)
- **B4** — `apt autoremove --purge` (freed 124 MB, `libllvm17t64`). Old kernel
  `linux-image-6.8.0-137` **kept** — Ubuntu's one-prior-kernel fallback, not
  auto-removable, correct default, not forced.
- **B2 pt.1** — `/opt/backups/hermes_v2/manual/` deleted (~2.4 GB: `pre-s68-repair.dump`,
  `s68-verified-checkpoint-…dump` from Sep 2 + Aug-12 `raw_onchain` files).
  Safety net: 7 automated `hermes_v2` daily dumps local + 7 off-site on Contabo.
  Empty `manual/` dir removed. `7839722`.
- **B2 pt.2 / B1** — 6 stale Ingestor deploy-rollback snapshots under `/opt/`
  deleted (~2.6 GB; `backup-before-s25-phase0`, `backup-pre-s27`, `-pre-s27b`,
  `-pre-s28`, `-pre-s14`, `-pre-s16-health`; all Aug 27–Sep 4, superseded — live
  `/opt/hermes-ingestor` clean at `f064750`). **`/opt/hermes-ingestor-staging`
  NOT touched** (active worktree, modified today). **Closes the S16-escalated
  `/opt` clutter item.** Notice:
  `docs/CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-ingestor-host-cleanup.md`.
  `7839722`.
- **`/opt/archives/crypto_db_v1_archive_20260518.dump` (578 MB) — DELETED** on
  explicit user go-ahead, after being told it was the **sole surviving copy** of
  a decommissioned DB (verified: no `crypto*` DB on Hetzner `:5432`, no copy on
  Contabo). `/opt/archives/` now empty and removed. `b2bf521`.

### Commits (all on `main`, pushed, deploy clone synced)
```
b2bf521 S21: delete /opt/archives/crypto_db_v1_archive (578 MB) on user authorization
7839722 S21: host disk cleanup (user-approved) — B2/B4, ~5 GB freed
3ff3aff S21: forensic-audit follow-through — B6 done, A1/A2 notices, handoff updated
56f64a9 S21: add deep forensic audit findings to handoff
b026634 S21: note the :5435 orch cluster in the reconciled roles section
025c2b6 S21: reconcile stale PostgreSQL roles table in VPS_CONNECTIVITY_REFERENCE.md
```

---

## 4. Pendings for S22 — all external or user-decision

### JR Hermes VPS owned
| # | Item | State |
|---|---|---|
| — | **Nothing broken. Nothing owed.** | — |
| B3 | sshd `ListenAddress` hardening (defense-in-depth) | Needs user go-ahead + staged smoke-test. Low priority. |
| B8 | `DROP ROLE crypto_platform` (unused login role) | Needs consumer confirmation first (check `crypto_data` / "crypto platform" project). |
| — | `VPS_CONNECTIVITY_REFERENCE.md` roles-table now current; §2 `PostgreSQL roles` is authoritative as of S21. | Done. |

### Waiting on other projects
| # | Item | Owner | Since |
|---|---|---|---|
| A1 | Register `hermes_ingestor_log` in the backup job (Ingestor picks retention → JR Hermes VPS can apply host steps) | Ingestor + GM | S21 |
| A2 | Verify `:5435` `vps_orchestrator` dump is full + off-sited | GM | S21 |
| X1 | Bulk-triage `vps_orchestrator_findings` for mirrored S19b storm CRITICALs, then close the S41 escalation | GM | S19b |
| X3 | `/opt/hermes_v2` teardown (5 timers + `hermes_v2.service` + dead `prometheus.service` unit file, 1.8 GB) + strip stale shadowed `FRED_API_KEY` in `/opt/hermes_v2/.env` | Ingestor | escalated S16 |
| P3 | GM copy of the S19b reply notice is dropped in `JR_VPS_Orchestrators/docs/` but not committed | GM | S19b |
| Y1 | Wire `parity_reader` into `contabo_tier1_watch.py` | Clevious VPS (S52) | S20 |
| Y2 | Raise Contabo standby `max_wal_senders` 10→16 + `max_locks_per_transaction` 512→1024 + restart | Clevious VPS (S51 C1-B) | S19 |
| Y3 | Cross-host TimescaleDB pkg divergence — latent at next PG restart | GM | escalated S19 |
| Y4 | Clevious S50 R5 detection-control naming confirmation | Clevious VPS | S16 |

### Cross-project notices emitted this session (awaiting reply)
- `CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-ingestor-log-unbackuped.md` → Ingestor + GM
- `CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-to-GM-orch-cluster-backup.md` → GM
- `CROSS-PROJECT-NOTICE-2026-09-10-jr-hermes-vps-s21-ingestor-host-cleanup.md` → Ingestor (INFO — cleanup done on their behalf)

---

## 5. Interaction / numbering ground rule

`#Interaction NN` opener + hallucination-zone flagging observed throughout S21.
Session = **S21** (disk-verified against `docs/sessions/`). Next = **S22**.
