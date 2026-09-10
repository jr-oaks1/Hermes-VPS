"""S19b: check_failed_units() must never count the guardrail's own two units as
a CRITICAL.

The 2026-09-08 → 2026-09-10 deadlock: hermes-vps-guardrail.service exited 1 on a
CRITICAL finding → systemd marked it `failed` → the next run saw its own unit in
`systemctl --failed` → emitted `systemd: 1 failed unit(s)` CRITICAL → exited 1
again. The Tier 4 escalation check then escalated that CRITICAL every 15 min.
Neither unit could return to green. ~39k findings_log rows.

Fix: own units are excluded here; their liveness is the T3.10 guardrail
heartbeat-staleness check's job instead.
"""

from __future__ import annotations

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

import hermes_vps_guardrail as g  # noqa: E402


def _mock_failed(units_text: str):
    return mock.patch.object(
        g.subprocess, "run",
        return_value=mock.Mock(stdout=units_text, returncode=0),
    )


def test_only_own_units_failed_is_info_not_critical():
    text = ("hermes-vps-guardrail.service loaded failed failed x\n"
            "hermes-vps-escalation.service loaded failed failed x\n")
    with _mock_failed(text):
        out = g.check_failed_units()
    assert len(out) == 1
    assert out[0].severity == "info"
    assert "own units excluded" in out[0].detail
    assert "hermes-vps-guardrail.service" in out[0].detail


def test_no_failed_units_at_all_is_info_clean():
    with _mock_failed(""):
        out = g.check_failed_units()
    assert out[0].severity == "info"
    assert out[0].detail == ""  # no own-unit note when nothing is failed


def test_a_real_other_unit_failing_is_still_critical():
    text = ("hermes-vps-guardrail.service loaded failed failed x\n"
            "postgresql@16-main.service loaded failed failed x\n")
    with _mock_failed(text):
        out = g.check_failed_units()
    assert len(out) == 1
    assert out[0].severity == "critical"
    assert "1 failed unit(s)" in out[0].summary          # counts only the non-own one
    assert "postgresql@16-main.service" in out[0].detail
    assert "own units excluded" in out[0].detail          # still notes the excluded one


def test_multiple_real_units_counted_correctly():
    text = ("foo.service loaded failed failed x\n"
            "bar.service loaded failed failed x\n")
    with _mock_failed(text):
        out = g.check_failed_units()
    assert "2 failed unit(s)" in out[0].summary
    assert out[0].severity == "critical"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
