#!/usr/bin/env bash
# Pre-deployment checklist for JR Hermes VPS.
# Run locally (Git Bash) before pushing / deploying to the Hetzner host.
# Rewritten S17: dropped the stale hermes_v2 / _secure / dual-export checks;
# added the S17 tier scripts + units, systemd-analyze verify, and the T-LOG.2
# routing assertion.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
PASS=0; FAIL=0; WARN=0
ok()   { echo -e "${GREEN}\xe2\x9c\x93${NC} $1"; PASS=$((PASS+1)); }
bad()  { echo -e "${RED}\xe2\x9c\x97${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "${YELLOW}\xe2\x9a\xa0${NC} $1"; WARN=$((WARN+1)); }

echo "=========================================="
echo "JR Hermes VPS — pre-deployment checklist"
echo "=========================================="

echo; echo "1. REPO STATE"; echo "---"
BR=$(git rev-parse --abbrev-ref HEAD)
[[ "$BR" == "main" ]] && ok "branch: main" || warn "branch: $BR (expected main)"
[[ -z "$(git status -s)" ]] && ok "working tree clean" || { bad "uncommitted changes"; git status -s | sed 's/^/  /'; }
git rev-parse '@{u}' >/dev/null 2>&1 && ok "upstream tracking set" || bad "no upstream tracking"
DEFAULT_BR=$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')
[[ "$DEFAULT_BR" == "main" ]] && ok "origin default branch: main" || warn "origin default branch: ${DEFAULT_BR:-unknown} (S17 wants main)"

echo; echo "2. PYTHON"; echo "---"
PYFILES=(
  scripts/log_finding.py
  scripts/audit/hermes_vps_health_check.py
  scripts/audit/hermes_vps_guardrail.py
  scripts/audit/hermes_vps_escalation_check.py
  scripts/audit/hermes_vps_reconcile.py
  scripts/audit/hermes_vps_daily_digest.py
)
for f in "${PYFILES[@]}"; do
  if [[ -f "$f" ]] && python -m py_compile "$f" 2>/dev/null; then ok "compiles: $f"; else bad "compile FAILED / missing: $f"; fi
done
if python -m pytest tests/ -q >/dev/null 2>&1; then ok "pytest tests/ green"; else warn "pytest not run or failing (pip install -r requirements-dev.txt)"; fi

echo; echo "3. T-LOG.2 ROUTING"; echo "---"
grep -q "from log_finding import" scripts/audit/hermes_vps_health_check.py \
  && ok "health check routes through log_finding" || bad "health check does NOT import log_finding"
grep -q "from log_finding import" scripts/audit/hermes_vps_daily_digest.py \
  && ok "daily digest routes through log_finding" || bad "daily digest does NOT import log_finding"
! grep -qE "^\s*import psycopg2|cursor_factory" scripts/audit/hermes_vps_daily_digest.py \
  && ok "daily digest is psycopg3" || bad "daily digest still imports psycopg2"
! grep -q "def insert_findings" scripts/audit/hermes_vps_health_check.py \
  && ok "health check's private insert_findings removed" || warn "health check still defines insert_findings"

echo; echo "4. UNIT FILES"; echo "---"
UNITS=(
  hermes-vps-healthcheck-weekly hermes-vps-audit-monthly hermes-vps-daily-digest
  hermes-vps-guardrail hermes-vps-escalation
)
for u in "${UNITS[@]}"; do
  [[ -f "deploy/$u.service" ]] && ok "deploy/$u.service" || bad "deploy/$u.service missing"
  [[ -f "deploy/$u.timer"   ]] && ok "deploy/$u.timer"   || bad "deploy/$u.timer missing"
done
for u in "${UNITS[@]}"; do
  grep -q "StartLimitIntervalSec=" "deploy/$u.service" \
    && ok "$u.service: T0.2 start limit set" || bad "$u.service: no StartLimitIntervalSec (T0.2)"
done
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify deploy/hermes-vps-*.service deploy/hermes-vps-*.timer 2>&1 \
    && ok "systemd-analyze verify clean" || bad "systemd-analyze verify found problems"
else
  warn "systemd-analyze not available locally — run on host"
fi

echo; echo "5. MIGRATION + DOCS"; echo "---"
[[ -f deploy/sql/S17_findings_log_tier4.sql ]] && ok "migration SQL present" || bad "deploy/sql/S17_findings_log_tier4.sql missing"
grep -qi "retention" deploy/sql/S17_findings_log_tier4.sql \
  && grep -q "NO retention" deploy/sql/S17_findings_log_tier4.sql \
  && ok "migration: no add_retention_policy (T-LOG.3)" || warn "migration: confirm no retention policy"
[[ -f public/index.html ]] && ok "public/index.html present (nginx root)" || bad "public/index.html missing"
! grep -q "root /opt/hermes_v2/public" deploy/nginx.conf \
  && ok "nginx root no longer points at /opt/hermes_v2" || bad "nginx still roots at /opt/hermes_v2/public"
[[ -f .env.template ]] && grep -q "FINDINGS_DB_URL" .env.template \
  && ok ".env.template lists FINDINGS_DB_URL" || bad ".env.template missing FINDINGS_DB_URL"

echo; echo "6. SECRETS"; echo "---"
grep -q '\.env' .gitignore && ok ".gitignore blocks .env" || bad ".gitignore does not block .env"
git ls-files | grep -q '\.env$' && bad "a .env file is tracked (git rm --cached)" || ok "no .env tracked"
if grep -Eqi '(password|token|secret)\s*=\s*[A-Za-z0-9]{8,}' .env.template; then
  bad ".env.template may contain a real secret"
else
  ok ".env.template placeholders only"
fi

echo; echo "=========================================="
echo -e "${GREEN}PASS: $PASS${NC}   ${RED}FAIL: $FAIL${NC}   ${YELLOW}WARN: $WARN${NC}"
echo "=========================================="
[[ $FAIL -eq 0 ]] && { echo -e "${GREEN}READY${NC}"; exit 0; } || { echo -e "${RED}BLOCKED — fix FAILs${NC}"; exit 1; }
