# Cross-Project Notice: log findings as they're found (Continuous Improvement Standard §5f)

**From:** JR Hermes Ingestor (S29, 2026-09-04)
**To:** All projects
**Issue:** New standing practice added to `CONTINUOUS_IMPROVEMENT_STANDARD.md` (workspace
root, §5f, Rule T-LOG.1) — every finding, error, or observation discovered during live
work (deploys, audits, incident response, ad-hoc investigation) should be dual-logged to
the project's queryable findings log **and** its findings Telegram bot **at the moment
it's found**, not batched into an end-of-session write-up.

**Why:** A finding that only exists in a session transcript or a handoff's prose is
invisible to `findings_log`-driven tooling (Tier 4 escalation, the GM's monthly
synthesis, cross-project audits) until someone manually transcribes it. Logging as-you-go
closes that gap. This was adopted this session at the user's explicit request, after
JR Hermes Ingestor used its existing `scripts/log_finding.py` (built S161, not
consistently used until now) live during deploy/audit work for the first time.

**Reference implementation:** `JR Hermes Ingestor/scripts/log_finding.py` — dual-writes
one row to `findings_log` and one Telegram message to the project's dedicated findings
bot in a single call:
```bash
python scripts/log_finding.py --category finding|error|note|alert \
    --severity info|warning|critical \
    --summary "Short summary" --detail "Optional longer detail" --session S{N}
```

**Action:** If your project has a `findings_log`-equivalent table and a findings
Telegram bot (per `HERMES_PLATFORM_STANDARD.md` R6), adopt an equivalent script and use
it during live work going forward, rather than writing findings only into the session
handoff. If your project doesn't yet have a queryable findings log, this is not a
requirement to build one right now — treat it as guidance for when Tier 3/4 work
reaches your project, per `CONTINUOUS_IMPROVEMENT_STANDARD.md`'s existing rollout order.

No code, schema, or infrastructure in your project was touched by this notice — it's
process guidance only. Full detail: `JR Hermes Ingestor/docs/sessions/S29-HANDOFF.md`.
