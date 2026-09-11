#!/usr/bin/env python3
"""
scripts/audit/hermes_vps_guardrail.py — Tier 3 preventive guardrail (S17)

CONTINUOUS_IMPROVEMENT_STANDARD.md §Tier 3 (R7-R9) + Rule T3.10 (heartbeat) +
Rule T3.11 (deploy assertion — see scripts/deploy_guardrail.sh).

Read-only, idempotent, safe to run every 5 minutes. Runs on boot + every 5 min
(hermes-vps-guardrail.timer). Detects broken infrastructure BEFORE it cascades
into an outage, rather than waiting for the weekly health check.

Reuses the existing check functions from hermes_vps_health_check.py rather than
reimplementing them (single source of truth for SYSTEMD_SERVICES, replication
thresholds, TLS parsing).

DEBOUNCE: at 5-min cadence a transient blip becomes a page (Clevious S71: ~115
false "replication offline" findings). A check must fail N consecutive cycles
(2 default, 3 for replication/netdata) before its finding is emitted above INFO.
INFO findings are emitted only on STATE CHANGE, plus one hourly all-clear
roll-up — keeps the permanent findings_log from filling with identical rows
(retention is never the answer — CONTINUOUS_IMPROVEMENT_STANDARD.md T-LOG.3).

HEARTBEAT (T3.10): written atomically only on a fully successful run (every
check executed without an unexpected exception). Findings may be present — the
heartbeat means "the guardrail ran", not "the host is healthy". Staleness
detection is in hermes_vps_escalation_check.py, because a guardrail cannot
detect its own absence.

Env: HERMES_VPS_LOG_DB_URL, DATABASE_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
     HERMES_VPS_STATE_DIR (optional, staging override).

Exit codes (S19b): 0 = the audit ran to completion (findings or not), 2 = the
audit could not run (collect() raised). A CRITICAL finding is NOT a non-zero
exit — a oneshot that exits 1 becomes a `failed` unit, which check_failed_units()
then re-alarms on, which the Tier 4 escalation check then escalates: a
self-sustaining loop that ran 2026-09-08 → 2026-09-10 and produced ~39k
findings_log rows. "The audit found something" and "the audit could not run"
are different states and only the second is a unit failure.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(_SCRIPT_DIR)))  # repo root
sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))                   # repo/scripts
sys.path.insert(0, _SCRIPT_DIR)

from log_finding import Finding, log_findings, state_dir  # noqa: E402
from emission_state import load_state, save_state, throttle  # noqa: E402
import psycopg  # noqa: E402
import requests  # noqa: E402

from hermes_vps_health_check import (  # noqa: E402
    check_systemd_services, check_replication, check_tls_expiry,
)

_TIMERS = (
    "hermes-vps-healthcheck-weekly.timer",
    "hermes-vps-audit-monthly.timer",
    "hermes-vps-daily-digest.timer",
    "hermes-vps-guardrail.timer",
    "hermes-vps-escalation.timer",
)
_NETDATA_URL = "http://127.0.0.1:19999/api/v1/info"
_ROOT_DOC = os.environ.get("HERMES_VPS_ROOT_DOC", "/opt/hermes-vps/public/index.html")
_FINDINGS_TABLE_WARN_MB = 500          # convert to hypertable-with-justification at this point

_DISK_WARN_PCT, _DISK_CRIT_PCT = 80.0, 90.0
_MEM_WARN_PCT, _MEM_CRIT_PCT = 15.0, 8.0   # available %, lower is worse

# consecutive-failure thresholds before a check emits above INFO
_DEBOUNCE = {"replication": 3, "netdata": 3}
_DEBOUNCE_DEFAULT = 2
_ALLCLEAR_EVERY_SEC = 3600


# --------------------------------------------------------------------------- #
# New cheap checks
# --------------------------------------------------------------------------- #

def check_own_timers() -> list[Finding]:
    out = []
    for t in _TIMERS:
        try:
            r = subprocess.run(["systemctl", "is-active", t],
                               capture_output=True, text=True, timeout=10)
            state = r.stdout.strip()
            if state == "active":
                out.append(Finding("finding", "info", f"timer.{t}: active"))
            elif state == "inactive" and _unit_exists(t):
                out.append(Finding("finding", "warning", f"timer.{t}: {state}"))
            elif not _unit_exists(t):
                out.append(Finding("finding", "info", f"timer.{t}: not installed yet"))
            else:
                out.append(Finding("finding", "warning", f"timer.{t}: {state or 'unknown'}"))
        except Exception as e:  # noqa: BLE001
            out.append(Finding("error", "warning", f"timer.{t}: check failed", str(e)))
    return out


def _unit_exists(unit: str) -> bool:
    r = subprocess.run(["systemctl", "list-unit-files", unit],
                       capture_output=True, text=True, timeout=10)
    return unit in r.stdout


# S19b: this guardrail's own two units MUST NOT be counted here. If a bug puts
# hermes-vps-guardrail.service or hermes-vps-escalation.service into `failed`,
# counting that as a CRITICAL makes the guardrail alarm on its own failure —
# and the Tier 4 escalation check then escalates that CRITICAL, which keeps both
# units `failed`, which is the exact condition each alarms on. Neither can ever
# return to green. Their liveness is covered instead by the T3.10 guardrail
# heartbeat-staleness check in hermes_vps_escalation_check.py, which is the
# correct "a guardrail cannot detect its own absence" backstop.
_OWN_UNITS = ("hermes-vps-guardrail.service", "hermes-vps-escalation.service")


def check_failed_units() -> list[Finding]:
    try:
        r = subprocess.run(["systemctl", "list-units", "--state=failed", "--no-legend", "--plain"],
                           capture_output=True, text=True, timeout=10)
        failed = [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()]
        own = [u for u in failed if u in _OWN_UNITS]
        other = [u for u in failed if u not in _OWN_UNITS]
        own_note = (f" | own units excluded: {', '.join(own)} — liveness covered by the T3.10 "
                    f"guardrail-heartbeat staleness check" if own else "")
        if other:
            return [Finding("alert", "critical", f"systemd: {len(other)} failed unit(s)",
                            detail=", ".join(other) + own_note)]
        return [Finding("finding", "info", "systemd: no failed units",
                        detail=own_note.lstrip(" |") if own_note else "")]
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "warning", "systemd: --failed check failed", str(e))]


def check_postgres_writable() -> list[Finding]:
    """Reachability != writability (S67). CREATE TEMP TABLE / INSERT / rollback."""
    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    if not db_url:
        return [Finding("error", "warning", "pg.writable: HERMES_VPS_LOG_DB_URL not set")]
    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE TEMP TABLE _gr_probe (x int) ON COMMIT DROP")
                cur.execute("INSERT INTO _gr_probe VALUES (1)")
                cur.execute("SELECT count(*) FROM _gr_probe")
                cur.fetchone()
            conn.rollback()
        return [Finding("finding", "info", "pg.writable: ok")]
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "critical", "pg.writable: write probe failed", str(e))]


def check_disk_mem() -> list[Finding]:
    out = []
    try:
        du = shutil.disk_usage("/")
        pct = du.used / du.total * 100
        free_gb = du.free / 1e9
        if pct >= _DISK_CRIT_PCT:
            out.append(Finding("alert", "critical", f"disk./: {pct:.0f}% used ({free_gb:.1f} GB free)"))
        elif pct >= _DISK_WARN_PCT:
            out.append(Finding("finding", "warning", f"disk./: {pct:.0f}% used ({free_gb:.1f} GB free)"))
        else:
            out.append(Finding("finding", "info", f"disk./: {pct:.0f}% used ({free_gb:.1f} GB free)"))
    except Exception as e:  # noqa: BLE001
        out.append(Finding("error", "warning", "disk./: check failed", str(e)))

    try:
        meminfo = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                meminfo[k.strip()] = int(v.strip().split()[0])  # kB
        total = meminfo["MemTotal"]
        avail = meminfo.get("MemAvailable", meminfo["MemFree"])
        avail_pct = avail / total * 100
        if avail_pct <= _MEM_CRIT_PCT:
            out.append(Finding("alert", "critical", f"mem: {avail_pct:.0f}% available"))
        elif avail_pct <= _MEM_WARN_PCT:
            out.append(Finding("finding", "warning", f"mem: {avail_pct:.0f}% available"))
        else:
            out.append(Finding("finding", "info", f"mem: {avail_pct:.0f}% available"))
    except Exception as e:  # noqa: BLE001
        out.append(Finding("error", "warning", "mem: check failed", str(e)))
    return out


def check_netdata() -> list[Finding]:
    try:
        r = requests.get(_NETDATA_URL, timeout=5)
        if r.ok:
            return [Finding("finding", "info", "netdata: reachable (127.0.0.1:19999)")]
        return [Finding("finding", "warning", f"netdata: HTTP {r.status_code}")]
    except Exception as e:  # noqa: BLE001
        return [Finding("finding", "warning", "netdata: unreachable", str(e))]


def check_nginx_root_path() -> list[Finding]:
    """The served landing page. Emits WARNING the day the file vanishes — e.g.
    if the /opt/hermes_v2 teardown removes a path nginx still points at."""
    if os.path.isfile(_ROOT_DOC):
        return [Finding("finding", "info", f"nginx.root: {_ROOT_DOC} present")]
    return [Finding("alert", "critical", f"nginx.root: served document missing: {_ROOT_DOC}",
                    detail="nginx `location = /` will 404 the public root of artek-studio.com")]


_SSH_AUTH_WINDOW_MIN = 6      # guardrail cadence is 5 min; overlap slightly
_SSH_AUTH_WARN, _SSH_AUTH_CRIT = 20, 100


def check_ssh_auth_anomalies() -> list[Finding]:
    """H6 (JR Hermes VPS S23): counts SSH auth-failure signals from the last
    _SSH_AUTH_WINDOW_MIN minutes on ssh.service, including the failed-*key*-auth
    class fail2ban cannot see on this key-only host (VPS_CONNECTIVITY_REFERENCE.md
    §13.3: 'Connection closed by authenticating user ... [preauth]' does not match
    fail2ban's filter) — this check is the only thing counting that class.

    Not an intrusion-detection signal: key auth cannot be brute-forced, so a high
    count here is noise/scan volume, not a compromise path (§13.3 again). Thresholds
    are calibrated for DoS/scan visibility, not attack detection — hence generous
    values and INFO (not WARNING) for any nonzero-but-low count.
    """
    try:
        r = subprocess.run(
            ["journalctl", "-u", "ssh.service", "--since", f"-{_SSH_AUTH_WINDOW_MIN} min", "-o", "cat"],
            capture_output=True, text=True, timeout=15,
        )
        lines = r.stdout.splitlines()
        invalid_or_failed = sum(1 for ln in lines if "Invalid user" in ln or "Failed password" in ln)
        preauth_key_fail = sum(
            1 for ln in lines
            if "Connection closed by authenticating user" in ln and "[preauth]" in ln
        )
        total = invalid_or_failed + preauth_key_fail

        banned = None
        try:
            fb = subprocess.run(["fail2ban-client", "status", "sshd"],
                                capture_output=True, text=True, timeout=10)
            for ln in fb.stdout.splitlines():
                if "Currently banned" in ln:
                    banned = ln.split(":")[-1].strip()
        except Exception:  # noqa: BLE001
            pass

        detail = f"invalid-user/failed-password={invalid_or_failed}, preauth-key-fail={preauth_key_fail}"
        if banned is not None:
            detail += f", fail2ban-currently-banned={banned}"

        summary = f"ssh.auth: {total} auth-anomaly event(s) in {_SSH_AUTH_WINDOW_MIN}min"
        if total >= _SSH_AUTH_CRIT:
            return [Finding("alert", "critical", summary, detail)]
        if total >= _SSH_AUTH_WARN:
            return [Finding("finding", "warning", summary, detail)]
        return [Finding("finding", "info", summary, detail)]
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "warning", "ssh.auth: check failed", str(e))]


def check_findings_table_size() -> list[Finding]:
    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    if not db_url:
        return []
    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_total_relation_size('findings_log') / 1048576.0")
                mb = cur.fetchone()[0]
        if mb >= _FINDINGS_TABLE_WARN_MB:
            return [Finding("finding", "warning",
                            f"findings_log: {mb:.0f} MB — time to justify hypertable compression tuning",
                            detail="never a retention/DELETE decision (T-LOG.3); revisit chunk size + compression")]
        return [Finding("finding", "info", f"findings_log: {mb:.1f} MB")]
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "warning", "findings_log: size check failed", str(e))]


# --------------------------------------------------------------------------- #
# Debounce + state
# --------------------------------------------------------------------------- #
# The debounce/state-change/roll-up mechanism now lives in scripts/emission_state.py
# (S18) so the Tier 4 escalation check shares one implementation. This thin shim
# keeps the guardrail's tuning (_DEBOUNCE / _DEBOUNCE_DEFAULT) local and the
# public name stable — tests/test_guardrail_debounce.py imports apply_debounce.

_STATE_FILE = "guardrail_state.json"


def apply_debounce(raw: list[Finding], state: dict, now_ts: float) -> tuple[list[Finding], dict]:
    return throttle(
        raw, state, now_ts,
        debounce=_DEBOUNCE,
        debounce_default=_DEBOUNCE_DEFAULT,
        allclear_every_sec=_ALLCLEAR_EVERY_SEC,
        allclear_summary=lambda n: f"guardrail: all {n} checks OK",
    )


def write_heartbeat(worst: str, n_checks: int) -> None:
    path = os.path.join(state_dir(), "guardrail.heartbeat")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "checks_run": n_checks,
        "worst_severity": worst,
        "pid": os.getpid(),
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def collect() -> list[Finding]:
    database_url = os.environ.get("DATABASE_URL", "")
    raw: list[Finding] = []
    raw += check_systemd_services()
    raw += check_own_timers()
    raw += check_failed_units()
    raw += check_postgres_writable()
    if database_url:
        raw += check_replication(database_url)
    raw += check_disk_mem()
    raw += check_netdata()
    raw += check_tls_expiry()
    raw += check_nginx_root_path()
    raw += check_findings_table_size()
    raw += check_ssh_auth_anomalies()
    return raw


def run(dry_run: bool = False) -> int:
    now_ts = datetime.now(timezone.utc).timestamp()
    try:
        raw = collect()
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            log_findings([Finding("error", "critical", "guardrail: collect() raised", detail=str(e))],
                         session_ref=f"vps-guardrail-{datetime.now(timezone.utc):%Y%m%d}")
        print(f"guardrail: collect failed: {e}", file=sys.stderr)
        return 2

    state = load_state(_STATE_FILE)
    emitted, new_state = apply_debounce(raw, state, now_ts)
    worst = max((f.severity for f in raw),
                key=lambda s: ("info", "warning", "critical").index(s))

    if dry_run:
        print("--- DRY RUN — no writes (DB, Telegram, state, heartbeat) ---")
        for f in raw:
            print(f"  [{f.severity.upper():8}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))
        print(f"\nworst severity: {worst}; would emit {len(emitted)} finding(s)")
        return 0

    log_findings(emitted, session_ref=f"vps-guardrail-{datetime.now(timezone.utc):%Y%m%d}",
                 header="🛡️ Tier 3 guardrail")
    save_state(_STATE_FILE, new_state)
    write_heartbeat(worst, len(raw))    # only reached if nothing above raised

    for f in emitted:
        print(f"[{f.severity.upper()}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))
    # S19b: exit 0 whenever the audit completed. A CRITICAL finding is dual-written
    # + heartbeat-recorded above; it does not make this oneshot a `failed` unit.
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tier 3 read-only preventive guardrail")
    ap.add_argument("--dry-run", action="store_true",
                    help="run every check, write nothing (DB/Telegram/state/heartbeat)")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run))
