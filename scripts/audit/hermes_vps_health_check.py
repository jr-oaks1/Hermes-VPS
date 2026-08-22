#!/usr/bin/env python3
"""
scripts/audit/hermes_vps_health_check.py — Hermes VPS's own recurring health check
(built S179 inside hermes_v2; moved to its own JR Hermes VPS project S1)

Two cadences, one script:
  --mode quick   weekly — services up, /health agent statuses, replication lag,
                 ohlcv_1m ingestion freshness. Fast, no filesystem/network extras.
  --mode deep    monthly — everything quick does, plus backup currency, TLS cert
                 expiry, and local-vs-origin git sync. Mirrors the S178 diagnostic
                 scope so the monthly run is a repeatable version of that audit.

Every check writes one row to hermes_vps_log.findings_log (category='finding',
severity info/warning/critical) regardless of outcome — S178's own diagnostic
logged passing checks too, and the user asked for "everything reported", not an
alert-only-on-failure feed. A single summary message is then sent to the Hermes
VPS Telegram bot every run (not suppressed on all-clear) — deliberately simpler
than scripts/audit/run_bronze_audit_alert.sh's known-issue-suppression pattern,
since that pattern exists to fight page fatigue on a much noisier daily job; a
weekly/monthly cadence doesn't need it.

Runs ON the Hetzner host itself (systemd, not SSH) — checks hit localhost/local
sockets directly.

Usage:
    python scripts/audit/hermes_vps_health_check.py --mode quick
    python scripts/audit/hermes_vps_health_check.py --mode deep

Requires (from environment — EnvironmentFile= in the systemd unit; the unit reads
TWO env files, /root/.hermes_vps/.env (primary) then /opt/hermes_v2/.env
(secondary, for HERMES_LOG_DB_URL only) so this project doesn't duplicate a
credential it doesn't otherwise need):
    DATABASE_URL            (hermes_v2 — replication + ingestion freshness reads)
    HERMES_VPS_LOG_DB_URL   (hermes_vps_log — findings_log writes)
    HERMES_LOG_DB_URL       (hermes_v2_log — cross-project findings export only)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (Hermes VPS's own bot)

Exit codes: 0 = no critical finding, 1 = at least one critical finding, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INGESTION_STALE_WARN_MIN = 15
TLS_EXPIRY_WARN_DAYS = 21
TLS_CERT_PATH = "/etc/letsencrypt/live/artek-studio.com/fullchain.pem"
PG_BACKUP_CONF = "/etc/pg_backup.conf"
SYSTEMD_SERVICES = ("hermes_v2", "nginx", "postgresql")


@dataclass
class Finding:
    category: str   # finding | error | note | alert
    severity: str    # info | warning | critical
    summary: str
    detail: str = ""


def check_systemd_services() -> list[Finding]:
    findings = []
    for svc in SYSTEMD_SERVICES:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", svc], capture_output=True, text=True, timeout=10
            )
            state = result.stdout.strip()
            if state == "active":
                findings.append(Finding("finding", "info", f"service.{svc}: active"))
            else:
                findings.append(Finding("finding", "critical", f"service.{svc}: {state or 'unknown'}"))
        except Exception as e:
            findings.append(Finding("error", "critical", f"service.{svc}: check failed", str(e)))
    return findings


def check_api_health() -> list[Finding]:
    findings = []
    try:
        resp = requests.get("https://localhost/health", verify=False, timeout=15)
        body = resp.json()
        status = body.get("status", "unknown")
        agents = body.get("agents", {})
        bad_agents = {
            aid: s for aid, s in agents.items() if s not in ("healthy", "idle", "role_excluded")
        }
        if status == "ok" and not bad_agents:
            findings.append(Finding("finding", "info", f"api.health: ok ({len(agents)} agents)"))
        else:
            # "starting" is normal for the first few minutes after any restart
            # (several agents run a multi-minute backfill on every restart, per
            # hermes_v2.service's own ExecStartPost comment) -- only escalate to
            # critical when an agent reports something other than that expected
            # transient, so a health check landing shortly after a restart
            # doesn't false-alarm.
            only_starting = bad_agents and all(s == "starting" for s in bad_agents.values())
            severity = "warning" if (not bad_agents or only_starting) else "critical"
            findings.append(Finding(
                "finding", severity, f"api.health: {status}",
                detail=f"unhealthy agents: {bad_agents}" if bad_agents else "",
            ))
    except Exception as e:
        findings.append(Finding("error", "critical", "api.health: unreachable", str(e)))
    return findings


def check_replication(database_url: str) -> list[Finding]:
    findings = []
    try:
        with psycopg.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT standbys, max_lag_bytes FROM hermes_replication_status()")
                standbys, max_lag_bytes = cur.fetchone()
        if not standbys:
            findings.append(Finding("finding", "warning", "replication: no standby reporting"))
        elif max_lag_bytes and max_lag_bytes > 50_000_000:  # 50MB
            findings.append(Finding(
                "finding", "warning", f"replication: {standbys} standby(s), {max_lag_bytes} bytes max lag"
            ))
        else:
            findings.append(Finding(
                "finding", "info", f"replication: {standbys} standby(s), {max_lag_bytes} bytes max lag"
            ))
    except Exception as e:
        findings.append(Finding("error", "critical", "replication: check failed", str(e)))
    return findings


def check_ingestion_freshness(database_url: str) -> list[Finding]:
    findings = []
    try:
        with psycopg.connect(database_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT symbol, MAX(time) FROM ohlcv_1m "
                    "WHERE time > NOW() - INTERVAL '2 hours' GROUP BY symbol"
                )
                rows = cur.fetchall()
        if not rows:
            findings.append(Finding("finding", "critical", "ingestion.ohlcv_1m: no rows in last 2h for any symbol"))
            return findings
        now = datetime.now(timezone.utc)
        stale = []
        for symbol, latest in rows:
            age_min = (now - latest.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age_min > INGESTION_STALE_WARN_MIN:
                stale.append(f"{symbol}={age_min:.0f}m")
        if stale:
            findings.append(Finding(
                "finding", "warning",
                f"ingestion.ohlcv_1m: {len(stale)}/{len(rows)} symbols stale",
                detail=", ".join(stale),
            ))
        else:
            findings.append(Finding("finding", "info", f"ingestion.ohlcv_1m: {len(rows)} symbols current"))
    except Exception as e:
        findings.append(Finding("error", "critical", "ingestion.ohlcv_1m: check failed", str(e)))
    return findings


def _parse_pg_backup_conf(path: str) -> dict:
    """Minimal KEY="value" / KEY=value parser — matches pg_backup.conf's own shell-sourced format."""
    conf = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            conf[key.strip()] = val.strip().strip('"')
    return conf


def check_backup_currency() -> list[Finding]:
    """One row per registered database — mirrors DATABASES/BACKUP_ROOT/STALE_HOURS
    from /etc/pg_backup.conf rather than a hardcoded path, so this check tracks
    whatever's actually registered (S178 added hermes_vps_log there mid-session;
    a hardcoded list would have missed it)."""
    findings = []
    try:
        conf = _parse_pg_backup_conf(PG_BACKUP_CONF)
        databases = conf.get("DATABASES", "").split()
        backup_root = conf.get("BACKUP_ROOT", "/opt/backups")
        stale_hours = float(conf.get("STALE_HOURS", "26"))
    except Exception as e:
        findings.append(Finding("error", "warning", f"backups: cannot read {PG_BACKUP_CONF}", str(e)))
        return findings

    now = datetime.now(timezone.utc).timestamp()
    for db in databases:
        db_dir = os.path.join(backup_root, db)
        try:
            dumps = [f for f in os.listdir(db_dir) if f.startswith(f"{db}_") and f.endswith(".dump")] \
                if os.path.isdir(db_dir) else []
        except Exception as e:
            findings.append(Finding("error", "warning", f"backups.{db}: check failed", str(e)))
            continue
        if not dumps:
            findings.append(Finding("finding", "warning", f"backups.{db}: no dump found yet in {db_dir}"))
            continue
        newest_mtime = max(os.path.getmtime(os.path.join(db_dir, f)) for f in dumps)
        age_hours = (now - newest_mtime) / 3600
        if age_hours > stale_hours:
            findings.append(Finding(
                "finding", "warning", f"backups.{db}: newest is {age_hours:.1f}h old",
                f"threshold {stale_hours}h",
            ))
        else:
            findings.append(Finding("finding", "info", f"backups.{db}: newest is {age_hours:.1f}h old"))
    return findings


def check_tls_expiry() -> list[Finding]:
    findings = []
    try:
        result = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", TLS_CERT_PATH],
            capture_output=True, text=True, timeout=10,
        )
        # output: "notAfter=Oct 19 00:00:00 2026 GMT"
        end_str = result.stdout.strip().split("=", 1)[1]
        end_dt = datetime.strptime(end_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (end_dt - datetime.now(timezone.utc)).days
        if days_left < TLS_EXPIRY_WARN_DAYS:
            findings.append(Finding("finding", "warning", f"tls: expires in {days_left}d"))
        else:
            findings.append(Finding("finding", "info", f"tls: expires in {days_left}d"))
    except Exception as e:
        findings.append(Finding("error", "warning", "tls: check failed", str(e)))
    return findings


def check_git_sync(repo_dir: str) -> list[Finding]:
    """Checks one repo's local-vs-origin sync. Called once per tracked repo (S1,
    JR Hermes VPS split) -- hermes_v2/Ingestor's own deploy dir, plus this
    project's own /opt/hermes-vps -- so a stale deploy on either side surfaces."""
    findings = []
    label = os.path.basename(repo_dir.rstrip("/"))
    try:
        subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main", "--quiet"], timeout=30, check=True)
        local = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        remote = subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "origin/main"], capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", repo_dir, "status", "--short"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if local != remote:
            findings.append(Finding("finding", "warning", f"git.{label}: local HEAD {local[:7]} != origin/main {remote[:7]}"))
        elif status:
            findings.append(Finding("finding", "info", f"git.{label}: in sync with origin, uncommitted local changes present", status))
        else:
            findings.append(Finding("finding", "info", f"git.{label}: in sync with origin/main ({local[:7]})"))
    except Exception as e:
        findings.append(Finding("error", "warning", f"git.{label}: check failed", str(e)))
    return findings


def insert_findings(db_url: str, session_ref: str, findings: list[Finding]) -> None:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for f in findings:
                cur.execute(
                    """
                    INSERT INTO findings_log (session_ref, category, severity, summary, detail, source)
                    VALUES (%s, %s, %s, %s, %s, 'hermes-vps')
                    """,
                    (session_ref, f.category, f.severity, f.summary, f.detail or None),
                )
        conn.commit()


def _fetch_findings_window(db_url: str, window_days: int) -> list | dict:
    if not db_url:
        return {"error": "no connection string configured"}
    try:
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, ts, session_ref, category, severity, summary, detail, source
                    FROM findings_log
                    WHERE ts > NOW() - (%s || ' days')::interval
                    ORDER BY ts DESC
                    """,
                    (window_days,),
                )
                rows = cur.fetchall()
                cols = [d.name for d in cur.description]
        return [
            {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, row)}
            for row in rows
        ]
    except Exception as e:
        return {"error": str(e)}


def _commit_and_push_export(repo_dir: str, export_path: str, mode: str, label: str) -> None:
    try:
        rel_path = os.path.relpath(export_path, repo_dir)
        subprocess.run(["git", "-C", repo_dir, "add", rel_path], check=True)
        diff = subprocess.run(["git", "-C", repo_dir, "diff", "--cached", "--quiet"], cwd=repo_dir)
        if diff.returncode == 0:
            print(f"findings export ({label}): no changes, skipping commit")
            return
        subprocess.run(
            ["git", "-C", repo_dir, "commit", "-m",
             f"chore: findings export ({mode}, {datetime.now(timezone.utc):%Y-%m-%d})"],
            check=True,
        )
        subprocess.run(["git", "-C", repo_dir, "push", "origin", "main"], check=True)
        print(f"findings export ({label}): committed and pushed")
    except Exception as e:
        print(f"findings export ({label}): git commit/push failed: {e}", file=sys.stderr)


def export_hermes_v2_findings(mode: str, hermes_log_db_url: str, repo_dir: str = "/opt/hermes_v2") -> None:
    """Dump hermes_v2_log findings_log rows to the hermes_v2/Ingestor repo (S179;
    split S1 -- this export stayed pointed at hermes_v2 unchanged so the existing
    weekly/monthly RemoteTrigger cloud-review routines there keep working as-is).

    Cloud-scheduled review agents can't reach this host directly (Tailscale-only,
    no SSH from Anthropic's cloud sandbox) -- this is the bridge: export what the
    agent needs into the repo it already has read/write access to, then commit
    and push from here, where the credentials and DB access actually exist."""
    window_days = 8 if mode == "quick" else 35
    export = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "window_days": window_days,
        "hermes_v2_log": _fetch_findings_window(hermes_log_db_url, window_days),
    }
    export_dir = os.path.join(repo_dir, "docs", "findings_export")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, "latest.json")
    with open(export_path, "w") as f:
        json.dump(export, f, indent=2, default=str)
    _commit_and_push_export(repo_dir, export_path, mode, "hermes_v2_log")


def export_hermes_vps_findings(mode: str, vps_log_db_url: str, repo_dir: str = "/opt/hermes-vps") -> None:
    """Dump hermes_vps_log findings_log rows to this project's own repo (S1, JR
    Hermes VPS split) -- mirrors export_hermes_v2_findings but targets this
    project's own repo/cloud-review routine instead of hermes_v2's, so host-level
    findings get reviewed by a VPS-scoped agent rather than piggybacking on
    hermes_v2's git history."""
    window_days = 8 if mode == "quick" else 35
    export = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "window_days": window_days,
        "hermes_vps_log": _fetch_findings_window(vps_log_db_url, window_days),
    }
    export_dir = os.path.join(repo_dir, "docs", "findings_export")
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(export_dir, "latest.json")
    with open(export_path, "w") as f:
        json.dump(export, f, indent=2, default=str)
    _commit_and_push_export(repo_dir, export_path, mode, "hermes_vps_log")


def send_telegram_summary(bot_token: str, chat_id: str, mode: str, findings: list[Finding]) -> bool:
    n_crit = sum(1 for f in findings if f.severity == "critical")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    label = "Monthly forensic audit" if mode == "deep" else "Weekly health check"
    if n_crit:
        head = f"🔴 {label} — {n_crit} CRITICAL, {n_warn} warning"
    elif n_warn:
        head = f"🟡 {label} — {n_warn} warning(s), rest OK"
    else:
        head = f"✅ {label} — all {len(findings)} checks OK"
    lines = [head]
    for f in findings:
        if f.severity != "info":
            marker = "🔴" if f.severity == "critical" else "🟡"
            lines.append(f"{marker} {f.summary}")
    text = "\n".join(lines)
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        return resp.ok
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes VPS recurring health check / forensic audit")
    parser.add_argument("--mode", choices=("quick", "deep"), required=True)
    parser.add_argument("--session-ref", default=None)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "")
    vps_log_db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not database_url or not vps_log_db_url:
        print("DATABASE_URL / HERMES_VPS_LOG_DB_URL not set", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    findings += check_systemd_services()
    findings += check_api_health()
    findings += check_replication(database_url)
    findings += check_ingestion_freshness(database_url)

    if args.mode == "deep":
        findings += check_backup_currency()
        findings += check_tls_expiry()
        findings += check_git_sync("/opt/hermes_v2")
        findings += check_git_sync("/opt/hermes-vps")

    session_ref = args.session_ref or f"vps-healthcheck-{args.mode}-{datetime.now(timezone.utc):%Y%m%d}"
    insert_findings(vps_log_db_url, session_ref, findings)

    # Dual-write to unified findings DB (S6)
    # Skip if FINDINGS_DB_URL not set (backward compatible with older deployments)
    findings_db_url = os.environ.get("FINDINGS_DB_URL", "")
    if findings_db_url:
        import subprocess
        for f in findings:
            # Map severity for routing table compliance
            # Only send CRITICAL/WARNING to Telegram (from log_operational_finding.py)
            try:
                cmd = [
                    "/opt/hermes-vps/.venv/bin/python3", "/opt/jrvps-orchestrator/scripts/log_operational_finding.py",
                    "--source_project", "JR Hermes VPS",
                    "--severity", f.severity,
                    "--category", f.category,
                    "--summary", f.summary,
                ]
                if f.detail:
                    cmd.extend(["--detail", f.detail])
                if session_ref:
                    cmd.extend(["--session", session_ref])

                # Skip Telegram if INFO (only CRITICAL/WARNING alert)
                if f.severity == "info":
                    cmd.append("--no-telegram")

                subprocess.run(cmd, check=False, timeout=30)
            except Exception as e:
                print(f"warning: dual-write to unified DB failed for finding '{f.summary}': {e}", file=sys.stderr)
    else:
        if findings:  # Only log if there are findings to write
            print("warning: FINDINGS_DB_URL not set — unified DB logging skipped", file=sys.stderr)

    for f in findings:
        print(f"[{f.severity.upper()}] {f.category}.{f.summary}" + (f" — {f.detail}" if f.detail else ""))

    if bot_token and chat_id:
        sent = send_telegram_summary(bot_token, chat_id, args.mode, findings)
        print(f"telegram_sent={sent}")
    else:
        print("telegram skipped: TELEGRAM_BOT_TOKEN/CHAT_ID not set", file=sys.stderr)

    hermes_log_db_url = os.environ.get("HERMES_LOG_DB_URL", "")
    export_hermes_v2_findings(args.mode, hermes_log_db_url)
    export_hermes_vps_findings(args.mode, vps_log_db_url)

    return 1 if any(f.severity == "critical" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
