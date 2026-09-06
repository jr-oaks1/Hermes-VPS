#!/usr/bin/env python3
"""
scripts/emission_state.py — shared state-change / hourly-roll-up emission gate (S18)

Extracted from hermes_vps_guardrail.apply_debounce so the Tier 3 guardrail and the
Tier 4 escalation check share ONE implementation of the emission discipline
CONTINUOUS_IMPROVEMENT_STANDARD.md wants:

  * a WARNING/CRITICAL finding is emitted UNCHANGED once its key has failed N
    consecutive cycles; before then it is downgraded to an INFO "(debounce n/N)"
    line (N-cycle debounce — stops a 5-min cadence turning a blip into a page);
  * an INFO finding is emitted ONLY when its key's status changed since the last
    cycle (a recovery), or as the single hourly all-clear roll-up.

Why this is not in log_finding.py: that module is the T-LOG.2 dual-write sink, and
its one invariant is "everything handed to me reaches both sinks". A suppression
rule living inside it could one day silently drop a WARNING — exactly what T-LOG.2
exists to prevent. The gate belongs in the caller; the sink stays dumb.

The guardrail passes debounce_default=2 (transient-blip protection at 5-min
cadence). The escalation check passes debounce_default=1: its escalation state is
already durable in the findings_log row itself, so a real escalation MUST emit on
the first cycle — but its 3 steady-state INFO lines (every 15 min, forever, into a
table Rule T-LOG.3 forbids ever pruning) must not.

Retention is never the answer to log volume (T-LOG.3) — emitting less is.
"""

from __future__ import annotations

import json
import os

from log_finding import Finding, state_dir


def load_state(name: str) -> dict:
    """Read <state_dir>/<name>; {} if absent or corrupt (fail open — a lost state
    file costs at most one cycle of duplicate INFO, never a missed alert)."""
    try:
        with open(os.path.join(state_dir(), name)) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(name: str, state: dict) -> None:
    """Atomic write (tmp + os.replace) so a crash mid-write cannot corrupt it."""
    path = os.path.join(state_dir(), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)


def finding_key(f: Finding) -> str:
    """Stable per-check identity: the summary up to the first ':'."""
    return f.summary.split(":", 1)[0].strip()


def throttle(
    raw: list[Finding],
    state: dict,
    now_ts: float,
    *,
    debounce: dict[str, int] | None = None,
    debounce_default: int = 2,
    allclear_every_sec: int = 3600,
    allclear_summary=None,
    recovered_summary=None,
) -> tuple[list[Finding], dict]:
    """Returns (emitted_findings, new_state).

    `debounce` maps a finding key to its consecutive-failure threshold;
    `debounce_default` applies to keys not in the map. A threshold of 1 means a
    WARNING/CRITICAL emits on its first failing cycle — never downgraded, never
    suppressed. `debounce_default < 1` is rejected (it would suppress real
    failures entirely).

    `allclear_summary(n_checks) -> str` and `recovered_summary(key) -> str` let
    each caller word its own INFO lines; pass None to omit the all-clear.
    """
    if debounce_default < 1:
        raise ValueError("debounce_default < 1 would suppress a real failure entirely")
    debounce = debounce or {}
    counters = state.get("fail_counters", {})
    last_status = state.get("last_status", {})
    last_allclear = state.get("last_allclear", 0)
    new_counters: dict[str, int] = {}
    new_status: dict[str, str] = {}
    emitted: list[Finding] = []

    all_ok = True
    for f in raw:
        k = finding_key(f)
        failing = f.severity in ("warning", "critical")
        prev = last_status.get(k, "info")
        if failing:
            all_ok = False
            n = counters.get(k, 0) + 1
            new_counters[k] = n
            threshold = debounce.get(k, debounce_default)
            if n >= threshold:
                emitted.append(f)
                new_status[k] = f.severity
            else:
                # still within grace — surface as INFO, note the pending failure
                emitted.append(Finding("finding", "info",
                                       f"{f.summary} (debounce {n}/{threshold})"))
                new_status[k] = "info"
        else:
            new_counters[k] = 0
            new_status[k] = "info"
            if prev in ("warning", "critical"):
                msg = recovered_summary(k) if recovered_summary else f"{k}: recovered"
                emitted.append(Finding("finding", "info", msg))

    # one hourly all-clear roll-up
    if all_ok and (now_ts - last_allclear) >= allclear_every_sec:
        if allclear_summary:
            emitted.append(Finding("finding", "info", allclear_summary(len(raw))))
        last_allclear = now_ts

    new_state = {
        "fail_counters": new_counters,
        "last_status": new_status,
        "last_allclear": last_allclear,
        "last_run": now_ts,
    }
    return emitted, new_state
