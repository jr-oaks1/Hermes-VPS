#!/bin/bash
# Pre-Deployment Checklist for JR Hermes VPS S2
# Run locally before server deployment
# Date: 2026-08-22

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

echo "=========================================="
echo "JR Hermes VPS — Pre-Deployment Checklist"
echo "=========================================="
echo ""

# === Local Repo State ===
echo "1. LOCAL REPO STATE"
echo "---"

# Check branch
if [[ $(git rev-parse --abbrev-ref HEAD) == "main" ]]; then
    check_pass "Branch: main"
else
    check_warn "Branch: $(git rev-parse --abbrev-ref HEAD) (expected main)"
fi

# Check clean working tree
if [[ -z $(git status -s) ]]; then
    check_pass "Working tree: clean"
else
    check_fail "Working tree: has uncommitted changes"
    git status -s | sed 's/^/  /'
fi

# Check commit count
COMMIT_COUNT=$(git rev-list --count main)
if [[ $COMMIT_COUNT -ge 4 ]]; then
    check_pass "Commits pushed: $COMMIT_COUNT"
else
    check_warn "Commits: $COMMIT_COUNT (expected 4+)"
fi

# Check remote tracking
if git rev-parse @{u} >/dev/null 2>&1; then
    check_pass "Remote tracking: set up"
else
    check_fail "Remote tracking: not set"
fi

echo ""

# === GitHub Remote ===
echo "2. GITHUB REMOTE"
echo "---"

# Check remote URL
REMOTE_URL=$(git config --get remote.origin.url)
if [[ $REMOTE_URL == *"jr-oaks1/Hermes-VPS"* ]]; then
    check_pass "Remote URL: $REMOTE_URL"
else
    check_fail "Remote URL: $REMOTE_URL (unexpected)"
fi

# Check repo is public (attempt clone)
if git clone --depth 1 https://github.com/jr-oaks1/Hermes-VPS.git /tmp/hermes-vps-test >/dev/null 2>&1; then
    check_pass "GitHub repo: publicly accessible"
    rm -rf /tmp/hermes-vps-test
else
    check_fail "GitHub repo: not accessible from clone"
fi

# Check both local commits visible on GitHub
GITHUB_COMMITS=$(curl -s https://api.github.com/repos/jr-oaks1/Hermes-VPS/commits?per_page=10 | grep -o '"sha":"[^"]*"' | wc -l)
if [[ $GITHUB_COMMITS -ge 4 ]]; then
    check_pass "GitHub commits: $GITHUB_COMMITS visible"
else
    check_warn "GitHub commits: only $GITHUB_COMMITS visible (expected 4+)"
fi

echo ""

# === Files Present ===
echo "3. FILES & DIRECTORIES"
echo "---"

# Systemd units
if [[ -f deploy/hermes-vps-healthcheck-weekly.service ]]; then
    check_pass "Systemd: hermes-vps-healthcheck-weekly.service"
else
    check_fail "Systemd: hermes-vps-healthcheck-weekly.service missing"
fi

if [[ -f deploy/hermes-vps-healthcheck-weekly.timer ]]; then
    check_pass "Systemd: hermes-vps-healthcheck-weekly.timer"
else
    check_fail "Systemd: hermes-vps-healthcheck-weekly.timer missing"
fi

if [[ -f deploy/hermes-vps-audit-monthly.service ]]; then
    check_pass "Systemd: hermes-vps-audit-monthly.service"
else
    check_fail "Systemd: hermes-vps-audit-monthly.service missing"
fi

if [[ -f deploy/hermes-vps-audit-monthly.timer ]]; then
    check_pass "Systemd: hermes-vps-audit-monthly.timer"
else
    check_fail "Systemd: hermes-vps-audit-monthly.timer missing"
fi

# nginx config
if [[ -f deploy/nginx.conf ]]; then
    check_pass "nginx: config present (deploy/nginx.conf)"
else
    check_fail "nginx: config missing"
fi

# Prometheus
if [[ -f deploy/prometheus.service ]]; then
    check_pass "Prometheus: service file present"
else
    check_fail "Prometheus: service file missing"
fi

if [[ -f deploy/prometheus.yml ]]; then
    check_pass "Prometheus: config present"
else
    check_fail "Prometheus: config missing"
fi

if [[ -f deploy/prometheus_rules.yml ]]; then
    check_pass "Prometheus: alert rules present"
else
    check_fail "Prometheus: alert rules missing"
fi

# Health check script
if [[ -f scripts/audit/hermes_vps_health_check.py ]]; then
    check_pass "Health check: script present"
else
    check_fail "Health check: script missing"
fi

# Documentation
if [[ -f docs/CREDENTIAL_SETUP.md ]]; then
    check_pass "Docs: CREDENTIAL_SETUP.md present"
else
    check_fail "Docs: CREDENTIAL_SETUP.md missing"
fi

if [[ -f docs/CLOUD_REVIEW_SETUP.md ]]; then
    check_pass "Docs: CLOUD_REVIEW_SETUP.md present"
else
    check_fail "Docs: CLOUD_REVIEW_SETUP.md missing"
fi

if [[ -f docs/cloud-review-prompts/weekly-triage.md ]]; then
    check_pass "Docs: cloud-review prompts present"
else
    check_fail "Docs: cloud-review prompts missing"
fi

if [[ -f .env.template ]]; then
    check_pass ".env.template: present"
else
    check_fail ".env.template: missing"
fi

echo ""

# === Systemd Unit Validation ===
echo "4. SYSTEMD UNITS VALIDATION"
echo "---"

check_systemd_path() {
    local file=$1
    local path=$2
    if grep -q "^$path" "$file" 2>/dev/null || grep -q "$path" "$file" 2>/dev/null; then
        check_pass "$file: contains $path"
    else
        check_fail "$file: missing $path"
    fi
}

check_systemd_path "deploy/hermes-vps-healthcheck-weekly.service" "/opt/hermes-vps"
check_systemd_path "deploy/hermes-vps-audit-monthly.service" "/opt/hermes-vps"
check_systemd_path "deploy/hermes-vps-healthcheck-weekly.service" "EnvironmentFile=/root/.hermes_vps/.env"
check_systemd_path "deploy/prometheus.service" "/opt/hermes-vps/deploy/prometheus.yml"

echo ""

# === .gitignore Validation ===
echo "5. SECRETS PROTECTION"
echo "---"

if grep -q "\.env" .gitignore; then
    check_pass ".gitignore: blocks .env"
else
    check_fail ".gitignore: does not block .env"
fi

if grep -q "_secure" .gitignore; then
    check_pass ".gitignore: blocks _secure/"
else
    check_fail ".gitignore: does not block _secure/"
fi

if ! git ls-files | grep -q "\.env$"; then
    check_pass "Git: no .env files tracked"
else
    check_fail "Git: .env files tracked (remove with git rm --cached)"
fi

if [[ -f .env ]]; then
    check_warn ".env exists locally (not tracked; won't affect server)"
fi

# Verify .env.template has no secrets
if grep -qi "password.*=.*[a-zA-Z0-9]" .env.template; then
    check_fail ".env.template: may contain secrets (check manually)"
else
    check_pass ".env.template: contains only placeholders"
fi

echo ""

# === Cross-Project Dependencies ===
echo "6. CROSS-PROJECT DEPENDENCIES"
echo "---"

# Check hermes_v2 repo for S180 cleanup
if [[ -d ../hermes_v2 ]]; then
    cd ../hermes_v2
    if git log --oneline | head -1 | grep -q "S180\|S1\|cleanup"; then
        check_pass "hermes_v2: S180 cleanup visible"
    else
        check_warn "hermes_v2: S180 commit not visible (may not be pulled)"
    fi

    # Verify moved files are gone
    if [[ ! -f deploy/hermes-vps-healthcheck-weekly.service ]]; then
        check_pass "hermes_v2: VPS files removed"
    else
        check_warn "hermes_v2: VPS files still present (will be removed on server)"
    fi
    cd - >/dev/null
else
    check_warn "hermes_v2: repo not found locally (can't verify)"
fi

echo ""

# === Health Check Script Validation ===
echo "7. HEALTH CHECK SCRIPT"
echo "---"

if python3 -m py_compile scripts/audit/hermes_vps_health_check.py 2>/dev/null; then
    check_pass "Health check: Python syntax valid"
else
    check_fail "Health check: Python syntax error"
fi

if grep -q "export_hermes_vps_findings" scripts/audit/hermes_vps_health_check.py; then
    check_pass "Health check: export function present"
else
    check_fail "Health check: export function missing"
fi

if grep -q "export_hermes_v2_findings" scripts/audit/hermes_vps_health_check.py; then
    check_pass "Health check: dual export (hermes_v2 + vps)"
else
    check_warn "Health check: hermes_v2 export may not be present"
fi

echo ""

# === Summary ===
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""
echo -e "${GREEN}✓ PASS: $PASS_COUNT${NC}"
echo -e "${RED}✗ FAIL: $FAIL_COUNT${NC}"
echo -e "${YELLOW}⚠ WARN: $WARN_COUNT${NC}"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "${GREEN}✓ Pre-deployment checklist: READY${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Review any warnings (marked with ⚠)"
    echo "2. Verify CREDENTIAL_SETUP.md is complete"
    echo "3. Set up RemoteTrigger routines (see CLOUD_REVIEW_SETUP.md)"
    echo "4. Proceed to server deployment (Phase 4)"
    exit 0
else
    echo -e "${RED}✗ Pre-deployment checklist: BLOCKED${NC}"
    echo ""
    echo "Fix failures (marked with ✗) before proceeding."
    exit 1
fi
