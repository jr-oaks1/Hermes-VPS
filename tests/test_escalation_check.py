"""Unit tests for hermes_vps_escalation_check — Tier 4 durable escalation (S17).

State is the findings_log row itself (ts + action_status), never anything held
in the check. These tests exercise the pure classification functions directly:
constructing rows with fabricated ages and asserting the same classification is
re-derived every time, with nothing cached between calls.

Run: pip install -r requirements-dev.txt && pytest tests/ -q
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

from hermes_vps_escalation_check import (  # noqa: E402
    classify_row, classify_escalations, check_guardrail_heartbeat,
    queue_integrity_finding,
)


class TestQueueIntegrity:
    """S51: a bulk age-based settle silently emptied the Tier 4 ladder once
    (deploy/sql/S17_findings_log_tier4.sql). queue_integrity_finding is the
    runtime half of the guard (deploy_guardrail.sh step 7b is the deploy half)."""

    def test_clean_is_info(self):
        f = queue_integrity_finding([])
        assert f.severity == "info"
        assert f.summary.startswith("queue-integrity:")

    def test_untriaged_rows_are_warning_and_listed(self):
        rows = [{"id": 105}, {"id": 152}, {"id": 239}]
        f = queue_integrity_finding(rows)
        assert f.severity == "warning"
        assert "3 WARNING/CRITICAL" in f.summary
        assert "#105" in f.detail and "#239" in f.detail

    def test_key_prefix_isolates_it_from_escalation_alerts(self):
        # emission_state derives the state-machine key from the text before ':'
        assert queue_integrity_finding([]).summary.split(":")[0] == "queue-integrity"
        assert queue_integrity_finding([{"id": 1}]).summary.split(":")[0] == "queue-integrity"


def _row(fid, ts, action_status="open", owner_project=None,
         escalated_gm_at=None, escalated_ceo_at=None):
    return {
        "id": fid, "ts": ts, "severity": "critical", "category": "alert",
        "summary": f"synthetic #{fid}", "action_status": action_status,
        "owner_project": owner_project,
        "escalated_gm_at": escalated_gm_at, "escalated_ceo_at": escalated_ceo_at,
    }


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


class TestClassifyRow:
    def test_below_gm_threshold_is_info_band_none(self):
        c = classify_row(_row(1, NOW - timedelta(minutes=30)), NOW)
        assert c["level"] == "info" and c["band"] == "none"

    def test_over_2h_open_is_gm_warning(self):
        c = classify_row(_row(2, NOW - timedelta(hours=3)), NOW)
        assert c["level"] == "warning" and c["band"] == "gm"
        assert "GM escalation" in c["message"]

    def test_over_24h_open_is_ceo_critical(self):
        c = classify_row(_row(3, NOW - timedelta(hours=30)), NOW)
        assert c["level"] == "critical" and c["band"] == "ceo"
        assert "CEO ESCALATION" in c["message"]

    def test_in_progress_with_owner_caps_at_gm_even_at_3_days(self):
        c = classify_row(
            _row(4, NOW - timedelta(days=3), action_status="in_progress",
                 owner_project="JR Hermes VPS"),
            NOW,
        )
        assert c["level"] == "warning" and c["band"] == "gm"
        assert "owned by JR Hermes VPS" in c["message"]

    def test_in_progress_without_owner_still_hits_ceo(self):
        c = classify_row(
            _row(5, NOW - timedelta(hours=30), action_status="in_progress",
                 owner_project=None),
            NOW,
        )
        assert c["level"] == "critical" and c["band"] == "ceo"

    def test_in_progress_owned_below_threshold_is_info(self):
        c = classify_row(
            _row(6, NOW - timedelta(minutes=30), action_status="in_progress",
                 owner_project="PionexBots"),
            NOW,
        )
        assert c["level"] == "info" and c["band"] == "none"

    def test_naive_timestamp_is_treated_as_utc(self):
        c = classify_row(_row(7, (NOW - timedelta(hours=3)).replace(tzinfo=None)), NOW)
        assert c["band"] == "gm"

    def test_state_is_the_row_not_the_call(self):
        row = _row(8, NOW - timedelta(hours=25))
        a = classify_row(row, NOW)
        b = classify_row(row, NOW)
        assert a == b == classify_row(dict(row), NOW)


class TestClassifyEscalations:
    def test_one_entry_per_row_always(self):
        rows = [
            _row(10, NOW - timedelta(minutes=10)),
            _row(11, NOW - timedelta(hours=3)),
            _row(12, NOW - timedelta(hours=30)),
        ]
        out = classify_escalations(rows, NOW)
        assert len(out) == 3
        assert [c["band"] for _, c in out] == ["none", "gm", "ceo"]

    def test_empty_rows_empty_result(self):
        assert classify_escalations([], NOW) == []


class TestHeartbeatStaleness:
    def test_missing_heartbeat_timer_disabled_is_info(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_VPS_STATE_DIR", str(tmp_path))
        out = check_guardrail_heartbeat(NOW, timer_enabled=False)
        assert out[0].severity == "info"

    def test_missing_heartbeat_timer_enabled_is_warning(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_VPS_STATE_DIR", str(tmp_path))
        out = check_guardrail_heartbeat(NOW, timer_enabled=True)
        assert out[0].severity == "warning"

    def test_fresh_heartbeat_is_info(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_VPS_STATE_DIR", str(tmp_path))
        hb = tmp_path / "guardrail.heartbeat"
        hb.write_text("{}")
        out = check_guardrail_heartbeat(datetime.now(timezone.utc), timer_enabled=True)
        assert out[0].severity == "info"

    def test_stale_heartbeat_over_60min_is_critical(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_VPS_STATE_DIR", str(tmp_path))
        hb = tmp_path / "guardrail.heartbeat"
        hb.write_text("{}")
        old = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
        os.utime(hb, (old, old))
        out = check_guardrail_heartbeat(datetime.now(timezone.utc), timer_enabled=True)
        assert out[0].severity == "critical"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
