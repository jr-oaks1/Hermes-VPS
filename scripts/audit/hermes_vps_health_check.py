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

Requires (from environment — a single EnvironmentFile=/root/.hermes_vps/.env in
the systemd unit; the old secondary EnvironmentFile=/opt/hermes_v2/.env was
dropped S13 (2026-09-05) — hermes_v2 is decommissioned and every var below is
already in this project's own env file):
    DATABASE_URL            (hermes_v2 DB — replication + ingestion freshness reads)
    HERMES_VPS_LOG_DB_URL   (hermes_vps_log — findings_log writes)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (Hermes VPS's own bot)

Exit codes: 0 = no critical finding, 1 = at least one critical finding, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import psycopg
import requests
import urllib3

# S17: the Finding dataclass and all findings_log / Telegram writes now live in
# the shared dual-write helper (T-LOG.2 — every warning/alert event is written to
# findings_log AND @JRHermesVPSBot, in one call). This module only produces
# Finding objects; log_findings() is the single sink.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo/scripts
from log_finding import Finding, log_findings, log_finding  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INGESTION_STALE_WARN_MIN = 15
TLS_EXPIRY_WARN_DAYS = 21
TLS_CERT_PATH = "/etc/letsencrypt/live/artek-studio.com/fullchain.pem"
PG_BACKUP_CONF = "/etc/pg_backup.conf"
# hermes-ingestor is the live app on this host (hermes_v2.service decommissioned
# 2026-08-26; listing it here produced a false CRITICAL every run until S13).
SYSTEMD_SERVICES = ("hermes-ingestor", "nginx", "postgresql")


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
        # "disabled" is an operator choice (e.g. fred_data), not a fault — treat it
        # like the other benign states so it doesn't force a false CRITICAL (S13).
        bad_agents = {
            aid: s for aid, s in agents.items()
            if s not in ("healthy", "idle", "role_excluded", "disabled")
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


def check_findings_hypertable_integrity(vps_log_db_url: str) -> list[Finding]:
    """T3.12 for findings_log (a TimescaleDB hypertable since S17): assert the
    parent-level unique index is valid, a compression policy exists, and NO
    retention policy exists (Rule T-LOG.3 — the log is permanent)."""
    findings = []
    try:
        with psycopg.connect(vps_log_db_url, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*) FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'findings_log'
                """)
                if cur.fetchone()[0] == 0:
                    findings.append(Finding("finding", "warning",
                        "findings_log: not a hypertable (S17 migration not applied?)"))
                    return findings
                cur.execute("""
                    SELECT count(*) FROM pg_index i
                    JOIN pg_class c ON c.oid = i.indexrelid
                    WHERE c.relname = 'findings_log_event_uid_ts_uidx' AND i.indisvalid
                """)
                uidx_ok = cur.fetchone()[0] == 1
                cur.execute("""
                    SELECT count(*) FROM timescaledb_information.jobs
                    WHERE proc_name LIKE '%retention%'
                      AND hypertable_name = 'findings_log'
                """)
                retention_jobs = cur.fetchone()[0]
                cur.execute("""
                    SELECT count(*) FROM timescaledb_information.jobs
                    WHERE proc_name LIKE '%compression%'
                      AND hypertable_name = 'findings_log'
                """)
                compression_jobs = cur.fetchone()[0]
        if retention_jobs:
            findings.append(Finding("alert", "critical",
                "findings_log: a RETENTION policy exists — Rule T-LOG.3 forbids it, the log is permanent"))
        if not uidx_ok:
            findings.append(Finding("finding", "warning",
                "findings_log: event_uid unique index missing or invalid"))
        if not compression_jobs:
            findings.append(Finding("finding", "warning",
                "findings_log: no compression policy (expected compress_after 90d)"))
        if not findings:
            findings.append(Finding("finding", "info",
                "findings_log: hypertable healthy (unique idx valid, compression on, no retention)"))
    except Exception as e:
        findings.append(Finding("error", "warning", "findings_log: hypertable check failed", str(e)))
    return findings


def check_git_sync(repo_dir: str) -> list[Finding]:
    """Checks one repo's local-vs-origin sync. S13: now only this project's own
    /opt/hermes-vps deploy clone -- the /opt/hermes_v2 check was dropped with the
    hermes_v2 decommission."""
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


_EXPORT_COMMIT_PREFIX = "chore: findings export"


def _sync_repo_to_origin(repo_dir: str) -> bool:
    """Bring a deploy clone back in line with origin/main BEFORE we write the
    export into it. The clone is a deploy target, not a source of truth — a
    prior run's unpushable commit (transient network failure, or the pre-S13
    divergence) must not accumulate into a forked history. Guard: only hard-reset
    when every local-only commit is one of ours (the export chore); if a real
    hand-made commit is sitting on the clone, leave it alone and skip the export
    so a human notices."""
    label = os.path.basename(repo_dir.rstrip("/"))
    try:
        subprocess.run(["git", "-C", repo_dir, "fetch", "origin", "main", "--quiet"],
                       timeout=30, check=True)
        local_only = subprocess.run(
            ["git", "-C", repo_dir, "log", "--format=%s", "origin/main..HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()
        foreign = [s for s in local_only if not s.startswith(_EXPORT_COMMIT_PREFIX)]
        if foreign:
            msg = (f"findings-export: {len(foreign)} non-export local commit(s) on {label} "
                   f"— export skipped, needs manual review")
            print(msg + f" ({foreign[0]!r}...)", file=sys.stderr)
            log_finding("finding", "warning", f"export.{label}: sync blocked", detail=msg)
            return False
        subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"],
                       timeout=30, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"repo sync ({label}): failed: {e}", file=sys.stderr)
        log_finding("error", "warning", f"export.{label}: repo sync failed", detail=str(e))
        return False


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
             f"{_EXPORT_COMMIT_PREFIX} ({mode}, {datetime.now(timezone.utc):%Y-%m-%d})"],
            check=True,
        )
        try:
            subprocess.run(["git", "-C", repo_dir, "push", "origin", "main"],
                           check=True, capture_output=True, text=True, timeout=30)
            print(f"findings export ({label}): committed and pushed")
        except Exception as e:
            # Roll the commit back so the clone stays exactly at origin/main —
            # _sync_repo_to_origin would clean it next run anyway, but not leaving
            # a dangling commit keeps `git status` honest in the meantime.
            subprocess.run(["git", "-C", repo_dir, "reset", "--hard", "origin/main"],
                           check=False, capture_output=True)
            print(f"findings export ({label}): push failed, commit rolled back: {e}",
                  file=sys.stderr)
            log_finding("error", "warning", f"export.{label}: push failed",
                        detail=f"commit rolled back; cloud-review feed will go stale: {e}")
    except Exception as e:
        print(f"findings export ({label}): git commit failed: {e}", file=sys.stderr)
        log_finding("error", "warning", f"export.{label}: git commit failed", detail=str(e))


def export_hermes_vps_findings(mode: str, vps_log_db_url: str, repo_dir: str = "/opt/hermes-vps") -> None:
    """Dump hermes_vps_log findings_log rows into this project's own repo so the
    VPS-scoped RemoteTrigger cloud-review routine can read them (cloud agents
    can't reach this Tailscale-only host directly). S13: the parallel
    export_hermes_v2_findings() was removed — it pushed to the decommissioned
    hermes_v2 repo and had been failing every run since ~2026-08-26."""
    if not _sync_repo_to_origin(repo_dir):
        return
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


def _summary_header(mode: str, findings: list[Finding]) -> str:
    """The 🔴/🟡/✅ run header. S17: message body + delivery is log_findings()'s
    job; this only supplies the header line so that UX is preserved."""
    n_crit = sum(1 for f in findings if f.severity == "critical")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    label = "Monthly forensic audit" if mode == "deep" else "Weekly health check"
    if n_crit:
        return f"🔴 {label} — {n_crit} CRITICAL, {n_warn} warning"
    if n_warn:
        return f"🟡 {label} — {n_warn} warning(s), rest OK"
    return f"✅ {label} — all {len(findings)} checks OK"


def _send_allclear(mode: str, findings: list[Finding]) -> None:
    """log_findings() only messages WARNING+; an all-INFO run still gets its
    reassuring ✅ line (the health check has always sent one every run)."""
    if any(f.severity != "info" for f in findings):
        return
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (bot_token and chat_id):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": _summary_header(mode, findings) + "\n(hermes-vps)"},
            timeout=15,
        )
    except Exception:
        pass


_GM_MIRROR = "/opt/jrvps-orchestrator/scripts/log_operational_finding.py"


def _mirror_to_unified_db(findings: list[Finding], session_ref: str) -> None:
    """Shell each finding to the GM-owned log_operational_finding.py so JR Hermes
    VPS findings reach vps_orchestrator_findings (GM monthly synthesis + GM
    EscalationCheck). S17: rc is now captured — a mirror failure becomes a
    warning finding via log_finding() instead of a silent stderr line."""
    if not os.environ.get("FINDINGS_DB_URL"):
        log_finding("finding", "warning",
                    "mirror: FINDINGS_DB_URL not set — unified-DB mirror skipped",
                    detail="JR Hermes VPS findings will not reach the GM's synthesis / EscalationCheck",
                    session_ref=session_ref)
        return
    if not os.path.exists(_GM_MIRROR):
        log_finding("finding", "warning", f"mirror: GM script missing at {_GM_MIRROR}",
                    session_ref=session_ref)
        return
    fails = 0
    for f in findings:
        cmd = [
            "/opt/hermes-vps/.venv/bin/python3", _GM_MIRROR,
            "--source_project", "JR Hermes VPS",
            "--severity", f.severity, "--category", f.category, "--summary", f.summary,
        ]
        if f.detail:
            cmd += ["--detail", f.detail]
        if session_ref:
            cmd += ["--session", session_ref]
        if f.severity == "info":
            cmd.append("--no-telegram")
        try:
            r = subprocess.run(cmd, check=False, timeout=30, capture_output=True, text=True)
            if r.returncode != 0:
                fails += 1
        except Exception:
            fails += 1
    if fails:
        log_finding("error", "warning", f"mirror: {fails}/{len(findings)} unified-DB writes failed",
                    session_ref=session_ref)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes VPS recurring health check / forensic audit")
    parser.add_argument("--mode", choices=("quick", "deep"), required=True)
    parser.add_argument("--session-ref", default=None)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "")
    vps_log_db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    session_ref = args.session_ref or f"vps-healthcheck-{args.mode}-{datetime.now(timezone.utc):%Y%m%d}"

    if not database_url or not vps_log_db_url:
        # T-LOG.2 violation-by-design: can't write findings_log without its DSN —
        # but Telegram is still reachable. Page, then exit.
        msg = "config: DATABASE_URL / HERMES_VPS_LOG_DB_URL not set — health check cannot run"
        print(msg, file=sys.stderr)
        if bot_token and chat_id:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": f"🔴 {msg}\n(hermes-vps)"}, timeout=10,
                )
            except Exception:
                pass
        return 2

    findings: list[Finding] = []
    findings += check_systemd_services()
    findings += check_api_health()
    findings += check_replication(database_url)
    findings += check_ingestion_freshness(database_url)

    if args.mode == "deep":
        findings += check_backup_currency()
        findings += check_tls_expiry()
        findings += check_git_sync("/opt/hermes-vps")
        findings += check_findings_hypertable_integrity(vps_log_db_url)

    # Single dual-write: findings_log + @JRHermesVPSBot, one call, per-event
    # correlated (event_uid), self-reporting on partial failure (T-LOG.2).
    log_findings(findings, session_ref=session_ref,
                 header=_summary_header(args.mode, findings))
    _send_allclear(args.mode, findings)

    # Mirror to the unified findings DB (feeds the GM's monthly synthesis + the
    # GM's own EscalationCheck). Best-effort — but a failure is now a finding,
    # not a swallowed stderr line.
    _mirror_to_unified_db(findings, session_ref)

    for f in findings:
        print(f"[{f.severity.upper()}] {f.category}.{f.summary}" + (f" — {f.detail}" if f.detail else ""))

    export_hermes_vps_findings(args.mode, vps_log_db_url)

    return 1 if any(f.severity == "critical" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
