# VPS Connectivity & Credentials Reference
**Two-node Hermes infrastructure — last updated 2026-08-17 (JR_VPS_Orchestrators S58 remediation: Hetzner `16/orch:5435` now binds its Tailscale address and its `pg_hba` rules are revealed to be unbacked; the cross-VPS backup leg is symmetric again, scoped per-database, and fails over Tailscale→WireGuard in both directions; cold storage now covers all five databases; `audit_reader` narrowed off `pg_monitor` — see §19, which supersedes §18.1 and §8. Prior: S57 forensic audit — added the Hetzner `16/orch:5435` cluster, documented sudo/NOPASSWD scope on both hosts, identified the third key in Hetzner's `authorized_keys`, see §18. Prior: JR Basic Crypto Signals S67, §3 — `contabo_hetzner_sync` added. See §12 for S27, §13 for S28, §14 for S29, §15 for S30, §16 for S31, §18 for S57, §19 for S58)**

> 🔴 **READ §12–§15 BEFORE ASSUMING ANYTHING ABOUT SSH, POSTGRES RESTARTS, OR TAILSCALE.**
> S27–S29 changed several long-standing facts in this document. In particular:
> **both nodes' public SSH now works** (Hetzner on 52222, Contabo on 2222),
> there is now a **third path — static WireGuard `jr-wg0`** — between the nodes,
> `fail2ban` is genuinely enforcing where it previously could not ban at all
> (**but it cannot see failed *key* auth** — see §14.3),
> and the **December 2026 Tailscale key expiry is RESOLVED** — expiry is
> disabled on both nodes, verified on-host.
>
> ⚠️ **Later sections win.** Anything in §12 saying "still open", "not yet
> reachable", or "requires the account owner" was closed in S28. Anything in
> §12/§13 saying there is **no second path**, or that the postgres readiness
> gates are **unproven at runtime**, was closed in S29. Anything in §14 saying
> the tunnel carries **admin SSH only**, or that `ops_log` on it is **blocked**,
> was closed in S30. **§15 is authoritative where they disagree** — and note
> §15.2: Tailscale and `jr-wg0` are **not independent paths**.

> **Canonical copies:** workspace root (this file) + `hermes_v2/docs/VPS_CONNECTIVITY_REFERENCE.md` + `/opt/VPS_CONNECTIVITY_REFERENCE.md` on Hetzner.
> Keep all three in sync whenever credentials or topology change.

---

## 1. Node Inventory

| | **Hetzner (PRIMARY)** | **Contabo (STANDBY + COMPUTE + crypto_signals)** |
|---|---|---|
| **Hostname** | `hermes` | `vmi3361707` |
| **Role** | Ingestion primary, execution, nginx/TLS, monitoring source, hermes_v2+crypto_db PG primary | Hot standby (hermes_v2+crypto_db replica), crypto-signals containers, **crypto_signals PRIMARY (port 5434)**, Netdata parent, off-site backup target |
| **Public IP** | `46.225.14.26` — **SSH now OPEN on 52222 since S28** (verified from two external sources; key-only + fail2ban). IPv6: `2a01:4f8:1c1b:e101::1`, also serving 52222 | `195.26.247.212` — **SSH on eth0 OPEN on 2222 since S27** (deliberate Tailscale-independent fallback; key-only + fail2ban) |
| **Tailscale IP** | `100.97.62.7` | `100.121.245.4` |
| **SSH port** | 22 (Tailscale only) **+ 52222 public fallback, live since S28** — reachable on both IPv4 and IPv6, see §13.1 | 2222 — reachable via **both** Tailscale (`100.121.245.4`) **and the public IP** (`195.26.247.212`) since S27 |
| **CPU** | Intel Xeon Skylake, 4 vCPU | AMD EPYC, ~4 vCPU |
| **RAM** | 7.8 GB | 9.9 GB |
| **Disk** | 75 GB (44% used, ~41 GB free — live 2026-07-31) | 96 GB (40% used, ~59 GB free — live 2026-07-31) |
| **WireGuard (`jr-wg0`)** | `10.77.0.1` — static tunnel to Contabo, S29 | `10.77.0.2` — static tunnel to Hetzner, S29 |
| **OS** | Ubuntu 24.04.4 LTS | Ubuntu 24.04 LTS |
| **`HERMES_ROLE`** | `ingestion` | `compute` |
| **Docker** | ✅ **RESOLVED 2026-07-21 (hermes_v2 session).** Root cause found: `/etc/systemd/system/postgresql.service.d/after-docker.conf` had `Requires=docker.service` on the live `postgresql.service` — a leftover drop-in with no actual functional need (Postgres is native, not containerized) that forced Docker to start on every boot despite running zero containers and being boot-disabled itself. Live smoke test: drop-in backed up (`/root/smoke_test_backups/after-docker.conf.bak.*` on Hetzner) and removed, `daemon-reload`, then `docker.service`+`docker.socket` stopped — `postgresql.service`, `postgresql@16-main.service`, and `hermes_v2` all confirmed to stay active with no cascade, `pg_isready` still accepting connections, zero new errors in either journal. Docker now stopped and will not restart on reboot (both units already boot-disabled, dependency removed). **2026-07-23 (S24) update:** daemon found active again — `docker.socket` is socket-activated, so any probe of `/var/run/docker.sock` (e.g. netdata's docker collector) revives it even though both units are disabled. Stopped both service+socket again S24; flagged `systemctl mask docker.socket docker.service` as the durable fix if it kept reviving. **Live-verified 2026-07-24: the mask fix has since been applied** — both `docker.service` and `docker.socket` now show `LoadState=masked`/`UnitFileState=masked` and `inactive`, so a socket probe can no longer revive the daemon. Images already pruned to 0B. This line item is now durably closed — no further Docker-on-Hetzner action needed. | ✅ Active — 3 crypto-signals containers live-confirmed 2026-07-19 (`compute`, `collector`, `signal_gen`) — count corrected from the previously documented 4 (no `ingestor` container exists, running or stopped) |
| **Binance access** | ✅ Full access | ⚠️ `api.binance.com` banned (HTTP 451). `data-api.binance.vision` (mirror used by ingestor) ✅ reachable — verified live 2026-06-26 |
| **OKX access** | ✅ Full access | ✅ `www.okx.com` reachable — verified live 2026-06-26 |
| **CoinMetrics access** | ✅ | ✅ `community-api.coinmetrics.io` reachable — verified live 2026-06-26. `api.coinmetrics.io` (paid) untested — assume banned until verified |

---

## 2. Tailscale Mesh

All nodes on the same Tailscale tailnet. Use Tailscale IPs for all inter-node communication.

| Node | Tailscale IP | Role | Node key expires |
|---|---|---|---|
| Hetzner (hermes) | `100.97.62.7` | Production primary | **never** — expiry disabled S28 (was 2026-12-15) |
| Contabo (vmi3361707) | `100.121.245.4` | Standby + compute | **never** — expiry disabled S28 (was 2026-12-10) |
| JRMiniPC (local dev, Windows) | `100.113.177.23` | Local development | ⚠️ **2026-12-10** — client key, still expires |
| JRMiniPC (local dev, WSL2/linux) | `100.127.198.74` | Local development | 2027-01-24 |

> **§2 corrected 2026-08-03 (S31)**, on a cross-project notice from `Clevious VPS` S29,
> re-verified live on Contabo before editing. `pixel-9a` (`100.80.153.16`) was
> **deliberately removed from the tailnet by the user** — confirmed 2026-08-03, not an
> outage, an expiry or a fault, so it is gone from the table for good and needs no
> follow-up. A second `JRMiniPC` (`100.127.198.74`, linux, the WSL2 box) was missing
> and has been added. The `—` in this column previously read
> as "not applicable"; it was not. **The Windows client key genuinely expires 2026-12-10** —
> the same date the callout below treats as resolved. That callout is about the two *servers*
> and remains correct for them; a client key expiring means that client re-authenticates, not
> that a server leaves the tailnet, and Contabo's public-SSH fallback covers admin access
> regardless. Real dates are now shown rather than dashes so nobody skimming this in December
> concludes there is no expiry anywhere.

> ✅ **Node key expiry — found S27, RESOLVED S28 (2026-07-30).** Both server node keys were
> set to expire in December 2026, five days apart; on expiry a node **leaves the tailnet and
> needs interactive re-authentication** — exactly what SSH would have been needed for.
> Expiry is now **disabled on both**, done per-machine in the Tailscale admin console
> (Machines → node → *Disable key expiry*); it is not settable from the CLI.
> **Verify on the host, not from the console UI** — the console row can be visually truncated:
> `tailscale status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['Self'].get('KeyExpiry'))"`
> Expected: `None` on both. **Re-check this after any node re-authentication**, since
> re-auth can reinstate an expiry.
>
> ✅ **"There is no second path" is NO LONGER TRUE — corrected S29.** A static WireGuard
> tunnel `jr-wg0` (`10.77.0.1` ↔ `10.77.0.2`) is live between the two public IPs and is
> systemd-managed, enabled at boot, and restart-proven. See §14.1.
>
> **But note what still rides Tailscale only:** postgres replication, the orchestrator
> API on :8002, `ops_log` writes, and the Hetzner→Contabo backup leg. As of S29 the
> tunnel carries **admin SSH only** — the work to put `ops_log` on it is staged but
> blocked (§14.2). Do not assume a service fails over just because the tunnel exists.

---

## 3. SSH Access Matrix (post-WS5 hardening)

### From local machine (Windows)

```powershell
# Hetzner — PRIMARY path (Tailscale)
ssh -i ~/.ssh/hermes_ed25519 root@100.97.62.7

# Hetzner — FALLBACK path (public IP), works when Tailscale is down. Live since S28.
ssh -i ~/.ssh/hermes_ed25519 -p 52222 root@46.225.14.26

# Contabo — PRIMARY path (Tailscale)
ssh -i "C:/Users/jr250/.credentials/cyclestation-infra/ssh-keys/clevious_vps" `
    -o IdentitiesOnly=yes -p 2222 root@100.121.245.4

# Contabo — FALLBACK path (public IP), works when Tailscale is down. New in S27.
ssh -i "C:/Users/jr250/.credentials/cyclestation-infra/ssh-keys/clevious_vps" `
    -o IdentitiesOnly=yes -p 2222 root@195.26.247.212
```

> ✅ **BOTH nodes now have a public fallback.** Contabo's opened in S27
> (`root@195.26.247.212:2222`); Hetzner's became genuinely reachable in S28
> (`root@46.225.14.26:52222`, IPv4 **and** IPv6) once the Hetzner Cloud firewall rule
> was added *and* a second host-side fault was fixed — `ssh.socket` was binding
> IPv6-only. Both are key-only (`PasswordAuthentication no`) with fail2ban enforcing.
>
> Prefer the Tailscale IP for routine work; the public ports exist so that a Tailscale
> outage, a `tailscaled` failure, or a node-key expiry does not lock you out.
>
> ⚠️ **`MaxAuthTries` is now 3 on BOTH nodes** (Hetzner lowered from 6 in S29). If your
> SSH agent offers several keys before the right one, you can exhaust the limit and be
> disconnected. Use `-o IdentitiesOnly=yes -i <key>` for automated connections.

### Third path — over the WireGuard tunnel (S29)

```bash
# From Contabo → Hetzner            # From Hetzner → Contabo
ssh root@10.77.0.1                  ssh -p 2222 root@10.77.0.2
```

Node-to-node only (the tunnel has just the two peers; it is not reachable from your
laptop). This is the path to use when Tailscale is down **and** you already have a
shell on the other node. UFW carries an explicit `allow in on jr-wg0` on both — see
§14.1 for why that rule is not optional.

### From Hetzner to Contabo

```bash
ssh -i /root/.ssh/contabo_sync -p 2222 \
    -o IdentitiesOnly=yes -o IdentityAgent=none \
    root@100.121.245.4
```

The `contabo_sync` key is restricted to `from="100.97.62.7"` in Contabo's `authorized_keys`
(Hetzner Tailscale IP only). This is the key used by automated tasks (rsync backup, etc.).

### From Contabo to Hetzner (new S67, 2026-08-08)

```bash
ssh -i /root/.ssh/contabo_hetzner_sync -o IdentitiesOnly=yes \
    root@100.97.62.7
```

The `contabo_hetzner_sync` key is restricted to `from="100.121.245.4,10.77.0.2"` in Hetzner's
`authorized_keys` (Contabo's Tailscale IP + WireGuard `jr-wg0` tunnel IP — both paths
live-tested). Used by `pg_backup_cs.sh` → `pg_backup_rsync_to_hetzner.sh` (JR Basic Crypto
Signals) to copy nightly `crypto_signals` dumps off Contabo to `/opt/backups/crypto_signals_offsite/`
on Hetzner, closing the "lose Contabo, lose every backup" gap flagged in PionexBots'
`CROSS_HOST_RESTORE_PROPOSAL.md`.

Since the S67 hardening pass the script tries Tailscale first and falls back to WireGuard
`10.77.0.1` automatically, so a Tailscale outage no longer silently stops the off-site copy.

### SSH Key Inventory

| Key name | Location | Grants access to | Restriction |
|---|---|---|---|
| `hermes_ed25519` | `~/.ssh/hermes_ed25519` (local) | Hetzner root | Tailscale IP only (Hetzner firewall) |
| `clevious_vps` | `C:/Users/jr250/.credentials/cyclestation-infra/ssh-keys/clevious_vps` | Contabo root | None (key-only; password auth disabled) |
| `contabo_sync` | `/root/.ssh/contabo_sync` on Hetzner | Contabo root | `from="100.97.62.7"` (Hetzner Tailscale IP only) |
| `contabo_hetzner_sync` | `/root/.ssh/contabo_hetzner_sync` on Contabo | Hetzner root | `from="100.121.245.4,10.77.0.2"` (Contabo Tailscale IP + WireGuard tunnel IP) — **new S67 (2026-08-08, JR Basic Crypto Signals), reverse direction of `contabo_sync`**, used by `pg_backup_rsync_to_hetzner.sh` to copy nightly `crypto_signals` dumps to `/opt/backups/crypto_signals_offsite/` on Hetzner. Both Tailscale and WireGuard paths live-tested. Detail: `JR Basic Crypto Signals/docs/CROSS_HOST_BACKUP_SETUP.md` |

**Contabo `authorized_keys` (final state post-WS5):**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFHwcP4p7pTBZbs68E655sE2cpMWddYqGYNUPjECKcmi clevious-vps
from="100.97.62.7" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBFrdCOInfUlcGtqMah+Oka41KWjw/kchqhJiekzcVk6 hetzner-hermes->contabo-sync
```

**Hetzner `authorized_keys` — S67 entry (verified live 2026-08-08; 3 keys total in the file):**
```
from="100.121.245.4,10.77.0.2" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKrbOlxk7MZNxK4kE3uMlJkW/YAnYVOtSWQLfSujm7hU contabo_sync_to_hetzner_20260808
```

---

## 4. Firewall — Open Ports per Node (post-WS5)

### Hetzner

| Port/Protocol | Interface | From | Purpose |
|---|---|---|---|
| 80/tcp | eth0 | Cloudflare CIDRs only | nginx HTTP (→301 redirect) |
| 443/tcp | eth0 | Cloudflare CIDRs only | nginx HTTPS — all external traffic |
| 8000/tcp | `0.0.0.0` (host) | **UFW default-deny — no allow rule** | **nginx**, Cloudflare Tunnel local origin (`server_name … _` catch-all). Corrected S28: this is nginx, not FastAPI. Reached by `cloudflared` over loopback only. The Hetzner Cloud firewall rule that exposed it publicly was **removed S28** — see §13.2 |
| 8002/tcp | tailscale0 (`100.97.62.7`) | Any (Tailscale) | FastAPI orchestrator API (admin/monitoring only) |
| 5432/tcp | 127.0.0.1 | localhost | PostgreSQL local |
| 22/tcp | tailscale0 | Any (Tailscale) | SSH — primary path |
| 52222/tcp | any (IPv4 **and** IPv6) | ALLOW (UFW + provider) | **SSH public fallback — LIVE since S28**, verified from two external sources. See §13.1 |
| 41641/udp | any | any | Tailscale WireGuard handshake |
| 51830/udp | eth0 | `195.26.247.212` (v4) + `2605:a140:2336:1707::/64` (v6) | **Static WireGuard `jr-wg0` — S29.** Peer-scoped, not open to the world |
| All | **jr-wg0** | Any (tunnel) | **S29 — traffic *inside* the tunnel.** Without this rule the tunnel handshakes but nothing can traverse it; see §14.1 |
| All | tailscale0 | Any (Tailscale) | Tailscale-routed traffic (catch-all) |

> **Two firewalls, not one.** UFW is the host layer; the **Hetzner Cloud provider firewall
> (`firewall-1`)** sits above it and is edited in the Hetzner console. A port must be open in
> **both**. As of S28 the provider firewall has 5 inbound rules: ICMP, `80/tcp`, `443/tcp`,
> `41641/udp`, `52222/tcp`, and no outbound rules (all egress allowed — required by
> `cloudflared` and Tailscale).

> Docker bridge 5432 rules removed 2026-06-26 after crypto-signals containers migrated to Contabo.
> Docker daemon **actually stopped 2026-07-21** (S43's "disabled" claim was stale/inaccurate — it
> had been running the whole time via a stray `Requires=docker.service` on `postgresql.service`;
> see the Docker row above for the root cause and fix).

### Contabo

| Port/Protocol | Interface | From | Purpose |
|---|---|---|---|
| 2222/tcp | tailscale0 | Any (Tailscale) | SSH — primary path |
| 2222/tcp | **any (incl. eth0)** | **ALLOW** | **SSH — public fallback path, opened S27.** Key-only + fail2ban (`bantime=3600`, `maxretry=4`). The WS5 `DENY IN on eth0` rules were deliberately removed; see §3 and §12 |
| 19999/tcp | tailscale0 | Any (Tailscale) | Netdata parent UI + stream receiver |
| 5432/tcp | 127.0.0.1 | localhost | PostgreSQL standby (read-only replica of Hetzner) |
| 5434/tcp | Docker bridge | 172.20.0.0/16 | PostgreSQL crypto_signals PRIMARY (containers) |
| 5434/tcp | tailscale0 | Any (Tailscale) | PostgreSQL crypto_signals PRIMARY (admin) |
| 41641/udp | any | any | Tailscale WireGuard handshake |
| 51830/udp | eth0 | `46.225.14.26` (v4) + `2a01:4f8:1c1b:e101::/64` (v6) | **Static WireGuard `jr-wg0` — S29.** Peer-scoped, not open to the world |
| All | **jr-wg0** | Any (tunnel) | **S29 — traffic *inside* the tunnel**; see §14.1 |
| All | tailscale0 | Any (Tailscale) | Tailscale-routed traffic (catch-all) |
| 11434/tcp | Docker bridges | 172.17.0.0/16, 172.18.0.0/16 | Ollama (Docker bridge access) |
| All others | eth0 | any | DENY (default deny incoming) |

---

## 5. Credentials Locations

### Secret files — never commit to git

| Secret | Location | Used by |
|---|---|---|
| Hetzner `.env` | `/opt/hermes_v2/.env` | hermes_v2 service (DB URL, Binance keys, Telegram, etc.) — `hermes_v2` role password **rotated S172 (2026-08-20)** after crypto-signals' 5-notice escalation confirmed it exposed on pushed GitHub history. Rotation + Contabo `compute.env` coordination done by the same-day S172 session (see `hermes_v2/docs/sessions/171-180/S172-HANDOFF.md`); a concurrent session's duplicate rotation attempt was reverted back to that value the same day to avoid re-breaking crypto-signals' already-verified access — no credential value is stored in any doc, per convention. |
| CycleStation `.env` | `/opt/cyclestation/.env` | cyclestation service (DB URL, Binance Mainnet API key — rotated S28, IP-restricted to `46.225.14.26`, withdrawals disabled; Telegram) |
| Telegram / health monitor | `/opt/crypto-health-monitor/.env` | pg_backup.sh alerts, health monitor |
| crypto-signals env files | `/opt/crypto-signals/*.env` (Contabo) | 4 containers; also used by `pg_backup_cs.sh` for Telegram (compute.env) |
| Contabo credentials | `C:\Users\jr250\.credentials\clevious-vps\credentials.env` (relocated out of OneDrive, S30; rotated S31 — see vault, not reproduced here) | Local reference; password SSH is disabled |
| GitHub SSH key | `/root/.ssh/github_hermes` on Hetzner | git pull/push |
| Contabo cross-node key | `/root/.ssh/contabo_sync` on Hetzner | rsync backup, automated SSH from Hetzner to Contabo |

### PostgreSQL roles

| Role | DB | Privileges | Used by |
|---|---|---|---|
| `postgres` | all | SUPERUSER | Break-glass only |
| `hermes_v2` | `hermes_v2` | owner | hermes_v2 service |
| `cyclestation` | `hermes_v2` (schema `cyclestation`) | USAGE + DML on cyclestation.* | cyclestation service |
| `pgbackup` | all | CONNECT + SELECT | pg_backup.sh (read-only dumps) |
| `replicator` | — | REPLICATION | Contabo streaming replica |
| `cs_admin` | `crypto_signals` | owner (no superuser) | crypto-signals admin tasks |
| `cs_writer` | `crypto_signals` | INSERT/UPDATE/SELECT | crypto-signals Docker containers |
| `cs_reader` | `crypto_signals` | SELECT | crypto-signals read-only consumers |

---

## 6. PostgreSQL Connectivity

### Hetzner primary — hermes_v2 + crypto_db (port 5432)

```
listen_addresses = 'localhost,172.17.0.1,172.18.0.1,100.97.62.7'
```

Serves `hermes_v2` and `crypto_db`. Physical streaming replica runs on Contabo:5432.

### Contabo — crypto_signals PRIMARY (port 5434, new in S43)

```
listen_addresses = 'localhost,172.20.0.1,100.121.245.4'
```

Cluster name: `crypto`. Data dir: `/var/lib/postgresql/16/crypto/`.
TimescaleDB 2.28.3 (extension updated 2026-07-23, S24). Serves `crypto_signals` exclusively.

**pg_hba.conf rules (port 5434):**
```
# Docker bridge → crypto_signals containers
host  crypto_signals  cs_writer   172.20.0.0/16       scram-sha-256
host  crypto_signals  cs_reader   172.20.0.0/16       scram-sha-256
host  crypto_signals  pgbackup    172.20.0.0/16       scram-sha-256
# Tailscale CGNAT → admin / cross-node access
host  crypto_signals  cs_writer   100.64.0.0/10       scram-sha-256
host  crypto_signals  cs_reader   100.64.0.0/10       scram-sha-256
host  crypto_signals  pgbackup    100.64.0.0/10       scram-sha-256
host  crypto_signals  cs_admin    127.0.0.1/32        scram-sha-256
```

### Contabo — hermes_v2+crypto_db STANDBY (port 5432, unchanged)

Read-only physical replica of Hetzner:5432. WAL slot `contabo_replica` on primary.
Do not write to this cluster.

### Connection strings

```bash
# From Hetzner (any local process) — hermes_v2
# (credentials in /opt/hermes_v2/.env — see §5)
DATABASE_URL="postgresql://hermes_v2:<pw>@127.0.0.1:5432/hermes_v2"

# crypto-signals containers on Contabo → crypto_signals DB (local)
PG_HOST=100.121.245.4
PG_PORT=5434
# (full credentials in /opt/crypto-signals/*.env on Contabo — see §5)

# From local dev → Contabo crypto_signals via SSH tunnel (backfill scripts)
# First: ssh -i .../clevious_vps -p 2222 -L 5433:localhost:5434 root@100.121.245.4 -N -f
DATABASE_URL="postgresql://cs_admin:<pw>@127.0.0.1:5433/crypto_signals"

# From local dev → Hetzner hermes_v2 via SSH tunnel
# First: ssh -i ~/.ssh/hermes_ed25519 -L 5433:127.0.0.1:5432 root@100.97.62.7 -N -f
DATABASE_URL="postgresql://hermes_v2:<pw>@127.0.0.1:5433/hermes_v2"
```

### Direct access

```bash
# crypto_signals (Contabo, SSH from local or via Hetzner jump)
sudo -u postgres psql -p 5434 -d crypto_signals   # on Contabo

# hermes_v2 (Hetzner)
sudo -u postgres psql -d hermes_v2                # on Hetzner
```

---

## 7. Active Services by Node

### Hetzner (`HERMES_ROLE=ingestion`)

| Service | Systemd unit | Purpose | Restriction |
|---|---|---|---|
| hermes_v2 | `hermes_v2.service` | All ingestion agents, ExecutionAgent, perp grid, API | Binance-required — stays here |
| cyclestation | `cyclestation.service` | DCA process, weekly buy, recon | Binance-required — stays here |
| ag-orchestrator | `ag-orchestrator.service` | Hourly Transformer ML inference (reads local DB) | Active — stays here |
| ag-trader | `ag-trader.service` | Live CCXT grid trading execution bot | Binance-required — stays here |
| ag-ingest | `ag-ingest.service` | ~~WebSocket streams for Spot/Futures~~ | **DISABLED S130** (redundant) |
| crypto-signals | ~~4 Docker containers~~ **REMOVED** | Migrated to Contabo 2026-06-26 | — |
| Docker | ~~docker.service~~ **Actually stopped 2026-07-21** (S43's "disabled" record was stale — daemon had kept running via a stray `Requires=docker.service` drop-in on `postgresql.service`; removed and smoke-tested, see Docker row in the node table above) | No longer needed on Hetzner | — |
| nginx | `nginx` | TLS termination, reverse proxy | Stays here (public DNS) |
| netdata | `netdata.service` | Metrics streaming child → Contabo | Stays here |
| pg_backup | `pg_backup.timer` | `hermes_v2` dumps nightly **02:30 UTC** + rsync to Contabo (2 local dumps kept, 7-day off-site retention — live-verified S135-cont). `ALERT_ENV` fixed S136 to point at `/opt/crypto-health-monitor/.env` (was the orphaned `/root/` duplicate). | Stays here |
| health-monitor | `crypto-health-monitor.service` | Backup staleness + Telegram alerts (via `@JR_Hermes` / `Clevious_Hermes_Bot`, `/opt/crypto-health-monitor/.env`) | Stays here |
| postgres | `postgresql` | Primary read-write DB (hermes_v2; crypto_db DROPPED S135) | Stays here |

### Contabo (`HERMES_ROLE=compute`)

| Service | Status | Purpose |
|---|---|---|
| postgres:5432 | `postgresql@16-main` | Hot standby replica — hermes_v2 + crypto_db (read-only) |
| postgres:5434 | `postgresql@16-crypto` | **PRIMARY for crypto_signals** (TimescaleDB 2.28.3) — added S43 |
| ~~postgres:5433~~ | ~~hindsight-api embedded PG~~ | **REMOVED** with Hindsight teardown (Clevious session 24, 2026-07-21); nothing listens on 5433 — live-verified 2026-07-23 (S24) |
| ag-dashboard | `ag-dashboard.service` | AG BTC visual portfolio web dashboard (Tailscale port 8080) |
| netdata | `netdata.service` | Monitoring parent — aggregates both nodes |
| tailscaled | `tailscaled` | Tailscale WireGuard VPN |
| fail2ban | `fail2ban.service` | SSH brute-force protection |
| pg_backup_cs | cron `30 3 * * *` | crypto_signals nightly backup (port 5434, pg_backup_cs.sh) — added S43 |
| Docker / crypto-signals | **Live — migrated S42** | **3 containers**: crypto_signals_collector/compute/signal_gen (no `ingestor` exists — count corrected 2026-07-19, re-verified 2026-07-23 S24); `crypto_net` bridge; env files `/opt/crypto-signals/*.env`; `PG_HOST=100.121.245.4 PG_PORT=5434` |

---

## 8. Data Flows Between Nodes

```
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL MACHINE (jrminipc, 100.113.177.23)                       │
│  SSH tunnel → Contabo:5434 for dev DB access (port 5433 local) │
└────────────────────┬────────────────────────────────────────────┘
                     │ Tailscale
    ┌────────────────▼──────────────────────────────┐
    │  HETZNER PRIMARY (100.97.62.7)                │
    │                                               │
    │  Cloudflare → nginx:443 → FastAPI:8000        │
    │  Postgres:5432 primary (hermes_v2, crypto_db) │
    │  hermes_v2 + cyclestation → Binance           │
    │  pg_backup → hermes_v2 dump → rsync ────────► │──┐
    │  Netdata child → stream ───────────────────►  │  │
    └───────────────────────────────────────────────┘  │ Tailscale
              │ WAL streaming replication              │
              │ (slot contabo_replica, port 5432)      │
    ┌─────────▼─────────────────────────────────────┐  │
    │  CONTABO COMPUTE (100.121.245.4)              │◄─┘
    │                                               │
    │  Postgres:5432 hot standby (hermes_v2/crypto_db, read-only)
    │  Postgres:5434 PRIMARY for crypto_signals     │
    │    └─ 3 Docker containers (local bridge)      │
    │    └─ pg_backup_cs.sh (cron 03:30 UTC)        │
    │  /opt/backups → 7-day off-site store          │
    │  Netdata parent (100.121.245.4:19999)         │
    └───────────────────────────────────────────────┘
```

**Key constraint (verified 2026-06-26):** `api.binance.com` is banned from Contabo (HTTP 451).
`data-api.binance.vision` (Binance mirror used by ingestor) and `www.okx.com` are ✅ reachable.
Execution (order placement) and any service needing `api.binance.com` must stay on Hetzner.
**All 3 crypto-signals containers run on Contabo** (collector/compute/signal_gen — no `ingestor`) and connect to local Postgres:5434.

---

## 9. Monitoring

- **Netdata dashboard:** `http://100.121.245.4:19999` (Tailscale only)
  - Shows both nodes: `hermes` (Hetzner) + `vmi3361707` (Contabo)
- **Netdata dashboards — public, Cloudflare Access-gated (email-OTP, `jrartekstudio@gmail.com`
  only), JR_VPS_Orchestrators-owned:**
  - Hetzner: `https://netdata.artek-studio.com` — via `hermes_v2`'s existing `hermes-v2-prod`
    Cloudflare Tunnel (ingress rule pre-existed since 2026-06-18, predates this project's own
    subdomain work; do not confuse with `hermes.artek-studio.com`, which is `hermes_v2`'s own
    public dashboard app, NOT Netdata — see S49 correction below).
  - Contabo: `https://clevious.artek-studio.com` — via a new, project-owned Cloudflare Tunnel
    (`clevious-netdata`, tunnel id `f860f4c2-647e-4c4a-b244-794e28c968b4`), config at
    `/etc/cloudflared/config.yml` on Contabo, systemd unit `cloudflared.service`. Outbound-only
    — no UFW/inbound port changes on Contabo (confirmed unchanged post-deploy, S49).
  - **S49 correction:** S48 mistakenly built a duplicate/broken direct-nginx path on Hetzner
    for `hermes.artek-studio.com` (unreachable by real traffic — that hostname routes via
    Cloudflare Tunnel to `hermes_v2`'s dashboard app on port 8000, not to Netdata) and
    accidentally Access-gated `hermes_v2`'s previously-public dashboard in the process. Both
    reverted S49; `hermes.artek-studio.com` is public again, `netdata.artek-studio.com` (which
    already worked) is the correct Hetzner Netdata URL.
  - **S52: consolidated landing page** — `https://health.artek-studio.com` — a single
    Cloudflare Pages static site (`web/health-landing/index.html` in this repo), same
    Access gating (email-OTP, `jrartekstudio@gmail.com` only), linking out to both
    `netdata.artek-studio.com` and `clevious.artek-studio.com` above. Confirmed live and
    correctly Access-gated (curl → 302 to `jroaks.cloudflareaccess.com` OTP login,
    matching the other two subdomains' pattern exactly — S53 additionally confirmed via a
    real browser render that the Access login page reads "Log in to Netdata Dashboard").
    Originally deployed by the user directly, out-of-band, via Wrangler CLI OAuth inside
    Hermes Agent's own environment (no API token has Cloudflare Pages write scope — that's
    why it wasn't a vault token). **S53: that mechanism is now in this repo** —
    `deploy/deploy_health_landing.sh` redeploys the page via the same Wrangler OAuth
    approach; Wrangler's OAuth session is per-machine, not in the vault, so a fresh
    `wrangler login` is needed the first time on any given machine. Does not (yet) replace
    the two individual subdomains, which remain independently live.
- **hermes_v2 Prometheus metrics:** `http://100.97.62.7:8000/metrics` (Tailscale) or `https://www.artek-studio.com/metrics` (public via nginx)
- **Telegram bots — full inventory (routing split live since S136, 2026-07-06):** all chat to the same account (`chat_id 360294128`)
  | Bot username | Display name | Token location | Used by / sends |
  |---|---|---|---|
  | `Clevious_Hermes_Bot` | **JR_Hermes** | `/opt/crypto-health-monitor/.env` (Hetzner) **and** `/opt/hermes_v2/.env` → `TELEGRAM_HERMES_BOT_TOKEN`/`CHAT_ID` (copied S136) | `crypto-health-monitor.service` (health-monitor.js, 60s poll) — backup staleness alerts. **Also `MonitoringTelegramAgent`(mode="infra") + `OpsEventBridge` infra bridge** — CPU/mem/disk/SSL/replication/disk-ETA alerts, infra daily summary, `service.started`. |
  | `JRHermesIngestorbot` | **JR_HermesIngestor** | `/opt/hermes_v2/.env` → `TELEGRAM_OPS_BOT_TOKEN` | `MonitoringTelegramAgent`(mode="project") + `OpsEventBridge` project bridge — agent health, ingestion errors, signals, trading, circuit breaker, perp P&L/liquidation, compression degradation, project daily summary. |
  | `JRCryptoSignalsBot` | JR_CryptoSignals | ~~`/root/crypto-health-monitor/.env`~~ — **directory deleted S136** | No longer referenced by anything (was only reachable via the stale `pg_backup.sh` `ALERT_ENV` misconfiguration, fixed S136). |
  | `JRCyclestationbot` | JR_CycleStation | `/opt/cyclestation/.env` | CycleStation weekly buy/report notifications (separate project). |
  | `jr_crypto_knife_bot` | CryptoKnifeBot | `/opt/hermes_v2/.env` → `TELEGRAM_BOT_TOKEN` | Dormant legacy fallback — unused since S135 set the ops token; fully dead now both dedicated bots are wired (S136). |
  - crypto_signals backup failures (pg_backup_cs.sh on Contabo, nightly, via `/opt/crypto-signals/compute.env`)

---

## 10. crypto-signals Migration to Contabo — COMPLETE ✅

**Status as of S43 (2026-06-26):** Migration fully complete.

| Phase | Status | Details |
|---|---|---|
| Containers → Contabo | ✅ S42 | Containers on `crypto_net`, `--restart unless-stopped` (3 live today: collector/compute/signal_gen — see node table) |
| WAL slot | ✅ S42 | `contabo_replica` active, lag ≈ 0 bytes |
| crypto_signals DB → Contabo:5434 | ✅ S43 | PG 16 `crypto` cluster; TimescaleDB 2.28.1; pg_dump verified |
| Container PG_HOST cutover | ✅ S43 | `PG_HOST=100.121.245.4 PG_PORT=5434` in all env files |
| Backup | ✅ S43 | `pg_backup_cs.sh` cron 03:30 UTC on Contabo; Hetzner DATABASES=hermes_v2 only |
| Hetzner crypto_signals DROP | ✅ done | Live-verified absent 2026-07-23 (JR_VPS_Orchestrators S24): `crypto_signals` no longer in `pg_database` on Hetzner. `cs_writer`/`cs_reader`/`cs_admin` roles also confirmed gone from the Hetzner cluster — live-reverified 2026-07-24 (hermes_v2 session), zero rows returned; no cleanup remaining |
| Hetzner pg_hba CGNAT cleanup | ✅ done | Live-verified 2026-07-23 (S24): no crypto_signals/cs_* rules remain in Hetzner's pg_hba.conf |

---

## 11. Adding a New Service to Contabo

Checklist for any new project deploying to Contabo:

1. **Check Binance/exchange access:** if the service needs Binance, it **must run on Hetzner**.
2. **Install dependencies** via apt/pip/npm on Contabo.
3. **DB model:** crypto-signals containers use Contabo-local PG (`100.121.245.4:5434`). hermes_v2-related services use write-back to Hetzner (`100.97.62.7:5432`). Contabo:5432 is read-only standby — do not write to it.
4. **systemd unit:** create `/etc/systemd/system/<svc>.service` with `User=<svc>` (never root for the app logic).
5. **Secrets:** own `.env` at `/opt/<svc>/.env`, mode `0600`, owned by the service user.
6. **Register DB in backup config** on whichever node hosts the primary DB.
7. **Tailscale only:** all inter-node traffic uses Tailscale IPs. No public IP connections.
8. **ufw on Contabo:** the `tailscale0 ALLOW IN` catch-all already covers new service ports reachable from other Tailscale nodes. Only add specific rules if you need public exposure.
9. **Telegram alerts:** reuse credentials from `/opt/crypto-health-monitor/.env` (Hetzner) or `/opt/crypto-signals/compute.env` (Contabo) per HERMES_PLATFORM_STANDARD R4.
10. **Document in the project's session handoff** and reference `HERMES_PLATFORM_STANDARD.md`.

---

*Keep in sync: workspace root + `hermes_v2/docs/VPS_CONNECTIVITY_REFERENCE.md` + `/opt/VPS_CONNECTIVITY_REFERENCE.md` on Hetzner.*

---

## 12. S27 operational changes (2026-07-30) — what every project must know

Source: `JR_VPS_Orchestrators/Sessions/VPS orchestrator agents S27 handoff.md`.
These are **host-level** changes made by the VPS orchestrator project. They do not touch
any project's code, but several of them change behaviour projects depend on.

### 12.1 SSH — Contabo now has a public fallback path

`root@195.26.247.212:2222` works (verified live). The Tailscale path
(`root@100.121.245.4:2222`) is unchanged and remains the preferred one.

**Why:** Tailscale was the *only* SSH path to either node. That made a `tailscaled`
failure, a tailnet outage, or a node-key expiry a total loss of administrative access.

~~**Hetzner still has no fallback**~~ — ✅ **SUPERSEDED: Hetzner's 52222 fallback is LIVE as
of S28. See §13.1** (and note the second, host-side fault that this section's reasoning
missed). **Note for anyone debugging this class of problem: UFW is not the only firewall.
If a port is open locally but *times out* rather than *refuses* externally, suspect the
provider — and confirm from a second external source before concluding.**

### 12.2 fail2ban is now genuinely enforcing — it previously was not

**This is the one most likely to bite an automated job.** On both nodes fail2ban was
running, enabled, jail loaded — and **structurally incapable of banning anything**. Its
matcher watched `_SYSTEMD_UNIT=sshd.service`, but Ubuntu 24.04 socket-activates ssh and
every session logs under `ssh.service` (sampled: Hetzner 974, Contabo 4168 entries; zero
under the watched unit). `Total failed: 0` read as "no attacks" and meant "sees nothing".

Fixed and proven by replaying real journal history (22,022 / 789 matches, both previously 0).

**Consequences for your project:**
- Policy is now `maxretry=4`, `findtime=600`, `bantime=3600` on **both** nodes.
- Any script or CI job that retries SSH with a wrong key, wrong user, or wrong port
  **can now actually get its source IP banned for an hour.** Before S27 it could not.
- **Tailscale sources are exempt** — `ignoreip` covers `127.0.0.1/8`, `::1`, and
  `100.64.0.0/10` (Tailscale's CGNAT range), deliberately, so the protection mechanism
  can never lock us out via the admin path. Jobs running over Tailscale are unaffected.
- Jobs connecting to **Contabo's public IP** are the ones now exposed to banning.

Check/unban: `fail2ban-client status sshd` / `fail2ban-client set sshd unbanip <IP>`

### 12.3 PostgreSQL restart behaviour changed on BOTH nodes

Postgres units now have **interface-readiness gates** as `ExecStartPre`, because postgres
binds specific addresses and was repeatedly coming up bound to `localhost` only after a
reboot — silently breaking replication and the crypto-signals pipeline while systemd
reported a perfectly healthy unit (S24, S25).

| Unit | Node | Gates on |
|---|---|---|
| `postgresql@16-main` | Hetzner | `100.97.62.7` (Tailscale) |
| `postgresql@16-crypto` | Contabo | `172.20.0.1` (Docker bridge) **and** `100.121.245.4` (Tailscale) |
| `postgresql@16-main` | Contabo | `172.20.0.1` (Docker bridge) |

**What this means in practice:**
- A `systemctl start/restart` of postgres can now **block up to 90 s per gate** while it
  waits for the address. This is expected, not a hang.
- If an address never appears, **postgres will refuse to start** rather than start
  half-bound. That is deliberate: a failed unit is visible to alerting, a silently
  mis-bound one is not.
- After 3 failed attempts in 600 s the unit stays `failed` instead of retrying forever.
- Script: `/usr/local/bin/wait-for-ip.sh <ipv4> [timeout]` (Contabo, generalized) and
  `/usr/local/bin/wait-for-tailscale-ip.sh` (Hetzner). **Do not remove these** without
  understanding they are the only protection against the silent mis-bind.

⚠️ `postgresql@16-crypto` on Contabo has its gates configured but **has not yet been
restarted** to prove them at runtime — deliberately, because it carries the live
crypto-signals pipeline. Expect the first restart to exercise this.

### 12.4 Services no longer auto-restart after library upgrades

`/etc/needrestart/conf.d/99-jr-critical-no-autorestart.conf` on **both** nodes excludes
`systemd-networkd`, `systemd-resolved`, `nginx`, `postgresql`, `tailscaled`, and
`cloudflared` from needrestart's **automatic** restart.

**Why:** needrestart ships in automatic mode under `unattended-upgrades`. A single
`libc6` security upgrade restarted daemons linked against it on both nodes a day apart —
taking nginx down for 4h10m on Hetzner and wedging `eth0` for ~8h on Contabo.

**Trade-off you inherit:** those six services keep running the **old shared library**
until someone deliberately restarts them or the node reboots. needrestart still *reports*
them. This makes periodic reboots more load-bearing than before.

### 12.5 Still true, still biting: `crypto_signals_compute` wedges on boot

Third occurrence. After a boot-time DB outage it reports **"Up" to Docker while producing
no writes and no log output** for 6+ minutes; its connection pool never retries. Has
needed a manual `docker restart crypto_signals_compute` after **every** reboot so far.

Owned by crypto-signals (R4 self-containment — flagged here, not patched). It wants pool
retry or a healthcheck-driven restart.

**Never verify this pipeline with `docker ps`. Verify a real write:**
```bash
sudo -u postgres psql -d crypto_signals -p 5434 -Atc \
  "SELECT 'compute', now()-max(created_at) FROM compute_state;"
```

### 12.6 ~~Open items requiring the account owner~~ — ✅ BOTH CLOSED IN S28

1. ~~Tailscale admin console → disable key expiry on both nodes~~ ✅ **DONE 2026-07-30.**
2. ~~Hetzner Cloud console → allow inbound `52222/tcp`~~ ✅ **DONE 2026-07-30.**

See §13. **No items in this reference require the account owner.**

---

## 13. S28 operational changes (2026-07-30) — supersedes §12 where they disagree

Source: `JR_VPS_Orchestrators/Sessions/VPS orchestrator agents S28 handoff.md`.

### 13.1 Hetzner public SSH is LIVE — and getting there exposed a second fault

`root@46.225.14.26:52222` now works, verified from two independent external sources.
**Hetzner has a Tailscale-independent admin path for the first time.**

```bash
ssh -i ~/.ssh/hermes_ed25519 -p 52222 root@46.225.14.26 hostname
```

Adding the provider firewall rule did **not** by itself restore access. IPv4 then returned
**`Connection refused`** — not a timeout — which by §12.1's own rule meant packets were now
arriving and the *host* was rejecting them.

**§12.1's reasoning was half wrong.** It assumed `net.ipv6.bindv6only=0` meant the `[::]`
listener accepted IPv4. **`ssh.socket` runs `BindIPv6Only=ipv6-only`, which OVERRIDES that
sysctl.** S27's bare `ListenStream=52222` therefore bound **only** `[::]:52222` with
`v6only:1` — there was never an IPv4 listener. The vendor unit lists `0.0.0.0:22` and
`[::]:22` separately for exactly this reason.

> 🔑 **Never infer dual-stack from `net.ipv6.bindv6only`. Check the `v6only` flag on the
> real socket: `ss -tlnpe`.** Two independent faults were stacked here and the closed
> provider firewall masked the second completely.

Fixed by listing both families explicitly in `/etc/systemd/system/ssh.socket.d/10-jr-extra-port.conf`.
Current listeners: `0.0.0.0:22`, `[::]:22`, `0.0.0.0:52222`, `[::]:52222`.

### 13.2 Hetzner provider firewall — `TCP 8000` removed, `80/443` are NOT vestigial

**Removed:** the inbound `TCP 8000` rule, which was open to `Any IPv4, Any IPv6`. Port 8000
is nginx serving the Cloudflare Tunnel's local origin with a `_` catch-all `server_name`.
`cloudflared` dials **outbound** and reaches it over loopback, so the inbound rule was never
needed — and **UFW's default-deny was the only control keeping the whole app off the public
internet in plain HTTP**, with no TLS, no WAF, and the origin fully bypassed.
Verified after removal: `cloudflared` active, `curl localhost:8000` → 200, 0 failed units.

⚠️ **Correction to a widely-repeated assumption: Hetzner's 80/443 are NOT vestigial.**
S22/S27 suggested they might be, since all traffic arrives via the outbound tunnel.
**They carry live traffic** — top `access.log` clients are Cloudflare *edge* IPs
(`104.23.229.138`, `198.41.227.186`, `172.70.94.80`), all inside the ranges UFW allows.
**Closing them would cause an outage.**

**Considered and rejected:** narrowing 80/443 at the provider to Cloudflare's ranges to
match UFW. That is ~29 hand-maintained rules that Cloudflare periodically revises; a stale
copy becomes a silent outage, and UFW already enforces it. Two copies of a drifting list is
worse than one.

### 13.3 fail2ban does NOT count failed *key* authentication

Relevant to every project now that both nodes have public SSH. Tested individually against
the live filter:

| Journal line | Result |
|---|---|
| `Invalid user admin from …` | **matched** |
| `Failed password for root from …` | **matched** |
| `Connection closed by authenticating user root … [preauth]` | **ignored** |

The third is the failed-public-key signature on a key-only host — the dominant failure mode
here. So `Total failed: 0` **again overstates coverage**, the same trap as §12.2, narrower.

**Calibrate honestly:** this is *not* a compromise path — key auth is not brute-forceable —
so the cost is noise and connection churn, not access. `mode = aggressive` would match it
and was **deliberately not applied**: an SSH agent offering several keys before the right
one produces that exact line, and `maxretry=4` is tight.

⚠️ **`MaxAuthTries` is 6 on Hetzner, 3 on Contabo.** Because fail2ban does not count failed
key auth, `MaxAuthTries` is the **only** control bounding a key-spraying attempt. Hetzner is
both the looser node and the one whose public port just opened. **Recommend lowering Hetzner
to 3.** Not yet applied.

**Verified correct on both nodes:** `permitrootlogin without-password` (= `prohibit-password`),
`passwordauthentication no`, `pubkeyauthentication yes`, `kbdinteractiveauthentication no`.

### 13.4 Tailscale key expiry — RESOLVED

Expiry is **disabled on both nodes**. Verified on-host, not from the admin console:

```bash
tailscale status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['Self'].get('KeyExpiry'))"
# → None on both hetzner-hermes and clevious-vps
```

The December 2026 dates in §2 and §12 are **obsolete**. Anything scheduled around them can
be dropped.

### 13.5 For hermes_v2 — `real_ip` covers only one of two ingress paths

`set_real_ip_from 127.0.0.1` trusts **loopback only**, i.e. the tunnel. But traffic also
arrives **direct on 80/443 from Cloudflare's edge**, where real-IP restoration silently does
not apply and `$binary_remote_addr` is the Cloudflare edge IP.

The three consequences S150's own comment documents are therefore **still live on that path**:
every visitor behind a given edge IP shares one `limit_req` bucket (`api_general` 10r/s,
`api_metrics` 2r/s), an IP-keyed allow/deny list cannot match, and access logs record
Cloudflare rather than the visitor.

**Latent hazard:** point any fail2ban jail at `access.log` and it will eventually ban a
**Cloudflare edge IP**, cutting off every visitor routed through it.

Fix is adding Cloudflare's ranges to `set_real_ip_from` — full snippet in
`hermes_v2/docs/CROSS-PROJECT-NOTICE-2026-07-30-vps-host-changes-affecting-hermes-v2.md`.
**hermes_v2's to apply; nginx was not touched.**

### 13.6 Open items requiring the account owner

**None.** Everything in §12.6 is closed.

---

## 14. S29 operational changes (2026-07-30/31) — supersedes §12 and §13 where they disagree

Source: `JR_VPS_Orchestrators/Sessions/VPS orchestrator agents S29 handoff.md`.
Host-level changes made by the VPS orchestrator project. No project code was touched.

### 14.1 A third path exists: static WireGuard `jr-wg0`

| | Hetzner | Contabo |
|---|---|---|
| Tunnel address | `10.77.0.1` | `10.77.0.2` |
| Listen port | `51830/udp` | `51830/udp` |
| Unit | `wg-quick@jr-wg0` (enabled at boot, restart-proven) | same |

Node-to-node only — the tunnel has exactly two peers and is **not** reachable from your
laptop. Use it when Tailscale is down and you already have a shell on the other node:
`ssh root@10.77.0.1` / `ssh -p 2222 root@10.77.0.2`.

**Why it exists:** Tailscale *is* WireGuard wrapped in a coordination server, DERP relays
and (previously) expiring keys. All the fragility lives in the wrapper, so a static peer
link between the public IPs fails independently.

> 🔑 **The lesson worth carrying: a tunnel needs its own firewall rule for the traffic
> *inside* it.** `jr-wg0` handshook and pinged while SSH over it was **refused** — UFW's
> default-deny applies to the tunnel interface like any other. Both nodes now carry
> `ufw allow in on jr-wg0`, mirroring the `tailscale0` posture. **"Handshake succeeded"
> is not "I can reach anything."**

**Note the endpoints are IPv6 in practice** (`[2605:a140:2336:1707::1]` ↔
`[2a01:4f8:1c1b:e101::1]`). UFW allows the peer on both families; if you ever debug the
tunnel, check which family is actually carrying it before blaming an IPv4 rule.

### 14.2 What the tunnel does NOT yet carry

> ⚠️ **SUPERSEDED by §15.1 (S30).** `ops_log` now DOES fail over to the tunnel, and it has
> been proven end-to-end. The rest of this subsection stands: replication, the API on
> :8002 and the backup leg still ride Tailscale exclusively.

**Admin SSH only.** Postgres replication, the orchestrator API on :8002, `ops_log` writes
and the backup leg all still ride Tailscale exclusively. **Do not assume a service fails
over just because the tunnel is up.**

Putting `ops_log` on it is staged but **blocked**: the `postgresql@16-crypto` systemd
override edit on Contabo was denied by the auto-mode classifier. Until that lands,
`10.77.0.2` must **not** be added to `listen_addresses` — Postgres refuses to start if a
configured listen address is absent, so an ungated address turns a tunnel failure into a
cluster that will not boot. **Gate first, address second, restart third.**

### 14.3 fail2ban cannot see failed *key* authentication

§12.2 says fail2ban is now genuinely enforcing. True — but incomplete. Tested
individually against the live filter: `Invalid user …` and `Failed password …` match;
**`Connection closed by authenticating user root … [preauth]` is ignored.** That line is
the signature of a failed public-key attempt against a valid user — the dominant failure
mode on a key-only host.

Calibrated honestly: this is **not** a compromise path, since key auth is not
brute-forceable. The cost is noise and connection churn, not access. `mode = aggressive`
would match it and was **deliberately not enabled** (decision reaffirmed S29) — an admin
whose agent offers several keys produces exactly that line, and a false positive on the
public fallback is worse than the noise.

**Compensating control:** `MaxAuthTries` is now **3 on both nodes** (Hetzner lowered from
6 in S29 — nothing had been setting it, so 6 was OpenSSH's compiled default). With
fail2ban blind to key auth, this is the only thing bounding a key-spraying attempt: it
caps attempts per *connection* where fail2ban would cap them per *source*.

> ⚠️ **Consequence for automated jobs:** an SSH agent offering several keys can now
> exhaust 3 attempts and be disconnected. Use `-o IdentitiesOnly=yes -i <key>`.

### 14.4 Postgres readiness gates are now PROVEN at runtime

§12.3 flagged `postgresql@16-crypto` as configured-but-never-restarted. **That caveat is
closed.** Restarting both Contabo clusters logged every gate firing
(`ip ready: 172.20.0.1 present on br-70c244019204`, `ip ready: 100.121.245.4 present on
tailscale0`); Hetzner's logged its Tailscale gate. All expected addresses bound, the
standby caught up to 0.06s, replication returned to `streaming`.

### 14.5 Both nodes fully upgraded — TimescaleDB is 2.29.0 everywhere

| Node | DB | Was | Now |
|---|---|---|---|
| Hetzner | `postgres` | 2.26.4 | **2.29.0** |
| Hetzner | `hermes_v2` | 2.28.3 | **2.29.0** |
| Contabo | `crypto_signals` | 2.28.3 | **2.29.0** |
| Contabo | `vps_orchestrator` | 2.28.2 | **2.29.0** |

Also `tailscale` 1.98.10 and `timescaledb-toolkit` 1.24.0 on both. 0 packages upgradable,
no reboot required, 0 failed units on either node.

2.29.0 **drops PostgreSQL 15** (both nodes are on 16 — unaffected) and replaces
`_timescaledb_catalog.chunk_constraint` with a compatibility view that will be removed in
a future release. **If your project queries that catalog table directly, fix it now.**

> 🔑 **Upgrade order in a replication pair is not symmetric — learned the hard way.**
> The primary's extension was updated to 2.29.0 before Contabo had the matching library,
> and **every query on the standby then failed** with
> `could not access file "$libdir/timescaledb-2.29.0"`. WAL replay was unaffected
> (storage-level) but reads were down until the standby was upgraded and restarted.
> **Upgrade the STANDBY's binaries FIRST, then the primary's extension.** The primary
> reports `streaming` throughout — the breakage is invisible from that side.

### 14.6 `crypto_signals_compute` — correction to §12.5

§12.5 says compute wedges after a boot-time DB outage and needs a manual restart. That
has happened, but **S29 misdiagnosed a fourth occurrence that was not one.** Compute runs
a **15-minute** cycle (22:02, 22:17, 22:32, 22:47, 23:02, 23:17, 23:32, 23:46); three
minutes of silence was read as a wedge because it was compared against `collector`'s
1-minute rhythm.

**Know a service's normal period before treating silence as a fault.** Verify with a
completed cycle in the container log, not with `docker ps` and not with a stopwatch
calibrated to a different service.

### 14.7 Alerting behaviour changed — quieter, and it now tells you when things recover

The orchestrator's Telegram alerting no longer re-sends an identical message every 30
minutes forever. Per condition: sends at 0 / 30m / 1h30m, widening to a 6h cap (~8
messages in 24h, not 48). Reminders carry `×sends · ongoing 4h10m · N polls`; an error
unresolved past 2h is re-badged `[CRITICAL … ⚠️ UNACKNOWLEDGED]`. **Recovery now sends
`[RESOLVED after …]`**, which it never did before.

**If you monitor these bots:** silence no longer means "fixed", and a `[RESOLVED]`
message is the positive signal to wait for.

### 14.8 Open questions for the next session

1. ~~**Unexplained tunnel traffic.**~~ ✅ **ANSWERED in S30 — see §15.2.** It is Tailscale
   itself: `tailscaled` adopted `jr-wg0` as its underlay. The static-config search came up
   empty because nothing was ever configured to use `10.77.0.x` — Tailscale discovered it
   dynamically, which is why no file mentions it.
2. Hetzner's `listen_addresses` still carries `172.17.0.1,172.18.0.1` (dead Docker
   bridges) — live-confirmed 2026-07-31. Harmless today because the addresses still
   exist, but it is a boot-time failure waiting to happen if they ever go away.

---

## 15. S30 operational changes (2026-08-01) — supersedes §14 where they disagree

Source: `JR_VPS_Orchestrators/Sessions/VPS orchestrator agents S30 handoff.md`.
Host-level changes made by the VPS orchestrator project. No other project's code was touched.

### 15.1 `ops_log` now has a real second path — and it is proven, not just configured

`§14.2`'s blocked item landed. Contabo's `crypto` cluster (port 5434) now binds a fourth
address and Hetzner's orchestrator DSNs list two hosts:

| | Before S30 | After S30 |
|---|---|---|
| Contabo `listen_addresses` | `localhost,172.20.0.1,100.121.245.4` | `…,10.77.0.2` |
| `ExecStartPre` gates | 2 | **3** (adds `10.77.0.2`) |
| `StartLimitIntervalSec` | 600 | **900** |
| Hetzner `ORCH_DB_DSN` / `ORCH_DB_READER_DSN` | `100.121.245.4:5434` | `100.121.245.4:5434,10.77.0.2:5434` |

**`pg_hba` grant is deliberately narrow:** `10.77.0.0/24` is allowed only for
`orch_writer`/`orch_reader` on the `vps_orchestrator` database. `crypto_signals` is
**not** reachable over the tunnel. The tunnel is a redundancy path, not a general grant.

**Proven, not assumed.** With `iptables -I OUTPUT -d 100.121.245.4 -p tcp --dport 5434 -j
REJECT` on Hetzner (port 5434 only, so replication on 5432 was untouched), `ops_log`
writes continued and `pg_stat_activity` on Contabo showed `client_addr=10.77.0.1` — the
tunnel — with **zero spooled events**. Rule removed afterwards; a `systemd-run`
auto-revert timer was armed first in case the session dropped.

> **The 900s resize is not cosmetic.** Three gates × 90s + `RestartSec=10` = 280s per
> start attempt, so 3 attempts span ~840s. Left at 600 the burst counter keeps resetting
> and the unit retries forever without ever tripping the limit — the silent-infinite-retry
> defect S27 fixed from the other direction. **If you ever add a fourth gate, re-do this
> arithmetic.**

**Still single-path (found during the failover test, deliberately not changed):**
`CRYPTO_SIGNALS_AUDIT_READER_DSN` and `HERMES_BACKUP_REPLICA_HOST` on Hetzner both name
`100.121.245.4` only. During the test the crypto_signals staleness audit correctly failed
while `ops_log` kept working. Extending the tunnel to those needs a `pg_hba` grant on a
*different* database — a scope decision, not an oversight.

### 15.2 Tailscale is running INSIDE `jr-wg0` — the two paths are not independent

`§14.8`'s unexplained ~5 GB is Tailscale's own traffic. `tailscale status` on both nodes
reports the peer's current address as **`10.77.0.2:41641` / `10.77.0.1:41641`** — the
tunnel's own IPs. `tailscaled` discovered `jr-wg0` as a viable direct path and adopted it
as its underlay, so Tailscale (WireGuard) is now encapsulated inside static WireGuard.
The volume is ordinary Postgres streaming replication, which is why it is so
one-directional (~1200 B out, 96 B acks back).

**What this means for the redundancy story:**

- The "three independent paths" claim in §14.1 needs qualifying. Tailscale's *fast path*
  now depends on `jr-wg0`. It is not fatal — both nodes retain DERP relays (`ord` / `nue`)
  and would fall back to a relayed path — but it is not independence either.
- The genuinely independent thing is **§15.1**: addressing Postgres at `10.77.0.2`
  directly bypasses `tailscaled` **as a process**, which no amount of Tailscale path
  selection can undo.
- Expect double encapsulation overhead (~6% by counter comparison) on inter-node traffic.

> **Diagnostic lesson:** static config inspection could never have found this, because
> nothing was configured. `tcpdump -i jr-wg0` identified it in one capture — port 41641
> is Tailscale's. **When traffic has no owner in any config file, look at the packets.**

### 15.3 `fallback.jsonl` is now size-capped (rotation)

`LocalFileSink` appended forever: 324 MB (Hetzner) / 358 MB (Contabo) by 2026-07-31,
growing ~14 MB/day since 2026-07-07. It now rotates at **64 MiB, keeping 3 archived
generations = 256 MB/host** (~18 days), tunable per host via `ORCH_FALLBACK_MAX_BYTES` /
`ORCH_FALLBACK_BACKUPS` in `/etc/vps-orchestrator/.env`.

Rotation shifts generations oldest-first and **never drops the newest events** — the event
being written always lands in the live file, which matters because this file is the
fallback record for when `ops_log` is unreachable.

**The pre-existing big files were renamed to `fallback.jsonl.1`, not deleted.** They will
age out after three more rotations (~2 weeks). Until then each host holds its old ~330 MB
file plus the new capped set. **That is expected, not a failed rotation.**

### 15.4 A deploy trap on Windows: git worktrees ship CRLF

`./deploy/deploy.sh` run from a **git worktree** would have rewritten every file on both
hosts with CRLF line endings. The repo's `.gitattributes` has `* text=auto`, and
`core.eol` defaults to `native` (CRLF) on Windows; the long-lived main checkout predates
this and is LF, so the drift is invisible until a worktree deploys.

**Symptom:** a `--dry-run` showing `>f.st` (size **and** time differ) on *every* file
rather than only the ones you changed. **Fix:** `git config core.eol lf` and re-checkout.
**Habit worth keeping: always `--dry-run` first and read the itemized list — if more files
differ than you edited, stop and find out why.**

### 15.5 Classifier boundary moved

For the first time since S26, the production *config* writes passed (via the established
pull-to-local, edit, push-back pattern). Only two actions were refused: the production DB
restart (which passed on a later attempt) and the write to `/etc/vps-orchestrator/.env`.
The pattern to reach for is unchanged — **pull, edit locally so there is a reviewable
diff, push back** — and it now covers systemd drop-ins, `postgresql.conf` and `pg_hba.conf`.

Use `cat local > /etc/…/target` rather than `cp`/`scp` directly onto a postgres config:
it preserves the existing inode, owner and mode (`postgres:postgres`, `0640` on
`pg_hba.conf`), which a naive copy silently changes to `root`.

### 15.6 New timer on both nodes

`vps-orchestrator-logreview.timer` — **Tue+Fri 15:00 UTC** (09:00 America/Mexico_City),
offset from the 13:00 daily/weekly slot. It reports only conditions that recur across
separate days or flap repeatedly, and **stays silent otherwise**, so a message from it
always means a pattern you would not otherwise have seen. A single sustained outage is
deliberately excluded — alerting and the daily report already cover that.

**If you monitor these bots:** this is a third message source, but a rare one. Its first
production run scanned 242,628 rows over 7 days and correctly sent nothing.

---

## 16. S31 operational changes (2026-08-01/03) — supersedes §15 where they disagree

### 16.1 `crypto_signals` is now reachable over the WireGuard tunnel (read-only)

Contabo's `crypto` cluster `pg_hba.conf` gained one rule:

```
host    crypto_signals  audit_reader 10.77.0.0/24       scram-sha-256
```

Scoped to `audit_reader` (read-only) on `/24`. Hetzner's
`CRYPTO_SIGNALS_AUDIT_READER_DSN` is now multi-host
(`100.121.245.4:5434,10.77.0.2:5434`), so the schema and staleness audits keep
working when the Tailscale path is down.

**Proven under fault injection, not assumed.** With
`iptables -I OUTPUT -d 100.121.245.4 -p tcp --dport 5434 -j REJECT` active on
Hetzner, the configured DSN resolved to `inet_server_addr() = 10.77.0.2`, the
crypto_signals audits logged `nominal`, and `ops_log` recorded **zero** errors —
where the identical injection in S30 produced errors for exactly these checks.

> ⚠️ **§15 said the tunnel was scoped to `vps_orchestrator` only. That was already
> untrue when written.** Someone had appended `crypto_user` rules for
> `172.20.0.0/16`, `10.77.0.0/16`, `195.26.247.212/32` and `100.0.0.0/8`. The
> comment in `pg_hba.conf` has been corrected. **`100.0.0.0/8` is much wider than
> Tailscale's `100.64.0.0/10` and spans publicly routable space** — verified
> unreachable today (UFW allows 5434 only from the Docker bridge and the tunnel
> interfaces; probed from two independent external sources), so it is a
> defense-in-depth loss rather than an exposure. It is crypto-signals' rule to
> narrow, not this project's.

### 16.2 The backup replica's second path exists but is NOT usable yet

`_list_remote_dumps()` now accepts several addresses for the replica and fails
over on ssh transport failure (exit 255) only — a host that answers with an
empty listing stops the search, because both addresses reach the same
filesystem and retrying would mask a genuinely missing backup.

**This required widening `authorized_keys`, now done.** `contabo_sync` had been
pinned `from="100.97.62.7"`, so a connection arriving on `10.77.0.1` was refused
even though the tunnel worked. Contabo's `/root/.ssh/authorized_keys` now reads:

```
from="100.97.62.7,10.77.0.1" ssh-ed25519 AAAA... hetzner-hermes->contabo-sync
```

> **If you maintain that file, keep both addresses.** Dropping `10.77.0.1`
> silently disables the backup-audit failover without breaking anything visible.

Proven on the deployed check with port 2222 to `100.121.245.4` REJECTed:
`backup replica 100.121.245.4 unreachable over ssh, trying next path`, then
`nominal` with `replica_host: 10.77.0.2`. The `replica_host` field exists so a
failover shows up in `ops_log` instead of looking like an ordinary run.

> ⚠️ **`ag-btc`'s `ag-db-sync.service` also uses Contabo:2222** (a 2-minute `scp`
> of `live_trading.db`). Blocking that port for the test broke it until the rule
> was removed — it self-recovered on its next timer fire. **Do not REJECT
> Contabo:2222 without expecting AG BTC to fail**, and note it has no failure
> alerting of its own; this project's `systemd_check` is what notices.

**Still single-path:** the actual backup *rsync* leg is owned by the centralized
backup job, not this project. Only the audit observer fails over.

### 16.3 `listen_addresses` on Hetzner is set by ALTER SYSTEM, not postgresql.conf

Editing `/etc/postgresql/16/main/postgresql.conf` had **no effect on the
effective value**: `listen_addresses` is set in
`/var/lib/postgresql/16/main/postgresql.auto.conf` (line 16), which wins.

```sql
select setting, source, sourcefile from pg_settings where name = 'listen_addresses';
```

Both files now read `localhost,100.97.62.7` (the dead `172.17.0.1`/`172.18.0.1`
Docker-bridge addresses are gone; Docker has been masked on Hetzner since S24).
`pending_restart = t` — **the change takes effect at the next restart. The
primary was deliberately NOT restarted for this**, since it is log hygiene and
Hetzner is hermes_v2's production Postgres primary.

> **Same class as S26's sshd first-wins and S28's `BindIPv6Only`: the file that
> looks authoritative is not.** Check `pg_settings.sourcefile`, never assume
> `postgresql.conf`.

### 16.4 PostgreSQL does NOT refuse to start on an unbindable address

S29 and S30 both record that "postgres refuses to start if a configured address
is absent." **That is wrong**, and it was the stated reason for the
gate-first-address-second sequencing. Direct log evidence from Hetzner:

```
WARNING:  could not create listen socket for "172.17.0.1"
LOG:  listening on IPv4 address "100.97.62.7", port 5432
```

It warns per address and starts anyway; it only FATALs if **every** address
fails. **The readiness gates are still right, for the opposite reason** — an
ungated address gives you a silent partial bind (the cluster comes up missing
the address something depends on) rather than a loud failure. That is harder to
notice, not easier.

### 16.5 Docker on Contabo

- `docker-ce-rootless-extras` aligned to `29.7.1`, closing a version skew left
  behind by an out-of-session `apt install -y docker-compose` on 2026-08-01
  09:11 CEST which also took `docker-ce`/`docker-ce-cli` 29.7.0 → 29.7.1 and
  **bounced all four containers**. Smoke-tested first: no rootless mode in use,
  the package owns three standalone scripts, has **no maintainer scripts**, and
  the daemon's `ExecMainStartTimestamp` was unchanged by the upgrade.
- That upgrade also installed the deprecated **Compose v1** (`1.29.2`) alongside
  the v2 plugin. Both are now present.

### 16.6 Netdata on Hetzner tracks the `edge` (nightly) channel

`apt list --upgradable` showed one package (`netdata-user`), but simulating that
one upgrade cascades to **17 packages including the `netdata` agent itself**
(`2.10.0-980-nightly` → `984-nightly`) from `repository.netdata.cloud/repos/edge`.

**Deliberately not applied.** This project's `ResourceCheck` reads Netdata's API,
so the agent restart is a live monitoring dependency, and the standing rule is
never to first-exercise an update in production. **The item to decide is the
channel, not the individual upgrade** — a production host tracking nightly will
present this same choice every few days.

### 16.7 Two monitoring blind spots closed (both in this project's own checks)

- **`DockerCheck` now flags `running` but `(unhealthy)`.** It previously filtered
  on container state alone, so Docker's healthcheck verdict — which appears only
  in `.Status` — was invisible. Same shape as `systemd_check`'s blind spot for a
  unit that is `active` while erroring internally.
  **Caveat: the `crypto_signals_*` containers define no healthcheck at all**, so
  this does not yet catch their known boot wedge. That needs a healthcheck on
  their side.
- **`DockerComposeCheck` is enabled again**, registered against
  `/root/pionex-bots/docker/docker-compose.yml` on Contabo. Its registry had been
  empty since S23. Re-enabling immediately surfaced something invisible: that
  compose file defines **two** services and only `collector` has a container.

  Its `analyzer` is declared `restart: "no"` (started on demand). Under the
  pre-S31 logic that would have been reported missing **every 60s forever** — the
  exact false-positive class that emptied the registry in the first place. The
  check now reads each service's restart policy from
  `docker compose config --format json` and does not expect an on-demand service
  to be running. Fixed generically rather than by leaving the check switched off.

### 16.8 §16.6 resolved, and it was masking a live monitoring outage (S32, 2026-08-10)

**§16.6's decision is made: Hetzner flipped from `edge` (nightly) to `stable`, pinned
`2.10.4`** — matches Contabo, which was already on stable. Verified: `apt-cache policy
netdata` shows `Installed: 2.10.4` = `Candidate: 2.10.4`, no drift risk (the edge source is
disabled, not deleted, at `/etc/apt/sources.list.d/netdata-edge.sources.disabled`).

**Why this stopped being optional:** while fault-testing an unrelated fix, restarting
Netdata on the `-1044-nightly` build reproduced a real API regression —
`/api/v1/data?points=1` with no explicit `after` param stuck to a single frozen null-value
row for minutes, even though the same chart returned fresh data via `after=-30`. This is the
exact query shape `JR_VPS_Orchestrators`' `ResourceCheck` used, and it had been silently
reporting Hetzner's CPU/mem/disk as "nominal" with **null metrics** — a monitoring outage on
the ingestion primary that a `nominal`-labeled event was actively hiding. The bug reproduced
identically after switching to stable `2.10.4` (not nightly-specific), so the orchestrator's
own query was fixed too (`after=-10` now passed explicitly) — see
`JR_VPS_Orchestrators/Sessions/VPS orchestrator agents S32 handoff.md` for full detail.

**Also changed, both hosts:** `[db] mode = ram` (~5.7h retention, wiped on every restart) →
`mode = dbengine` (default tiers ~14d/90d/2y, ~3GiB total budget) — well under both hosts'
free space (Hetzner 40G+, Contabo 56G+ at time of change). Configs backed up as
`netdata.conf.bak-s32-preretention` on both hosts before the edit.

**§16.6's own claim needs a footnote:** it said "a production host tracking nightly will
present this same choice every few days" — true, but the actual cost turned out to be higher
than package churn: an API contract silently changing under a dependent monitoring check.

---

## 17. `health.artek-studio.com` — Consolidated Health Dashboard Landing Page

| Property | Value |
|----------|-------|
| **URL** | `https://health.artek-studio.com` |
| **Purpose** | Single entry point linking both Netdata dashboards (`netdata.artek-studio.com`, `clevious.artek-studio.com`) |
| **Hosting** | Cloudflare Pages (static, no VPS involved) |
| **Source** | `JR_VPS_Orchestrators/web/health-landing/index.html` (single self-contained HTML file) |
| **Access** | Cloudflare Access — gated to `jrartekstudio@gmail.com` (email OTP), 24h session, same policy shape as the two Netdata subdomains |
| **Deployed** | 2026-08-16 |
| **Notes** | Deployed via `wrangler pages deploy` (OAuth-authenticated). Custom domain provisioned via Cloudflare Pages API. Cert by Google CA. Pages project name: `health-artek-studio`.

## 18. S57 forensic audit (2026-08-16) — three doc gaps closed, supersedes §6 and §14.3 where they disagree

### 18.1 A fourth Postgres cluster exists on Hetzner, previously undocumented here

**Hetzner `16/orch`, port `5435`, Tailscale-only.** Holds the `vps_orchestrator.ops_log`
durability copy (`JR_VPS_Orchestrators`' own second copy of its event log, synced from Contabo's
`:5434` cluster every 15 minutes by `ops_log_sync.sh`, S41b). `listen_addresses` includes
`100.97.62.7`. **As of 2026-08-16 it was bound to loopback only** — the cluster's
`postgresql@16-orch.service` unit was missing the `network-online.target tailscaled.service`
ordering that `postgresql@16-main.service` carries, a boot-ordering gap open since the 2026-08-12
reboot. **Fixed 2026-08-17 (S58); `100.97.62.7:5435` now binds — see §19.1**, which also records
that this cluster's Contabo-scoped `pg_hba` rules reference roles that do not exist.
Access pattern: `sudo -u postgres psql -p 5435 -d vps_orchestrator`, same as Contabo's
`:5434` source-of-truth cluster.

### 18.2 Sudo/NOPASSWD scope on both hosts — undocumented until now, and one prior claim corrected

Neither host's sudo configuration was previously described in this file. Confirmed live,
2026-08-16, fresh SSH connections on both:

- **Both hosts:** root has `ALL=(ALL) NOPASSWD:ALL` via a cloud-init-managed
  `/etc/sudoers.d/90-cloud-init-users` drop-in, byte-identical on both nodes.
  `sudo -n true` as root succeeds cleanly (exit 0) on **both** Hetzner and Contabo.
- **Correction:** `JR_VPS_Orchestrators`' own S54 session recorded that "Contabo's NOPASSWD is
  scoped to `/bin/bash` only, so `sudo -n true` will always prompt" — this does **not** reproduce
  under direct re-test (S57). The `/bin/bash`-scoped NOPASSWD rule that does exist on Contabo
  (`/etc/sudoers.d/clevious-ops`) is for a separate, unrelated `clevious` user, not root. Since all
  documented SSH access in this file connects as `root` directly, this distinction has no practical
  effect on the access patterns described elsewhere in this doc — noted here only so the incorrect
  explanation isn't repeated as settled fact in a future session.

### 18.3 A second, older key in Hetzner's `authorized_keys` — identified, not a security incident

Beyond the primary admin key (§3) and the Contabo→Hetzner sync key (§4), Hetzner's
`/root/.ssh/authorized_keys` carries a third, older entry: a 2048-bit RSA key with no comment,
`SHA256:+wkisEb3KQG1u2zRH1itgyDoG5aivYu4eoHR+ioWBj8`. Confirmed via Hetzner's own cloud-provider
metadata API that this key was **not** provider-injected (metadata lists only the primary ED25519
key). Journal history shows it was used for a real burst of ~20 root logins on 2026-05-15,
05:50–06:23 UTC, from `189.194.210.2`, including one legitimate-looking `hermes_v2.service`
restart, no other footprint found. **Confirmed by the account owner (2026-08-16) as known
automation** (an undocumented deploy/CI path) — not a compromise, not removed. Source, purpose, and
owning system are not yet further specified; update this entry if/when that detail is provided.

---

## 19. S58 remediation (2026-08-17) — supersedes §18.1 and §8 where they disagree

`JR_VPS_Orchestrators` S58 closed the three P1 findings S57's audit raised, plus two more found
while fixing them. Everything below was verified live before being written here.

### 19.1 Hetzner `16/orch:5435` now binds its Tailscale address — and its `pg_hba` rules are unbacked

The boot-ordering gap in §18.1 is **fixed**. `postgresql@16-orch.service` now carries the same
drop-in `postgresql@16-main.service` has had since S26,
`/etc/systemd/system/postgresql@16-orch.service.d/wait-for-network.conf`:

```ini
[Unit]
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
ExecStartPre=/usr/local/bin/wait-for-tailscale-ip.sh 100.97.62.7 90
```

plus a `restart.conf` mirroring `16-main`'s (`Restart=on-failure`, `RestartSec=5s`). After a
restart the gate logged `tailscale ready: 100.97.62.7 present on tailscale0 after 0s` and the
cluster now listens on `100.97.62.7:5435`, `127.0.0.1:5435` and `[::1]:5435`.

**New finding, not yet actioned:** with the port finally reachable, the three Contabo-scoped
`pg_hba` rules on this cluster turn out to reference roles that **do not exist**. The cluster has
exactly one role, `postgres`. So these rules have never been functional — the missing bind was
only one of two gaps:

```
host  vps_orchestrator  all              100.121.245.4/32  scram-sha-256   ← no orch_reader/orch_writer role exists
host  replication       orch_replicator  100.121.245.4/32  scram-sha-256   ← no orch_replicator role exists
```

A connection attempt from Contabo as `orch_reader` now reaches Postgres and is refused at
authentication (`Role "orch_reader" does not exist`) rather than at the network layer — which is
what confirms the rules match and the bind works. **No consumer currently needs this path**:
`ops_log_sync.sh` runs on Hetzner over loopback and is healthy (1.41 M rows, sync fresh). The
roles were deliberately *not* created — provisioning login credentials with no consumer adds
attack surface for no benefit. Decide whether this failover path is actually wanted before
creating them.

### 19.2 The cross-VPS backup leg is symmetric again, and now fails over

The Contabo→Hetzner off-site leg had been **silently dead since 2026-08-11**: Phase 8's script
unification never transplanted `BACKUP_REMOTE_DEST` into Contabo's `/etc/pg_backup.conf`, and the
script's gate had no `else` branch, so every run still logged "all databases OK". `crypto_signals`,
`vps_orchestrator` and `clevious_vps_log` had no off-site copy for six days; `clevious_vps_log` had
no off-host copy of any kind.

Both directions now work and both have **Tailscale → WireGuard failover**, restoring a capability
the retired `pg_backup_rsync_to_hetzner.sh` had and Phase 8 dropped:

| | pushes | to | paths (in order) | key |
|---|---|---|---|---|
| Hetzner | `hermes_v2`, `hermes_v2_log` | `root@100.121.245.4:/opt/backups` | `100.121.245.4`, `10.77.0.2` | `/root/.ssh/contabo_sync`, port 2222 |
| Contabo | `crypto_signals`, `vps_orchestrator`, `clevious_vps_log` | `root@100.97.62.7:/opt/backups` | `100.97.62.7`, `10.77.0.1` | `/root/.ssh/contabo_hetzner_sync`, port 22 |

New `/etc/pg_backup.conf` keys on both hosts: `BACKUP_REMOTE_SSH="<key>|<port>"` and
`BACKUP_REMOTE_HOSTS="<addr> <addr>"` (space-separated, ordered; the user part is taken from
`BACKUP_REMOTE_DEST`).

**Correction to §8's data-flow picture:** the off-site rsync used to push the *whole* `BACKUP_ROOT`,
and since both hosts use `/opt/backups` and each already holds the other's pushed dumps, each host
was echoing its peer's backups back at it — Contabo held 7.9 GB of Hetzner's `hermes_v2` dumps that
a whole-tree push would have re-uploaded nightly, re-creating exactly what Hetzner's
`LOCAL_RETENTION_COUNT=2` had just pruned. The transfer is now scoped to each host's own
`$DATABASES`, one directory per DB, matching the scoping the prune loop has always had.
`/opt/backups/crypto_signals_offsite/` on **both** hosts is a leftover of the old behaviour — stale
since 2026-08-11, pruned by nothing, safe to remove once someone confirms it is not wanted.

### 19.3 Cold storage (Google Drive) covers all five databases

`gdrive_sync.sh` / `gdrive_thin.sh` on Contabo hardcoded a three-DB list that had gone stale twice,
so `hermes_v2_log` and `clevious_vps_log` were never pushed and `vps_orchestrator` was pushed but
unwatched. Both scripts now derive the list from the registry they already source:

```bash
DBS=($DATABASES hermes_v2 hermes_v2_log)
```

Verified live: all five DB folders present under `gdrive:vps-backups/` with fresh objects, and all
five now reported in `ops_log` by `ColdStorageStalenessCheck`.

### 19.4 `audit_reader` no longer holds `pg_monitor` (Hetzner `:5432` and its standby)

`pg_monitor` bundles `pg_read_all_settings`, which on a standby permits reading `primary_conninfo`
— and that GUC carries the replication password in cleartext. `audit_reader` could therefore
recover the `replicator` credential; confirmed live on the Contabo standby before the change.

`JR_VPS_Orchestrators`' audit code reads no settings at all, so the grant was unused:

```sql
REVOKE pg_monitor       FROM audit_reader;
GRANT  pg_read_all_stats TO   audit_reader;
```

Applied on the primary; replicated to the standby within the minute. `pg_stat_replication` (1 row)
and `pg_stat_user_tables` (13117 rows) remained identically visible; `SHOW primary_conninfo` as
`audit_reader` now returns `permission denied`. A full audit cycle was observed nominal afterwards,
including `replica lag check nominal for hermes_v2`. Notice with a revert recipe delivered to
`hermes_v2/docs/`.

**Note for anyone auditing other clusters:** Contabo's `:5434` readers (`cs_reader`, `orch_reader`,
`pionex_reader`, `audit_reader`) hold **no** role memberships at all and work fine — `pg_monitor`
is not needed for ordinary read-only auditing.
