#!/usr/bin/env python3
"""
scripts/log_finding.py — JR Hermes VPS shared dual-write finding logger (S17)

The ONLY place in this repo allowed to call the Telegram Bot API or
INSERT into hermes_vps_log.findings_log. Every WARNING/ALERT/CRITICAL event
this project's tooling emits at runtime MUST route through here, so that
CONTINUOUS_IMPROVEMENT_STANDARD.md Rule T-LOG.2 ("every warning/alert event is
dual-written, always") holds by construction rather than by discipline.

Modeled on JR Hermes Ingestor's scripts/log_finding.py, with three deltas:
  1. No config.settings module here — read os.environ directly (HERMES_VPS_LOG_DB_URL,
     TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID), matching hermes_vps_health_check.py.
  2. Every event carries an `event_uid` written to BOTH sinks — this is what makes
     the T-LOG.2 reconciliation check (hermes_vps_reconcile.py) possible at all.
  3. A local append-only outbox journal (telegram_outbox.jsonl). The Telegram Bot
     API gives a bot no way to read its own sent messages (getUpdates is inbound
     only), so reconciliation diffs findings_log against this journal, not against
     Telegram. This is the one place T-LOG.2's literal wording ("diff recent
     Telegram alerts against recent findings-log rows") cannot be implemented as
     written — see docs/sessions/S17-HANDOFF.md.

Two ways to use it:
  CLI  — ad-hoc findings during live work (Rule T-LOG.1):
    python scripts/log_finding.py --category finding --severity warning \
        --summary "..." --detail "..." --session S17 [--owner-project "JR Hermes VPS"]
  Import — the health check / guardrail / escalation check call:
    from log_finding import Finding, log_findings, log_finding

Retention: findings_log is a PERMANENT historical record for continuous
improvement. This module NEVER deletes. See CONTINUOUS_IMPROVEMENT_STANDARD.md
Rule T-LOG.3.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psycopg
import requests

SEVERITIES = ("info", "warning", "critical")
CATEGORIES = ("finding", "error", "note", "alert")
ACTION_STATUSES = ("open", "in_progress", "resolved", "closed", "no_action_needed")
SOURCE = "hermes-vps"

# S18: which severities enter the log as an unresolved work item. "open" must mean
# "a human still has to do something" — otherwise the Tier 4 ladder and the
# "0 open actionable findings" health metric both drown in steady-state INFO.
_ACTIONABLE_SEVERITIES = ("warning", "critical")

# WARNING and above must reach Telegram; INFO is findings-log only (T-LOG.2 §exempt).
_TELEGRAM_MIN_SEVERITY = ("warning", "critical")

_OUTBOX_MAX_BYTES = 5 * 1024 * 1024


def state_dir() -> str:
    """Where the outbox journal and other runtime state live. Overridable for
    staging smoke tests so a test run never touches live state."""
    return os.environ.get("HERMES_VPS_STATE_DIR", "/var/lib/hermes-vps")


def outbox_path() -> str:
    return os.path.join(state_dir(), "telegram_outbox.jsonl")


@dataclass
class Finding:
    category: str            # finding | error | note | alert
    severity: str            # info | warning | critical
    summary: str
    detail: str = ""
    owner_project: str | None = None
    event_uid: str = field(default_factory=lambda: uuid.uuid4().hex)
    # S18: normally None → derived from severity by initial_action_status().
    # Set explicitly only to force an INFO row 'open' (a genuine work item that
    # happens to be low-severity) or to pre-close a warning.
    action_status: str | None = None

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"bad severity {self.severity!r}")
        if self.category not in CATEGORIES:
            raise ValueError(f"bad category {self.category!r}")
        if self.action_status is not None and self.action_status not in ACTION_STATUSES:
            raise ValueError(f"bad action_status {self.action_status!r}")


def initial_action_status(f: "Finding") -> str:
    """The action_status a finding enters findings_log with.

    An explicit f.action_status always wins. Otherwise it is derived from
    severity: an INFO row is a permanent observation, never a work item, so it
    enters already settled; a WARNING/CRITICAL row is actionable until a human
    dispositions it.
    """
    if f.action_status is not None:
        return f.action_status
    return "open" if f.severity in _ACTIONABLE_SEVERITIES else "no_action_needed"


# --------------------------------------------------------------------------- #
# Telegram leg
# --------------------------------------------------------------------------- #

def _format_message(findings: list[Finding], header: str | None) -> str:
    lines: list[str] = []
    if header:
        lines.append(header)
    for f in findings:
        marker = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}[f.severity]
        line = f"{marker} {f.summary}"
        if f.detail:
            line += f" — {f.detail}"
        lines.append(line)
    lines.append("(hermes-vps)")
    return "\n".join(lines)


def _append_outbox(records: list[dict]) -> None:
    """Write-ahead journal: append one line per event BEFORE returning, so an
    outbox line with no matching findings_log row (process died mid-write) is
    detectable by reconciliation."""
    path = outbox_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # size-based rotation; reconcile reads both <path> and <path>.1
    try:
        if os.path.exists(path) and os.path.getsize(path) > _OUTBOX_MAX_BYTES:
            os.replace(path, path + ".1")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, default=str) + "\n")


def send_telegram(
    bot_token: str,
    chat_id: str,
    findings: list[Finding],
    header: str | None = None,
) -> dict[str, bool]:
    """Send the WARNING+ findings as one message. Returns {event_uid: delivered}.
    Every uid — including INFO ones that were not sent — gets a journal line so
    reconciliation has a complete picture."""
    to_send = [f for f in findings if f.severity in _TELEGRAM_MIN_SEVERITY]
    delivered = False
    error = None
    if to_send and bot_token and chat_id:
        text = _format_message(to_send, header)
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=15,
            )
            delivered = resp.ok
            if not resp.ok:
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:  # noqa: BLE001
            error = str(e)
    elif to_send and not (bot_token and chat_id):
        error = "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set"

    now = datetime.now(timezone.utc).isoformat()
    status: dict[str, bool] = {}
    records: list[dict] = []
    for f in findings:
        sent = delivered if f.severity in _TELEGRAM_MIN_SEVERITY else None
        status[f.event_uid] = bool(sent)
        records.append({
            "event_uid": f.event_uid,
            "ts": now,
            "severity": f.severity,
            "category": f.category,
            "summary": f.summary,
            "telegram_expected": f.severity in _TELEGRAM_MIN_SEVERITY,
            "delivered": sent,
            "error": error if f.severity in _TELEGRAM_MIN_SEVERITY else None,
        })
    _append_outbox(records)
    return status


# --------------------------------------------------------------------------- #
# findings_log leg
# --------------------------------------------------------------------------- #

def insert_findings(
    db_url: str,
    session_ref: str | None,
    findings: list[Finding],
    telegram_status: dict[str, bool],
) -> int:
    """One transaction, one row per finding. Writes event_uid + telegram_sent +
    owner_project + action_status (via initial_action_status — INFO enters
    settled, WARNING/CRITICAL enters 'open') alongside the existing columns.
    Returns rows written."""
    rows = [
        (
            session_ref, f.category, f.severity, f.summary, f.detail or None,
            SOURCE, bool(telegram_status.get(f.event_uid, False)),
            f.event_uid, f.owner_project, initial_action_status(f),
        )
        for f in findings
    ]
    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO findings_log
                    (session_ref, category, severity, summary, detail, source,
                     telegram_sent, event_uid, owner_project, action_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    return len(rows)


# --------------------------------------------------------------------------- #
# The entry points
# --------------------------------------------------------------------------- #

def log_findings(
    findings: list[Finding],
    *,
    session_ref: str | None = None,
    header: str | None = None,
    dry_run: bool = False,
) -> int:
    """THE dual-write entry point. Telegram first (so a DB outage still pages),
    findings_log second, then a self-report: if either half failed, emit a
    synthetic critical Finding through the surviving channel. Never raises.

    Returns 0 on full success, 1 if either leg failed.
    """
    if not findings:
        return 0

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")

    if dry_run:
        print("--- DRY RUN — no writes ---")
        print("TELEGRAM:")
        print(_format_message([f for f in findings if f.severity in _TELEGRAM_MIN_SEVERITY], header)
              or "(nothing above INFO — no Telegram message)")
        print("\nfindings_log rows:")
        for f in findings:
            print(f"  {f.severity:8} {f.category:8} {f.summary!r} uid={f.event_uid} owner={f.owner_project}")
        return 0

    tg_ok = True
    db_ok = True
    tg_status: dict[str, bool] = {}

    try:
        tg_status = send_telegram(bot_token, chat_id, findings, header=header)
        expected = [f for f in findings if f.severity in _TELEGRAM_MIN_SEVERITY]
        if expected and not all(tg_status.get(f.event_uid) for f in expected):
            tg_ok = False
    except Exception as e:  # noqa: BLE001
        tg_ok = False
        print(f"log_finding: telegram leg raised: {e}", file=sys.stderr)

    if db_url:
        try:
            insert_findings(db_url, session_ref, findings, tg_status)
        except Exception as e:  # noqa: BLE001
            db_ok = False
            print(f"log_finding: findings_log leg raised: {e}", file=sys.stderr)
    else:
        db_ok = False
        print("log_finding: HERMES_VPS_LOG_DB_URL not set — findings_log write skipped", file=sys.stderr)

    if not (tg_ok and db_ok):
        _self_report(db_url, bot_token, chat_id, session_ref, tg_ok, db_ok)
        return 1
    return 0


def _self_report(db_url, bot_token, chat_id, session_ref, tg_ok, db_ok) -> None:
    """A dual-write that half-succeeded must be visible, never swallowed."""
    which = []
    if not tg_ok:
        which.append("Telegram")
    if not db_ok:
        which.append("findings_log")
    marker = Finding(
        "error", "critical",
        f"log_finding: dual-write incomplete ({', '.join(which)} leg failed)",
        detail="A finding was emitted but did not reach both sinks — T-LOG.2 breach.",
    )
    # Route the marker through the normal legs so it stays consistent (an outbox
    # line AND a DB row, or the reconciliation check flags the marker itself as an
    # orphan every cycle — a feedback loop).
    tg_status: dict[str, bool] = {}
    if bot_token and chat_id:
        try:
            tg_status = send_telegram(bot_token, chat_id, [marker], header="🔴 T-LOG.2 self-report")
        except Exception:  # noqa: BLE001
            pass
    if db_url:
        try:
            insert_findings(db_url, session_ref, [marker], tg_status)
        except Exception:  # noqa: BLE001
            pass


def log_finding(
    category: str,
    severity: str,
    summary: str,
    detail: str | None = None,
    *,
    session_ref: str | None = None,
    owner_project: str | None = None,
    dry_run: bool = False,
) -> int:
    """Single-event convenience wrapper for guardrail / escalation / ad-hoc use."""
    return log_findings(
        [Finding(category, severity, summary, detail or "", owner_project=owner_project)],
        session_ref=session_ref,
        dry_run=dry_run,
    )


# --------------------------------------------------------------------------- #
# Shared DB read layer for Tier 4 (used by hermes_vps_escalation_check.py)
# --------------------------------------------------------------------------- #

def open_critical(db_url: str, since: datetime) -> list[dict]:
    """Unresolved CRITICAL rows newer than `since`, newest first. Mirrors
    JR_VPS_Orchestrators FindingsLogReader.open_critical (synchronous here)."""
    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, ts, session_ref, category, severity, summary, detail,
                       source, action_status, owner_project,
                       escalated_gm_at, escalated_ceo_at
                  FROM findings_log
                 WHERE severity = 'critical'
                   AND action_status IN ('open', 'in_progress')
                   AND ts > %s
                 ORDER BY ts DESC
                """,
                (since,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_escalated(db_url: str, finding_id: int, level: str) -> None:
    """Latch a notification so a 15-min timer doesn't re-page the same row.
    Records notification, not state — the band is still re-derived every cycle."""
    col = {"gm": "escalated_gm_at", "ceo": "escalated_ceo_at"}[level]
    with psycopg.connect(db_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE findings_log SET {col} = now() "
                f"WHERE id = %s AND {col} IS NULL",
                (finding_id,),
            )
        conn.commit()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="Dual-write a finding to findings_log + @JRHermesVPSBot")
    p.add_argument("--category", required=True, choices=CATEGORIES)
    p.add_argument("--severity", default="info", choices=SEVERITIES)
    p.add_argument("--summary", required=True)
    p.add_argument("--detail", default=None)
    p.add_argument("--session", dest="session_ref", default=None)
    p.add_argument("--owner-project", dest="owner_project", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    rc = log_finding(
        args.category, args.severity, args.summary, args.detail,
        session_ref=args.session_ref, owner_project=args.owner_project,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        print("logged" if rc == 0 else "logged WITH ERRORS (see stderr / self-report)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
