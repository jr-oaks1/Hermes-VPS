#!/usr/bin/env python3
"""
scripts/audit/hermes_vps_daily_digest.py — Daily operational digest for unified findings

Queries vps_orchestrator_findings for findings from the past 24 hours, aggregates by
severity and source project, and posts a summary to @JRHermesVPSBot.

Runs daily at 09:00 UTC via systemd timer (hermes-vps-daily-digest.timer).

Usage:
    python scripts/audit/hermes_vps_daily_digest.py

Requires (from environment — EnvironmentFile= in the systemd unit):
    FINDINGS_DB_URL         (vps_orchestrator_findings — read-only)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (Hermes VPS bot)

Exit codes: 0 = success, 1 = DB error, 2 = Telegram error, 3 = config error.

S17: ported psycopg2 -> psycopg3 (repo-wide standardization); DB and Telegram
failure paths now dual-write a finding via scripts/log_finding.py (T-LOG.2 —
the digest silently stopping was itself an unlogged warning-grade event).
"""

from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo/scripts
from log_finding import log_finding  # noqa: E402

_SESSION = f"vps-digest-{datetime.now(timezone.utc):%Y%m%d}"


def query_findings_past_24h(db_url: str) -> list[dict] | None:
    """Query vps_orchestrator_findings for past 24 hours."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with psycopg.connect(db_url, connect_timeout=10) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT ts, source_project, severity, category, summary
                    FROM findings_log
                    WHERE ts >= %s
                    ORDER BY ts DESC
                    """,
                    (cutoff,),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"error: database query failed: {e}", file=sys.stderr)
        log_finding("error", "warning", "digest: findings query failed",
                    detail=str(e), session_ref=_SESSION)
        return None


def format_digest(findings: list[dict]) -> str:
    """Format findings into a digest message."""
    if not findings:
        return "📊 Daily Digest (past 24h)\n✅ No findings"

    # Count by severity
    counts = {"critical": 0, "warning": 0, "info": 0}
    by_source = {}

    for f in findings:
        severity = f["severity"]
        counts[severity] += 1
        source = f["source_project"]

        if source not in by_source:
            by_source[source] = {"critical": [], "warning": [], "info": []}
        by_source[source][severity].append(f["summary"])

    # Build message
    lines = ["📊 Daily Digest (past 24h)"]

    # Severity header
    if counts["critical"]:
        lines.append(f"🔴 {counts['critical']} CRITICAL")
    if counts["warning"]:
        lines.append(f"🟡 {counts['warning']} warning")
    if counts["info"]:
        lines.append(f"ℹ️  {counts['info']} info")

    lines.append("")

    # By project
    for source in sorted(by_source.keys()):
        items = by_source[source]
        total = sum(len(v) for v in items.values())
        lines.append(f"<b>{html.escape(source)}</b>: {total} findings")

        for severity in ["critical", "warning", "info"]:
            if items[severity]:
                marker = {"critical": "🔴", "warning": "🟡", "info": "ℹ️ "}[severity]
                for summary in items[severity][:3]:  # Show top 3 per severity
                    lines.append(f"  {marker} {html.escape(summary)}")
                if len(items[severity]) > 3:
                    lines.append(f"  ... and {len(items[severity]) - 3} more {severity}")

    return "\n".join(lines)


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Send digest to Telegram."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if not resp.ok:
            print(f"error: telegram send failed: HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
            log_finding("error", "warning", "digest: Telegram send failed",
                        detail=f"HTTP {resp.status_code}", session_ref=_SESSION)
        return resp.ok
    except Exception as e:
        print(f"error: telegram send failed: {e}", file=sys.stderr)
        log_finding("error", "warning", "digest: Telegram send raised",
                    detail=str(e), session_ref=_SESSION)
        return False


def main() -> int:
    # Load credentials
    findings_db_url = os.environ.get("FINDINGS_DB_URL", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not findings_db_url:
        print("error: FINDINGS_DB_URL not set", file=sys.stderr)
        return 3
    if not bot_token or not chat_id:
        print("error: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return 3

    # Query findings
    findings = query_findings_past_24h(findings_db_url)
    if findings is None:
        return 1

    # Format and send
    digest = format_digest(findings)
    if not send_telegram(bot_token, chat_id, digest):
        return 2

    print(f"info: digest sent ({len(findings)} findings, past 24h)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
