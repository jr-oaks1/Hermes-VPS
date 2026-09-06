"""Unit tests for hermes_vps_guardrail debounce + state logic (S17).

The debounce is what stops a 5-minute guardrail turning a transient blip into a
page (Clevious S71: ~115 false 'replication offline' findings). These tests pin
that behaviour: a failing check must fail N consecutive cycles before it emits
above INFO; recovery emits exactly one 'recovered'; INFO does not spam.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "audit"))

from log_finding import Finding  # noqa: E402
from hermes_vps_guardrail import apply_debounce  # noqa: E402


def _run(sequence, thresholds_key="disk./"):
    """Feed a sequence of raw finding-lists through apply_debounce, threading state."""
    state = {}
    ts = 1_000_000.0
    outputs = []
    for raw in sequence:
        emitted, state = apply_debounce(raw, state, ts)
        outputs.append(emitted)
        ts += 300  # +5 min
    return outputs


def test_single_failure_is_suppressed_to_info():
    out = _run([[Finding("finding", "warning", "disk./: 82% used")]])
    assert out[0][0].severity == "info"
    assert "debounce 1/2" in out[0][0].summary


def test_two_consecutive_failures_emit_warning():
    fail = [Finding("finding", "warning", "disk./: 82% used")]
    out = _run([fail, fail])
    assert out[0][0].severity == "info"
    assert out[1][0].severity == "warning"


def test_replication_needs_three_cycles():
    fail = [Finding("finding", "warning", "replication: no standby reporting")]
    out = _run([fail, fail, fail])
    assert [o[0].severity for o in out] == ["info", "info", "warning"]


def test_recovery_emits_one_recovered_then_quiet():
    fail = [Finding("finding", "warning", "disk./: 82% used")]
    ok = [Finding("finding", "info", "disk./: 40% used")]
    out = _run([fail, fail, ok, ok])
    assert out[1][0].severity == "warning"
    assert any("recovered" in f.summary for f in out[2])
    # 4th cycle: steady-state OK, no per-check spam (all-clear roll-up is time-gated)
    assert all("recovered" not in f.summary for f in out[3])


def test_all_clear_rollup_is_hourly_not_every_cycle():
    ok = [Finding("finding", "info", "disk./: 40% used")]
    # 3 cycles = 15 min elapsed inside _run; first emits the roll-up, next two don't
    out = _run([ok, ok, ok])
    assert any("all" in f.summary and "checks OK" in f.summary for f in out[0])
    assert not any("checks OK" in f.summary for f in out[1])
    assert not any("checks OK" in f.summary for f in out[2])


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
