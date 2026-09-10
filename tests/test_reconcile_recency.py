"""S19b: reconcile must not re-alarm on a resolved incident.

During the 2026-09-08→10 deadlock storm the Telegram outbox journal accumulated
~16k delivered=false lines and the findings_log ~30k open orphan rows. Before
S19b, reconcile re-emitted a CRITICAL every 15 min for the full 24h window after
the storm was already triaged. Now:
  - orphan_db counts only open/in_progress rows (a dispositioned row is not an
    actionable orphan);
  - delivery_failed is recency-gated to 6h, same as orphan_telegram.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

import hermes_vps_reconcile as r  # noqa: E402

NOW = datetime.now(timezone.utc)


def _outbox_line(uid, ts, delivered):
    return {"event_uid": uid, "ts": ts.isoformat(), "severity": "warning",
            "category": "alert", "summary": f"x {uid}", "telegram_expected": True,
            "delivered": delivered}


def _db_row(uid, ts, action_status="open", telegram_sent=False):
    return {"id": int(uid[1:]), "ts": ts, "severity": "warning", "summary": f"x {uid}",
            "event_uid": uid, "telegram_sent": telegram_sent,
            "action_status": action_status, "session_ref": "vps-guardrail-20260910"}


def _run(outbox, db_rows):
    with mock.patch.object(r, "_read_outbox", return_value=outbox), \
         mock.patch.object(r, "_read_db_rows", return_value=db_rows):
        return r.reconcile("postg://unused", window_hours=24)[0]


def test_old_delivery_failures_do_not_alarm():
    old = NOW - timedelta(hours=20)
    outbox = [_outbox_line(f"u{i}", old, False) for i in range(5000)]
    db_rows = [_db_row(f"u{i}", old, action_status="no_action_needed") for i in range(5000)]
    f = _run(outbox, db_rows)
    assert f.severity == "info", f.summary
    assert "delivery_failed=0" in f.summary


def test_recent_delivery_failure_is_warning():
    fresh = NOW - timedelta(minutes=30)
    outbox = [_outbox_line("u1", fresh, False)]
    db_rows = [_db_row("u1", fresh)]
    f = _run(outbox, db_rows)
    assert f.severity == "warning"
    assert "delivery_failed=1" in f.summary


def test_triaged_orphan_db_rows_do_not_alarm():
    old = NOW - timedelta(hours=10)
    # rows with no outbox match, telegram_sent false, but dispositioned
    db_rows = [_db_row(f"u{i}", old, action_status="no_action_needed") for i in range(30000)]
    f = _run([], db_rows)
    assert f.severity == "info", f.summary
    assert "orphan_db=0" in f.summary


def test_open_orphan_db_row_is_critical():
    old = NOW - timedelta(hours=10)
    db_rows = [_db_row("u1", old, action_status="open")]
    f = _run([], db_rows)
    assert f.severity == "critical"
    assert "orphan_db=1" in f.summary


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
