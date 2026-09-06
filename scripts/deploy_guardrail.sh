#!/usr/bin/env bash
# scripts/deploy_guardrail.sh — Tier 3 / Tier 4 deployment assertion (S17)
#
# CONTINUOUS_IMPROVEMENT_STANDARD.md Rule T3.11: deploying a guardrail asserts the
# executable bit AND a real dry-run. chmod +x is part of deployment, not an
# assumption. Step 4 (heartbeat proven) is the one that would have caught the S67
# 203/EXEC failure.
#
# Run ON the Hetzner host, from /opt/hermes-vps, as root, AFTER the repo is at the
# S17 commit and deploy/sql/S17_findings_log_tier4.sql has been applied.
set -euo pipefail

REPO=/opt/hermes-vps
PY="$REPO/.venv/bin/python3"
cd "$REPO"

echo "== 1. executable bit + syntax =="
for f in scripts/log_finding.py \
         scripts/audit/hermes_vps_guardrail.py \
         scripts/audit/hermes_vps_escalation_check.py \
         scripts/audit/hermes_vps_reconcile.py; do
  chmod +x "$f"
  test -x "$f"
  "$PY" -m py_compile "$f"
done
echo "   ok"

echo "== 2. real dry-run (every check runs; nothing written: DB, Telegram, state, heartbeat) =="
set -a; . /root/.hermes_vps/.env; set +a
HERMES_VPS_STATE_DIR=/tmp/hermes-vps-deploycheck "$PY" scripts/audit/hermes_vps_guardrail.py --dry-run
rm -rf /tmp/hermes-vps-deploycheck

echo "== 3. unit syntax =="
systemd-analyze verify \
  /etc/systemd/system/hermes-vps-guardrail.service \
  /etc/systemd/system/hermes-vps-guardrail.timer \
  /etc/systemd/system/hermes-vps-escalation.service \
  /etc/systemd/system/hermes-vps-escalation.timer
echo "   ok"

echo "== 4. start once, prove the heartbeat =="
systemctl start hermes-vps-guardrail.service
test -f /var/lib/hermes-vps/guardrail.heartbeat
echo "   heartbeat: $(cat /var/lib/hermes-vps/guardrail.heartbeat)"

echo "== 5. start the escalation check once =="
systemctl start hermes-vps-escalation.service
systemctl is-active hermes-vps-escalation.service || true

echo
echo "ALL T3.11 DEPLOYMENT ASSERTIONS PASSED — safe to: systemctl enable --now hermes-vps-{guardrail,escalation}.timer"
