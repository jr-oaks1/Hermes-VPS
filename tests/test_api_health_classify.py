"""Unit tests for hermes_vps_health_check.classify_api_health (S51).

The bug: when /health reports top-level status="ok" but an agent is unhealthy,
the check recorded summary="api.health: ok" at severity="critical" — the real
reason survived only in `detail`. Live rows id 108/127/133/146/152 are exactly
this. These tests pin that the summary always names the fault and severity
follows it.

Run: pytest tests/ -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

from hermes_vps_health_check import classify_api_health  # noqa: E402


def test_all_healthy_is_info():
    f = classify_api_health("ok", {"a": "healthy", "b": "idle"})
    assert f.severity == "info"
    assert f.summary == "api.health: ok (2 agents)"


def test_disabled_agent_is_benign():
    f = classify_api_health("ok", {"a": "healthy", "fred_data": "disabled"})
    assert f.severity == "info"


def test_ok_status_but_unhealthy_agent_is_critical_and_summary_names_it():
    # the exact live-bug shape
    f = classify_api_health("ok", {"a": "healthy", "cvd_ingestion": "degraded"})
    assert f.severity == "critical"
    assert f.summary != "api.health: ok"
    assert "cvd_ingestion" in f.summary
    assert "degraded" in f.summary
    assert "status=ok" in f.detail


def test_starting_agents_are_warning_not_critical():
    f = classify_api_health("degraded", {"macro_data": "starting", "fred_data": "starting"})
    assert f.severity == "warning"
    assert "starting" in f.summary
    assert "macro_data" in f.summary


def test_mixed_starting_and_degraded_is_critical():
    f = classify_api_health("degraded", {"macro_data": "starting", "cvd_ingestion": "degraded"})
    assert f.severity == "critical"


def test_bad_status_but_agents_ok_is_warning_and_summary_shows_status():
    f = classify_api_health("degraded", {"a": "healthy"})
    assert f.severity == "warning"
    assert "degraded" in f.summary
    assert f.summary != "api.health: ok"
