#!/usr/bin/env python3
"""
scripts/audit/hermes_vps_reconcile.py — T-LOG.2 checked invariant (S17)

CONTINUOUS_IMPROVEMENT_STANDARD.md Rule T-LOG.2 requires that every
WARNING/ALERT/CRITICAL event be dual-written (findings_log row + Telegram
message) and that a periodic reconciliation flag any unmatched event on either
side.

The Telegram Bot API cannot report a bot's own sent messages, so this diffs
findings_log against log_finding.py's local append-only outbox journal
(telegram_outbox.jsonl + .1), not against Telegram itself.

Three defect classes:
  orphan_telegram  — an outbox line (WARNING+) whose event_uid has no findings_log
                     row → CRITICAL (a page nobody can query — exactly what
                     T-LOG.2 forbids).
  orphan_db        — a findings_log row (WARNING+, post-cutover) with
                     telegram_sent IS NOT TRUE and no matching outbox line →
                     CRITICAL.
  delivery_failed  — matched pair but the outbox line records delivered=false →
                     WARNING.

Pre-cutover rows (event_uid IS NULL) are exempt — they predate the shared helper.

Importable as reconcile(db_url, window_hours=24) -> list[Finding]; also a CLI:
    python scripts/audit/hermes_vps_reconcile.py --window-hours 24 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))
sys.path.insert(0, _SCRIPT_DIR)

import psycopg  # noqa: E402

from log_finding import Finding, log_findings, outbox_path  # noqa: E402


def _read_outbox(since: datetime) -> list[dict]:
    records: list[dict] = []
    for path in (outbox_path(), outbox_path() + ".1"):
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = datetime.fromisoformat(rec["ts"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= since:
                        records.append(rec)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
    return records


def _read_db_rows(db_url: str, since: datetime) -> list[dict]:
    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, severity, summary, event_uid, telegram_sent
                  FROM findings_log
                 WHERE ts >= %s AND severity <> 'info'
                """,
                (since,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


# The escalation check's and reconcile's own output — excluded from the orphan_db
# scan. A meta-check finding that failed its Telegram leg is a delivery_failed
# (warning), never an orphan_db (critical); flagging it as a fresh critical every
# cycle is a feedback loop (S17 smoke test caught this).
_META_SESSION_PREFIXES = ("vps-escalation-", "vps-reconcile-")
_SELF_REPORT_MARKER = "log_finding: dual-write incomplete"


def _is_meta(row: dict) -> bool:
    sr = row.get("session_ref") or ""
    if any(sr.startswith(p) for p in _META_SESSION_PREFIXES):
        return True
    return _SELF_REPORT_MARKER in (row.get("summary") or "")


def reconcile(db_url: str, window_hours: int = 24) -> list[Finding]:
    """One summary finding per run. WARNING+ only when a *substantive* WARNING/
    CRITICAL finding failed to dual-write; INFO on a clean window."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    outbox = [r for r in _read_outbox(since) if r.get("telegram_expected")]
    db_rows = _read_db_rows(db_url, since)

    db_by_uid = {r["event_uid"]: r for r in db_rows if r.get("event_uid")}
    outbox_by_uid = {r["event_uid"]: r for r in outbox}

    orphan_telegram = [rec for uid, rec in outbox_by_uid.items() if uid not in db_by_uid]
    delivery_failed = [rec for uid, rec in outbox_by_uid.items()
                       if uid in db_by_uid and rec.get("delivered") is False]
    orphan_db = [
        r for r in db_rows
        if r.get("event_uid") is not None          # pre-cutover rows are exempt
        and not _is_meta(r)                         # meta-check output is exempt (feedback loop)
        and not r.get("telegram_sent")
        and r["event_uid"] not in outbox_by_uid
    ]

    n_ot, n_od, n_df = len(orphan_telegram), len(orphan_db), len(delivery_failed)
    if n_ot or n_od:
        sev, cat = "critical", "alert"
    elif n_df:
        sev, cat = "warning", "finding"
    else:
        sev, cat = "info", "finding"

    summary = (f"reconcile: {len(outbox)} tg / {len(db_rows)} db WARNING+ in {window_hours}h — "
               f"orphan_telegram={n_ot} orphan_db={n_od} delivery_failed={n_df}")
    bits = []
    for label, rows, key in (("orphan_telegram", orphan_telegram, "summary"),
                             ("delivery_failed", delivery_failed, "summary")):
        for rec in rows[:5]:
            bits.append(f"{label}: uid={rec['event_uid']} \"{rec.get(key)}\"")
    for r in orphan_db[:5]:
        bits.append(f"orphan_db: id={r['id']} \"{r['summary']}\"")
    return [Finding(cat, sev, summary, detail="; ".join(bits))]


def main() -> int:
    p = argparse.ArgumentParser(description="T-LOG.2 reconciliation: findings_log vs Telegram outbox")
    p.add_argument("--window-hours", type=int, default=24)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-log", action="store_true", help="print only, do not dual-write findings")
    args = p.parse_args()

    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    if not db_url:
        print("HERMES_VPS_LOG_DB_URL not set", file=sys.stderr)
        return 2

    findings = reconcile(db_url, window_hours=args.window_hours)
    worst = max((f.severity for f in findings),
                key=lambda s: ("info", "warning", "critical").index(s))

    if args.json:
        print(json.dumps({
            "window_hours": args.window_hours,
            "worst": worst,
            "findings": [{"severity": f.severity, "summary": f.summary, "detail": f.detail}
                         for f in findings],
        }, indent=2))
    else:
        for f in findings:
            print(f"[{f.severity.upper()}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))

    if not args.no_log:
        log_findings(findings, session_ref=f"vps-reconcile-{datetime.now(timezone.utc):%Y%m%d}")

    return 1 if worst == "critical" else 0


if __name__ == "__main__":
    sys.exit(main())
