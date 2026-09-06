#!/usr/bin/env python3
"""
scripts/audit/hermes_vps_escalation_check.py — Tier 4 durable escalation (S17)

Rules T4.1-T4.3 (CONTINUOUS_IMPROVEMENT_STANDARD.md §5c), over this project's
OWN findings log (hermes_vps_log.findings_log):

  T4.1 — a CRITICAL unacknowledged > 2h  escalates to the GM band.
  T4.2 — a CRITICAL unacknowledged > 24h escalates to the CEO band.
  T4.3 — escalation state lives in the findings_log row itself (ts + action_status),
         re-derived every cycle, NOT in this process. A reboot, a crashed timer,
         or this script dying changes nothing about what the next run reports.

Ported from JR_VPS_Orchestrators/src/collector/checks/escalation_check.py, made
synchronous and standalone (this repo has no collector / Event / async loop).
The `due()` throttle is dropped — the systemd timer IS the throttle, which is
strictly more durable than an in-process gate.

ROUTING (see docs/sessions/S17-HANDOFF.md §3d): HERMES_PLATFORM_STANDARD R4
forbids using another project's bot token, so this ladder never sends to
@JRCleviousVPSBot or a CEO channel directly. All output goes to this project's
own @JRHermesVPSBot with the band named in the text. GM/CEO PAGING remains the
GM's existing EscalationCheck over vps_orchestrator_findings — we feed that
ladder by mirroring GM-band criticals (once) into the unified DB via the GM's
own log_operational_finding.py. No double-paging: two DBs, two bots, two
audiences.

Also folded in (reusing the 15-min cadence rather than adding units):
  - heartbeat staleness for the Tier 3 guardrail (T3.10 — "a guardrail that
    cannot run must be as loud as one that fails")
  - the T-LOG.2 reconciliation check (hermes_vps_reconcile.reconcile)

Env: HERMES_VPS_LOG_DB_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
     FINDINGS_DB_URL (optional — unified-DB mirror; if unset, GM ladder is fed
     only by the health check and that gap is itself reported).
Exit codes: 0 = no CEO-band escalation, 1 = at least one CEO-band escalation, 2 = error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))          # repo/scripts
sys.path.insert(0, _SCRIPT_DIR)                            # repo/scripts/audit

from log_finding import (  # noqa: E402
    Finding, log_findings, open_critical, mark_escalated, state_dir,
)

_GM_ESCALATE_AFTER = timedelta(hours=2)     # T4.1
_CEO_ESCALATE_AFTER = timedelta(hours=24)   # T4.2
_LOOKBACK = timedelta(days=3)               # query window > CEO threshold + margin

_HEARTBEAT_WARN_AFTER = timedelta(minutes=20)
_HEARTBEAT_CRIT_AFTER = timedelta(minutes=60)

_GM_MIRROR = "/opt/jrvps-orchestrator/scripts/log_operational_finding.py"
_VENV_PY = "/opt/hermes-vps/.venv/bin/python3"

SESSION_REF = f"vps-escalation-{datetime.now(timezone.utc):%Y%m%d}"


# --------------------------------------------------------------------------- #
# Pure classification — no I/O, unit-tested directly
# --------------------------------------------------------------------------- #

def classify_row(row: dict, now: datetime) -> dict:
    """Given a findings_log row, return {level, message, band} where band is one
    of 'none' | 'gm' | 'ceo'. State is derived purely from row['ts'] and
    row['action_status'] — nothing cached."""
    ts = row["ts"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = now - ts
    fid = row["id"]
    summary = row["summary"]
    action_status = row.get("action_status", "open")
    owner = row.get("owner_project")

    # S71: a finding claimed (in_progress) AND attributed to an owner is being
    # worked — keep the GM informed, stop paging the CEO, regardless of age.
    # in_progress with NO owner does not get this relief.
    owned_and_in_progress = action_status == "in_progress" and bool(owner)

    if age < _GM_ESCALATE_AFTER:
        return {
            "level": "info",
            "band": "none",
            "message": f"escalation: finding #{fid} open {_fmt_age(age)}, below GM threshold — \"{summary}\"",
        }

    if owned_and_in_progress:
        return {
            "level": "warning",
            "band": "gm",
            "message": (f"escalation: GM escalation — finding #{fid} in progress {_fmt_age(age)}, "
                        f"owned by {owner} — \"{summary}\""),
        }

    if age >= _CEO_ESCALATE_AFTER:
        return {
            "level": "critical",
            "band": "ceo",
            "message": (f"escalation: CEO ESCALATION (mirrored to GM ladder for CEO routing) — "
                        f"finding #{fid} unresolved for {_fmt_age(age)} — \"{summary}\""),
        }

    return {
        "level": "warning",
        "band": "gm",
        "message": f"escalation: GM escalation — finding #{fid} unresolved for {_fmt_age(age)} — \"{summary}\"",
    }


def _fmt_age(age: timedelta) -> str:
    h = age.total_seconds() / 3600
    if h < 48:
        return f"{h:.1f}h"
    return f"{h / 24:.1f}d"


def classify_escalations(rows: list[dict], now: datetime) -> list[tuple[dict, dict]]:
    """Returns list of (row, classification). One entry per row, always."""
    return [(row, classify_row(row, now)) for row in rows]


# --------------------------------------------------------------------------- #
# Heartbeat staleness (T3.10)
# --------------------------------------------------------------------------- #

def check_guardrail_heartbeat(now: datetime, *, timer_enabled: bool | None = None) -> list[Finding]:
    path = os.path.join(state_dir(), "guardrail.heartbeat")
    if not os.path.exists(path):
        if timer_enabled is False:
            return [Finding("finding", "info", "guardrail.heartbeat: absent, timer not enabled")]
        # S71: deployed-but-not-yet-past-first-run grades warning, not critical.
        return [Finding("finding", "warning",
                        "guardrail.heartbeat: missing — Tier 3 guardrail has not written a success heartbeat")]
    age = now - datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    if age >= _HEARTBEAT_CRIT_AFTER:
        return [Finding("finding", "critical",
                        f"guardrail.heartbeat: stale {_fmt_age(age)} — Tier 3 guardrail is not running")]
    if age >= _HEARTBEAT_WARN_AFTER:
        return [Finding("finding", "warning",
                        f"guardrail.heartbeat: stale {_fmt_age(age)}")]
    return [Finding("finding", "info", f"guardrail.heartbeat: fresh ({_fmt_age(age)})")]


# --------------------------------------------------------------------------- #
# Unified-DB mirror (feeds the GM's own EscalationCheck / CEO ladder)
# --------------------------------------------------------------------------- #

def _mirror_to_gm_ladder(row: dict, message: str) -> list[Finding]:
    """Mirror a GM-band critical into vps_orchestrator_findings via the GM's own
    script, so the GM's EscalationCheck owns CEO routing from there. Best-effort;
    a failure is itself a finding, never a silent stderr line."""
    if not os.environ.get("FINDINGS_DB_URL"):
        return [Finding("finding", "warning",
                        "escalation: FINDINGS_DB_URL unset — cannot mirror to GM ladder",
                        detail=f"finding #{row['id']} would not reach the GM's EscalationCheck / CEO routing")]
    if not os.path.exists(_GM_MIRROR):
        return [Finding("finding", "warning",
                        f"escalation: GM mirror script missing at {_GM_MIRROR}")]
    cmd = [
        _VENV_PY, _GM_MIRROR,
        "--source_project", "JR Hermes VPS",
        "--severity", "critical", "--category", "alert",
        "--summary", message[:400],
        "--session", SESSION_REF,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return [Finding("finding", "warning",
                            f"escalation: GM mirror exited rc={r.returncode}",
                            detail=(r.stderr or r.stdout)[:400])]
    except Exception as e:  # noqa: BLE001
        return [Finding("finding", "warning", "escalation: GM mirror raised", detail=str(e))]
    return []


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

def run() -> int:
    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    if not db_url:
        log_findings([Finding("error", "critical",
                              "escalation: HERMES_VPS_LOG_DB_URL not set — Tier 4 cannot run")],
                     session_ref=SESSION_REF)
        return 2

    now = datetime.now(timezone.utc)
    findings: list[Finding] = []
    ceo_band = False

    # --- Tier 4 escalation ladder ---
    try:
        rows = open_critical(db_url, now - _LOOKBACK)
    except Exception as e:  # noqa: BLE001
        # A Tier 4 check that cannot read its own state must be as loud as a failure.
        log_findings([Finding("error", "critical",
                              "escalation: cannot reach findings_log", detail=str(e))],
                     session_ref=SESSION_REF)
        return 2

    if not rows:
        findings.append(Finding("finding", "info", "escalation: no unresolved CRITICAL findings"))
    else:
        below = 0
        for row, cls in classify_escalations(rows, now):
            if cls["band"] == "none":
                below += 1
                continue
            # GM / CEO band: one finding per row (real, actionable, latched).
            findings.append(Finding(
                "alert", cls["level"], cls["message"],
                owner_project=row.get("owner_project"),
            ))
            if cls["band"] == "ceo":
                ceo_band = True
            # Latch + mirror once per band crossing.
            if row.get("escalated_gm_at") is None:
                try:
                    mark_escalated(db_url, row["id"], "gm")
                except Exception as e:  # noqa: BLE001
                    findings.append(Finding("error", "warning",
                                            f"escalation: could not latch escalated_gm_at for #{row['id']}",
                                            detail=str(e)))
                findings.extend(_mirror_to_gm_ladder(row, cls["message"]))
            if cls["band"] == "ceo" and row.get("escalated_ceo_at") is None:
                try:
                    mark_escalated(db_url, row["id"], "ceo")
                except Exception:  # noqa: BLE001
                    pass
        # One summary line for the below-threshold criticals, never one each
        # (S17 smoke test: per-row INFO every 15 min is a slow feedback loop).
        if below:
            findings.append(Finding("finding", "info",
                                    f"escalation: {below} open critical(s) below the 2h GM threshold"))

    # --- T3.10 heartbeat staleness ---
    timer_enabled = _timer_enabled("hermes-vps-guardrail.timer")
    findings.extend(check_guardrail_heartbeat(now, timer_enabled=timer_enabled))

    # --- T-LOG.2 reconciliation ---
    try:
        from hermes_vps_reconcile import reconcile
        findings.extend(reconcile(db_url, window_hours=24))
    except Exception as e:  # noqa: BLE001
        findings.append(Finding("error", "warning", "reconcile: check raised", detail=str(e)))

    log_findings(findings, session_ref=SESSION_REF,
                 header="🛡️ Tier 4 escalation + guardrail heartbeat + T-LOG.2 reconcile")

    for f in findings:
        print(f"[{f.severity.upper()}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))

    return 1 if ceo_band else 0


def _timer_enabled(unit: str) -> bool | None:
    try:
        r = subprocess.run(["systemctl", "is-enabled", unit],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "enabled"
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    sys.exit(run())
