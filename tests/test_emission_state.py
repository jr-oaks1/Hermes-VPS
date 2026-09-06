"""Unit tests for scripts/emission_state.py + log_finding.initial_action_status (S18).

emission_state.throttle is the shared gate that stopped the Tier 4 escalation
check writing 3 steady-state INFO rows every 15 min (288/day) into a table Rule
T-LOG.3 forbids ever pruning. The critical safety property: with
debounce_default=1 a WARNING/CRITICAL is NEVER suppressed or downgraded — only
steady-state INFO is throttled.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

from log_finding import Finding, initial_action_status  # noqa: E402
from emission_state import throttle, finding_key  # noqa: E402


def _thread(sequence, **kw):
    """Feed a list of raw finding-lists through throttle, threading state; +15min/step."""
    state, ts, outputs = {}, 1_000_000.0, []
    for raw in sequence:
        emitted, state = throttle(raw, state, ts, **kw)
        outputs.append(emitted)
        ts += 900
    return outputs


# --------------------------------------------------------------------------- #
# The escalation-check contract: debounce_default=1
# --------------------------------------------------------------------------- #

def test_threshold_1_emits_warning_on_first_cycle_unchanged():
    w = [Finding("alert", "warning", "escalation: GM escalation — #5")]
    out = _thread([w], debounce_default=1)
    assert len(out[0]) == 1
    assert out[0][0].severity == "warning"
    assert out[0][0].summary == "escalation: GM escalation — #5"   # not downgraded


def test_threshold_1_critical_never_suppressed_even_when_repeated():
    c = [Finding("alert", "critical", "escalation: CEO ESCALATION — #7")]
    out = _thread([c, c, c], debounce_default=1)
    assert [o[0].severity for o in out] == ["critical", "critical", "critical"]


def test_steady_state_info_is_silent_after_first_sight():
    info = [Finding("finding", "info", "reconcile: 1 tg / 3 db WARNING+ in 24h — orphan_telegram=0")]
    out = _thread([info, info, info], debounce_default=1,
                  allclear_every_sec=3600,
                  allclear_summary=lambda n: f"escalation: all {n} checks nominal")
    # cycle 0: all-clear roll-up only (the info line itself is first-sight, not emitted)
    assert any("checks nominal" in f.summary for f in out[0])
    assert all("reconcile" not in f.summary for f in out[0])
    # cycles 1, 2: total silence (roll-up is hourly, +15min steps haven't reached it)
    assert out[1] == [] and out[2] == []


def test_info_reconcile_varying_counts_same_key_stays_silent():
    # the reconcile summary embeds changing numbers but the key is stable
    a = [Finding("finding", "info", "reconcile: 1 tg / 3 db WARNING+ in 24h — orphan_telegram=0")]
    b = [Finding("finding", "info", "reconcile: 2 tg / 5 db WARNING+ in 24h — orphan_telegram=0")]
    assert finding_key(a[0]) == finding_key(b[0]) == "reconcile"
    out = _thread([a, b], debounce_default=1)
    assert out[1] == []


def test_recovery_emits_once_with_custom_wording():
    w = [Finding("alert", "warning", "guardrail.heartbeat: stale 0.5h")]
    ok = [Finding("finding", "info", "guardrail.heartbeat: fresh (0.1h)")]
    out = _thread([w, ok, ok], debounce_default=1,
                  recovered_summary=lambda k: f"{k}: cleared")
    assert out[0][0].severity == "warning"
    assert any(f.summary == "guardrail.heartbeat: cleared" for f in out[1])
    assert all("cleared" not in f.summary for f in out[2])


def test_debounce_default_below_1_is_rejected():
    with pytest.raises(ValueError):
        throttle([], {}, 0.0, debounce_default=0)


# --------------------------------------------------------------------------- #
# The guardrail contract still holds through the shared function
# --------------------------------------------------------------------------- #

def test_guardrail_style_two_cycle_debounce_still_works():
    fail = [Finding("finding", "warning", "disk./: 82% used")]
    out = _thread([fail, fail], debounce_default=2)
    assert out[0][0].severity == "info" and "debounce 1/2" in out[0][0].summary
    assert out[1][0].severity == "warning"


# --------------------------------------------------------------------------- #
# initial_action_status — "open" must mean actionable
# --------------------------------------------------------------------------- #

def test_info_enters_settled():
    assert initial_action_status(Finding("finding", "info", "x: ok")) == "no_action_needed"


def test_warning_and_critical_enter_open():
    assert initial_action_status(Finding("finding", "warning", "x: bad")) == "open"
    assert initial_action_status(Finding("alert", "critical", "x: worse")) == "open"


def test_explicit_action_status_wins():
    f = Finding("finding", "info", "x: tracked", action_status="open")
    assert initial_action_status(f) == "open"
    g = Finding("alert", "critical", "x: known", action_status="in_progress")
    assert initial_action_status(g) == "in_progress"


def test_bad_action_status_rejected_at_construction():
    with pytest.raises(ValueError):
        Finding("finding", "info", "x", action_status="bogus")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
