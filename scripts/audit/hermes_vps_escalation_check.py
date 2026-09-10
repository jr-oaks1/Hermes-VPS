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

Exit codes (S19b): 0 = the check ran to completion (escalations found or not),
2 = the check could not run (findings_log unreachable / env missing). A CEO-band
escalation is NOT a non-zero exit — a oneshot that exits 1 becomes a `failed`
unit, the Tier 3 guardrail then alarms on that failed unit, this check then
escalates the guardrail's CRITICAL, and both units are wedged `failed` forever
(the 2026-09-08 → 2026-09-10 deadlock, ~39k rows). Escalation state is durable
in the findings_log row itself (T4.3); the exit code carries none of it.

S19b also makes each escalating row emit ONCE per band crossing (gated on the
row's escalated_gm_at / escalated_ceo_at latch), not once every 15-min cycle —
the per-cycle re-emission was the bulk of the storm volume.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_SCRIPT_DIR))          # repo/scripts
sys.path.insert(0, _SCRIPT_DIR)                            # repo/scripts/audit

from log_finding import (  # noqa: E402
    Finding, log_findings, open_critical, mark_escalated, state_dir,
    settled_without_triage,
)
from emission_state import load_state, save_state, throttle  # noqa: E402

_GM_ESCALATE_AFTER = timedelta(hours=2)     # T4.1
_CEO_ESCALATE_AFTER = timedelta(hours=24)   # T4.2
_LOOKBACK = timedelta(days=3)               # query window > CEO threshold + margin

_HEARTBEAT_WARN_AFTER = timedelta(minutes=20)
_HEARTBEAT_CRIT_AFTER = timedelta(minutes=60)

# S18: this check runs every 15 min and emitted 3 INFO rows EVERY cycle (288/day)
# into a table Rule T-LOG.3 forbids ever pruning. It now shares the guardrail's
# emission gate (scripts/emission_state.py). debounce_default=1 → a real escalation
# still emits on its first failing cycle; only steady-state INFO is throttled.
_STATE_FILE = "escalation_state.json"
_ALLCLEAR_EVERY_SEC = 3600

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


def queue_integrity_finding(untriaged: list[dict]) -> Finding:
    """Pure: turn the settled_without_triage() result into one Finding.

    deploy/sql/S17_findings_log_tier4.sql retro-closed every open row older than
    7 days regardless of severity, silently emptying this ladder. A WARNING/
    CRITICAL row in 'no_action_needed' must carry an explicit human 'triage:'
    note (deploy/sql/S51_findings_log_severity_triage.sql), never be swept there
    by a bulk UPDATE. key prefix 'queue-integrity' so the emission gate reads
    its recovery independently of the 'escalation:' alerts.
    """
    if not untriaged:
        return Finding("finding", "info",
                       "queue-integrity: all settled WARNING/CRITICAL rows carry a triage stamp")
    ids = ", ".join(f"#{r['id']}" for r in untriaged[:10])
    more = f" (+{len(untriaged) - 10} more)" if len(untriaged) > 10 else ""
    return Finding(
        "finding", "warning",
        f"queue-integrity: {len(untriaged)} WARNING/CRITICAL row(s) settled without a triage stamp",
        detail=(f"ids {ids}{more} are action_status='no_action_needed' with no 'triage:' note in "
                f"detail — likely swept by a bulk UPDATE. Review and stamp each, or re-open. "
                f"See deploy/sql/S51_findings_log_severity_triage.sql for the pattern."),
    )


def _fmt_age(age: timedelta) -> str:
    h = age.total_seconds() / 3600
    if h < 48:
        return f"{h:.1f}h"
    return f"{h / 24:.1f}d"


def classify_escalations(rows: list[dict], now: datetime) -> list[tuple[dict, dict]]:
    """Returns list of (row, classification). One entry per row, always."""
    return [(row, classify_row(row, now)) for row in rows]


def is_first_band_crossing(row: dict, band: str) -> bool:
    """S19b: True the first time a row reaches `band` ('gm'|'ceo'), i.e. its
    escalated_<band>_at latch is still NULL. A row already latched at its current
    band is silent — the latch column IS the durable notification record (T4.3),
    and re-emitting a Finding every 15-min cycle is what turned 2 stuck rows into
    ~37k findings_log rows over 2026-09-08 → 2026-09-10.
    """
    if band == "gm":
        return row.get("escalated_gm_at") is None
    if band == "ceo":
        return row.get("escalated_ceo_at") is None
    return False


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

def run(dry_run: bool = False) -> int:
    db_url = os.environ.get("HERMES_VPS_LOG_DB_URL", "")
    if not db_url:
        if not dry_run:
            log_findings([Finding("error", "critical",
                                  "escalation: HERMES_VPS_LOG_DB_URL not set — Tier 4 cannot run")],
                         session_ref=SESSION_REF)
        else:
            print("escalation: HERMES_VPS_LOG_DB_URL not set — Tier 4 cannot run")
        return 2

    now = datetime.now(timezone.utc)
    findings: list[Finding] = []

    # --- Tier 4 escalation ladder ---
    try:
        rows = open_critical(db_url, now - _LOOKBACK)
    except Exception as e:  # noqa: BLE001
        # A Tier 4 check that cannot read its own state must be as loud as a failure.
        if not dry_run:
            log_findings([Finding("error", "critical",
                                  "escalation: cannot reach findings_log", detail=str(e))],
                         session_ref=SESSION_REF)
        else:
            print(f"escalation: cannot reach findings_log — {e}")
        return 2

    if not rows:
        findings.append(Finding("finding", "info", "escalation: no unresolved CRITICAL findings"))
    else:
        below = already_gm = already_ceo = 0
        for row, cls in classify_escalations(rows, now):
            band = cls["band"]
            if band == "none":
                below += 1
                continue
            # S19b: emit ONLY on the first crossing into a band (see
            # is_first_band_crossing). A row already notified at its current band
            # is counted into an INFO roll-up, never re-paged.
            if not is_first_band_crossing(row, band):
                if band == "ceo":
                    already_ceo += 1
                else:
                    already_gm += 1
                continue
            # First crossing → one derived notification row. NOT a work item:
            # the underlying finding #row['id'] carries the real action_status,
            # so this enters already-settled and tagged, and open_critical()
            # excludes this check's own session_ref — double protection against
            # the check re-escalating its own output (the nested
            # "CEO ESCALATION ... 'CEO ESCALATION ...'" rows in the storm).
            findings.append(Finding(
                "alert", cls["level"], cls["message"],
                detail=f"[meta: derived Tier 4 {band.upper()}-band notification for finding #{row['id']}]",
                owner_project=row.get("owner_project"),
                action_status="no_action_needed",
            ))
            # Latch + mirror once per band crossing. Skipped in --dry-run
            # (mark_escalated writes the DB; _mirror_to_gm_ladder shells out to
            # the GM's script and writes vps_orchestrator_findings).
            if not dry_run:
                try:
                    mark_escalated(db_url, row["id"], "gm")
                    if band == "ceo":
                        mark_escalated(db_url, row["id"], "ceo")
                except Exception as e:  # noqa: BLE001
                    findings.append(Finding("error", "warning",
                                            f"escalation: could not latch escalation for #{row['id']}",
                                            detail=str(e)))
                findings.extend(_mirror_to_gm_ladder(row, cls["message"]))
        # One INFO summary line each for the below-threshold and the
        # already-notified criticals, never one per row (S17 smoke test: per-row
        # INFO every 15 min is a slow feedback loop). Distinct key prefixes so the
        # emission gate never reads them as a recovery of an active 'escalation:'
        # alert.
        if below:
            findings.append(Finding("finding", "info",
                                    f"escalation.subthreshold: {below} open critical(s) below the 2h GM threshold"))
        if already_gm or already_ceo:
            findings.append(Finding("finding", "info",
                                    f"escalation.notified: {already_gm} GM-band + {already_ceo} CEO-band "
                                    f"row(s) already latched — no re-page"))

    # --- T3.10 heartbeat staleness ---
    timer_enabled = _timer_enabled("hermes-vps-guardrail.timer")
    findings.extend(check_guardrail_heartbeat(now, timer_enabled=timer_enabled))

    # --- T-LOG.2 reconciliation ---
    try:
        from hermes_vps_reconcile import reconcile
        findings.extend(reconcile(db_url, window_hours=24))
    except Exception as e:  # noqa: BLE001
        findings.append(Finding("error", "warning", "reconcile: check raised", detail=str(e)))

    # --- Tier 4 queue integrity: no WARNING/CRITICAL row may sit settled
    # without an explicit human triage stamp (S51). A bulk age-based UPDATE
    # -- deploy/sql/S17_findings_log_tier4.sql did exactly this -- silently
    # emptied this very ladder; catch a repeat between deploys, not only at
    # deploy time (deploy_guardrail.sh step 7b). key prefix 'queue-integrity'
    # so the emission gate reads its recovery independently.
    try:
        findings.append(queue_integrity_finding(settled_without_triage(db_url)))
    except Exception as e:  # noqa: BLE001
        findings.append(Finding("error", "warning", "queue-integrity: check raised", detail=str(e)))

    # --- S18 emission gate: state-change INFO + one hourly all-clear only ---
    # WARNING/CRITICAL still emit on the first failing cycle (debounce_default=1);
    # this only suppresses the 3 steady-state INFO lines that ran 96×/day.
    now_ts = now.timestamp()
    if dry_run:
        print("--- DRY RUN — no writes (DB, Telegram, state, latch, GM mirror) ---")
        for f in findings:
            print(f"  [{f.severity.upper():8}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))
        state = load_state(_STATE_FILE)
        emitted, _ = throttle(findings, state, now_ts, debounce_default=1,
                              allclear_every_sec=_ALLCLEAR_EVERY_SEC,
                              allclear_summary=lambda n: f"escalation: all {n} checks nominal",
                              recovered_summary=lambda k: f"{k}: cleared")
        print(f"\nwould emit {len(emitted)} of {len(findings)} finding(s) after the gate")
        return 0

    state = load_state(_STATE_FILE)
    emitted, new_state = throttle(
        findings, state, now_ts,
        debounce_default=1,
        allclear_every_sec=_ALLCLEAR_EVERY_SEC,
        allclear_summary=lambda n: f"escalation: all {n} checks nominal",
        recovered_summary=lambda k: f"{k}: cleared",
    )

    log_findings(emitted, session_ref=SESSION_REF,
                 header="🛡️ Tier 4 escalation + guardrail heartbeat + T-LOG.2 reconcile")
    save_state(_STATE_FILE, new_state)

    for f in emitted:
        print(f"[{f.severity.upper()}] {f.summary}" + (f" — {f.detail}" if f.detail else ""))

    # S19b: exit 0 whenever the check completed. CEO-band state is durable in the
    # findings_log row (escalated_ceo_at); the exit code must not turn this
    # oneshot into a `failed` unit that the Tier 3 guardrail then alarms on.
    return 0


def _timer_enabled(unit: str) -> bool | None:
    try:
        r = subprocess.run(["systemctl", "is-enabled", unit],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "enabled"
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tier 4 durable escalation ladder + heartbeat + reconcile")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + reconcile read-only; write nothing (DB/Telegram/state/latch/GM mirror)")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run))
