# Archived monitoring infra-as-code (S17, 2026-09-06)

These files described a **Prometheus + Grafana** stack that was **never the live
monitoring on the Hetzner host**. The live stack is and has been **netdata**
(systemd `netdata`, local API on `127.0.0.1:19999`) — confirmed live S13 and
again S17.

State on the host (S17):
- `prometheus.service` — installed but `inactive` + `disabled`.
- Grafana — not installed at all.

They were kept in `deploy/` as "possible future re-deploy" scaffolding, but:
- `prometheus.service` carried stale `After=/Wants=hermes_v2.service` (a
  decommissioned unit) and violated Tier 0 rules T0.2 (no `StartLimitIntervalSec`)
  and T0.3 (`ProtectSystem=strict` + `ReadWritePaths` with no `StateDirectory=`).
- `prometheus_rules.yml`'s alert thresholds (disk > 85 %, TLS < 21d / < 7d,
  `AgentDown`) were **never firing**. Those thresholds now live in the real,
  running Tier 3 guardrail: `scripts/audit/hermes_vps_guardrail.py`.

If Prometheus/Grafana is ever genuinely wanted here, start from these files but
treat every host-coupling reference as stale and re-derive it. Until then, this
is history, not config — do not deploy from here.

> Note: the **host-side** `/etc/systemd/system/prometheus.service` teardown is
> owned by JR Hermes Ingestor (S16 escalation, item 5). Archiving the repo copy
> here is JR Hermes VPS's own housekeeping and does not touch the host.
