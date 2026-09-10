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

# REPO/PY overridable so a staged git-worktree can be smoke-tested before the
# live `git pull` (SMOKE-TEST BINDING RULE). Defaults are the live deploy paths.
REPO="${REPO:-/opt/hermes-vps}"
PY="${PY:-/opt/hermes-vps/.venv/bin/python3}"
cd "$REPO"

echo "== 1. committed executable bit + syntax =="
# S51: the old form did `chmod +x` and THEN `test -x` — self-fulfilling, could
# never catch a repo committed 0644. A fresh clone of a 0644 guardrail is exactly
# the S67 203/EXEC silent-failure. Assert the COMMITTED mode is 100755 first, then
# chmod only as belt-and-braces repair of the working tree.
for f in scripts/log_finding.py \
         scripts/emission_state.py \
         scripts/audit/hermes_vps_guardrail.py \
         scripts/audit/hermes_vps_escalation_check.py \
         scripts/audit/hermes_vps_reconcile.py \
         scripts/audit/hermes_vps_health_check.py \
         scripts/audit/hermes_vps_daily_digest.py; do
  mode=$(git ls-files -s -- "$f" | awk '{print $1}')
  if [ "$mode" != "100755" ]; then
    echo "   FAIL: $f is committed as ${mode:-MISSING}, not 100755 — a fresh clone would not be executable"
    echo "         fix: git update-index --chmod=+x $f && git commit"
    exit 1
  fi
  chmod +x "$f"
  "$PY" -m py_compile "$f"
done
echo "   ok"

echo "== 1b. offline test suite (emission gate + escalation classification) =="
if [ -d tests ] && "$PY" -c "import pytest" 2>/dev/null; then
  "$PY" -m pytest -q tests/ || { echo "   FAIL: unit tests red — do not deploy"; exit 1; }
else
  echo "   (pytest or tests/ unavailable on host — offline suite runs in CI/dev)"
fi

echo "== 2. real dry-run (every check runs; nothing written: DB, Telegram, state, heartbeat) =="
set -a; . /root/.hermes_vps/.env; set +a
HERMES_VPS_STATE_DIR=/tmp/hermes-vps-deploycheck "$PY" scripts/audit/hermes_vps_guardrail.py --dry-run
rm -rf /tmp/hermes-vps-deploycheck

echo "== 2b. escalation check dry-run (classify + reconcile read-only; nothing written) =="
( unset FINDINGS_DB_URL
  HERMES_VPS_STATE_DIR=/tmp/hermes-vps-esc-deploycheck \
    "$PY" scripts/audit/hermes_vps_escalation_check.py --dry-run )
rm -rf /tmp/hermes-vps-esc-deploycheck

echo "== 3. unit syntax =="
systemd-analyze verify \
  /etc/systemd/system/hermes-vps-guardrail.service \
  /etc/systemd/system/hermes-vps-guardrail.timer \
  /etc/systemd/system/hermes-vps-escalation.service \
  /etc/systemd/system/hermes-vps-escalation.timer
echo "   ok"

echo "== 3b. StartLimitBurst must clear the timer cadence (S17: Burst=8 vs 12/h tripped start-limit-hit) =="
for pair in "guardrail:5" "escalation:15"; do
  unit=${pair%%:*}; mins=${pair##*:}
  per_hour=$(( 60 / mins + 1 ))          # +1 for the boundary run
  burst=$(systemctl show "hermes-vps-$unit.service" -p StartLimitBurst --value)
  interval=$(systemctl show "hermes-vps-$unit.service" -p StartLimitIntervalUSec --value)
  if [ "$interval" = "1h" ] && [ "${burst:-0}" -le "$per_hour" ]; then
    echo "   FAIL: hermes-vps-$unit Burst=$burst <= ${per_hour}/h — will hit start-limit within the hour"
    exit 1
  fi
  echo "   ok: hermes-vps-$unit Burst=$burst > ${per_hour}/h"
done

echo "== 4. start once, prove the heartbeat =="
systemctl start hermes-vps-guardrail.service
test -f /var/lib/hermes-vps/guardrail.heartbeat
echo "   heartbeat: $(cat /var/lib/hermes-vps/guardrail.heartbeat)"

echo "== 5. start the escalation check once =="
systemctl start hermes-vps-escalation.service
systemctl is-active hermes-vps-escalation.service || true

# ---- S18 regression guards: the escalation check must not spew steady-state INFO
# nor insert INFO rows as action_status='open' (that is the bug S18 fixed) --------
psql_scalar() { psql "$HERMES_VPS_LOG_DB_URL" -tAc "$1" | tr -d '[:space:]'; }

echo "== 6. bounded-emission assertion (S18) =="
# Step 5 already ran the check once; this is the 2nd consecutive run. In steady
# state (no state change, hourly roll-up already spent) it must emit 0 rows.
# (Rare false-fail if a real WARNING or the hour boundary lands between the two
#  runs — re-run the script.)
T0=$(psql_scalar "SELECT extract(epoch from now())::bigint")
systemctl start hermes-vps-escalation.service
sleep 3
NEW=$(psql_scalar "SELECT count(*) FROM findings_log
                    WHERE session_ref LIKE 'vps-escalation-%' AND ts > to_timestamp($T0)")
if [ "${NEW:-99}" -ne 0 ]; then
  echo "   FAIL: a steady-state escalation run emitted $NEW row(s) — emission gate not active"
  psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT ts,severity,summary FROM findings_log
       WHERE session_ref LIKE 'vps-escalation-%' AND ts > to_timestamp($T0) ORDER BY ts"
  exit 1
fi
echo "   ok: 2nd consecutive steady-state run emitted 0 rows"

echo "== 7. action_status assertion (S18) — no INFO row may enter 'open' =="
OPEN_INFO=$(psql_scalar "SELECT count(*) FROM findings_log
                          WHERE severity='info' AND action_status='open'")
if [ "${OPEN_INFO:-99}" -ne 0 ]; then
  echo "   FAIL: $OPEN_INFO INFO row(s) with action_status='open' — run deploy/sql/S18_findings_log_info_settle.sql"
  exit 1
fi
echo "   ok: 0 INFO rows are 'open'"

echo "== 7b. Tier 4 queue integrity (S51) — no WARNING/CRITICAL row settled without triage =="
# deploy/sql/S17_findings_log_tier4.sql retro-closed every open row older than
# 7 days regardless of severity, silently emptying the escalation ladder. Any
# warning/critical row in 'no_action_needed' must carry an explicit human
# 'triage:' note in detail (deploy/sql/S51_findings_log_severity_triage.sql),
# never be swept there by a bulk UPDATE.
UNTRIAGED=$(psql_scalar "SELECT count(*) FROM findings_log
                          WHERE severity IN ('warning','critical')
                            AND action_status='no_action_needed'
                            AND (detail IS NULL OR
                                 (position('triage:' in lower(detail)) = 0
                                  AND position('[meta:' in lower(detail)) = 0))")
if [ "${UNTRIAGED:-99}" -ne 0 ]; then
  echo "   FAIL: $UNTRIAGED WARNING/CRITICAL row(s) settled with no triage stamp — run deploy/sql/S51_findings_log_severity_triage.sql (review each first)"
  psql "$HERMES_VPS_LOG_DB_URL" -c "SELECT id,ts::date,severity,left(summary,60) FROM findings_log
       WHERE severity IN ('warning','critical') AND action_status='no_action_needed'
         AND (detail IS NULL OR position('triage:' in lower(detail)) = 0) ORDER BY id"
  exit 1
fi
echo "   ok: every settled WARNING/CRITICAL row carries a triage stamp"

echo "== 8. T-LOG.3 guard — no retention policy on findings_log =="
RET=$(psql_scalar "SELECT count(*) FROM timescaledb_information.jobs
                    WHERE proc_name LIKE '%retention%' AND hypertable_name='findings_log'")
if [ "${RET:-99}" -ne 0 ]; then
  echo "   FAIL: $RET retention job(s) on findings_log — T-LOG.3 forbids retention on this table"
  exit 1
fi
echo "   ok: 0 retention jobs"

echo "== 9. S19b anti-deadlock guards =="
# 9a — the units themselves must not be `failed` right now (steps 4/5/6 ran them).
#      Before S19b a CRITICAL finding exited 1 -> the oneshot went `failed` ->
#      the guardrail alarmed on it -> the escalation check escalated that ->
#      neither unit could ever return to green.
for u in hermes-vps-guardrail hermes-vps-escalation; do
  st=$(systemctl is-failed "$u.service" || true)
  if [ "$st" = "failed" ]; then
    echo "   FAIL: $u.service is 'failed' after a normal run — exit-code contract regressed (must be 0 = 'audit ran')"
    journalctl -u "$u.service" -n 20 --no-pager
    exit 1
  fi
done
echo "   ok: both units clean after their deploy-check runs"
# 9b — check_failed_units() must exclude the two own units from CRITICAL.
# `systemctl list-units --no-legend` emits NO header line — the fakes match that.
"$PY" - <<'PYEOF'
import sys
sys.path.insert(0, "scripts"); sys.path.insert(0, "scripts/audit")
from unittest import mock
import hermes_vps_guardrail as g
own = ("hermes-vps-guardrail.service loaded failed failed x\n"
       "hermes-vps-escalation.service loaded failed failed x\n")
with mock.patch.object(g.subprocess, "run",
                       return_value=mock.Mock(stdout=own, returncode=0)):
    out = g.check_failed_units()
assert len(out) == 1 and out[0].severity == "info", out
assert "own units excluded" in (out[0].detail or ""), out
with mock.patch.object(g.subprocess, "run",
                       return_value=mock.Mock(stdout=own + "some-other.service loaded failed failed x\n",
                                              returncode=0)):
    out = g.check_failed_units()
assert len(out) == 1 and out[0].severity == "critical", out
assert "some-other.service" in out[0].detail and "1 failed unit(s)" in out[0].summary, out
print("   ok: own units excluded from CRITICAL; real failed units still escalate")
PYEOF

echo
echo "ALL T3.11 DEPLOYMENT ASSERTIONS PASSED — safe to: systemctl enable --now hermes-vps-{guardrail,escalation}.timer"
