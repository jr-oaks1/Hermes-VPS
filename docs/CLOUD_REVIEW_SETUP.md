# JR Hermes VPS — Cloud-Review Routine Setup

**Date Created:** 2026-08-22  
**Status:** Ready for RemoteTrigger scheduling (two routines, weekly + monthly)  
**Model:** claude-sonnet-5  
**Repository:** `jr-oaks1/Hermes-VPS`  

---

## Overview

Cloud-review routines are automated agents (via RemoteTrigger) that:
1. Read the weekly/monthly findings export from `docs/findings_export/latest.json`
2. Diagnose issues and patterns
3. Open pull requests for code-only fixes; flag infra-touching items for manual review
4. Write detailed reports to `docs/findings_export/reviews/`

The export infrastructure is already in place (`hermes_vps_health_check.py`); this document describes the cloud-side scheduling.

---

## Routine 1: Weekly Findings Triage

**Schedule:** Sundays 06:00 UTC (8-day window)  
**Trigger ID:** (To be assigned by RemoteTrigger)  
**Cron:** `0 6 * * 0`  

### Responsibilities

1. **Read findings:** Load `docs/findings_export/latest.json` from git (8-day window, populated by Sunday 04:00 health-check)
2. **Diagnose:** Classify findings by severity (critical, warning, info)
3. **Code-only fixes:** Open PR for any fixes that touch only app code (not infra)
4. **Infra-touching:** Flag for manual review (cannot auto-fix nginx, Prometheus, firewall, DB)
5. **Write report:** Create `docs/findings_export/reviews/weekly-{YYYYMMDD-HHmm}.md`

### Report Structure

```markdown
# JR Hermes VPS — Weekly Findings Triage ({date})

**Window:** 8 days (most recent health-check cycle)  
**Run:** {execution timestamp}  
**Agent:** Cloud-review routine (claude-sonnet-5)  

## Summary
- Critical findings: X
- Warnings: Y
- Info: Z

## Code-Only Fixes (Auto-PR Opened)
- Item 1: [PR link] {description}
- Item 2: [PR link] {description}

## Infra-Touching Items (Manual Review Required)
- Item 1: {description, why manual}
- Item 2: {description, why manual}

## Recommendations
{Additional guidance for next steps}
```

### Tools Allowed
- Bash (git clone, git push, gh CLI for PR creation)
- Read (findings_export/, health-check logs)
- Write (findings_export/reviews/)
- Edit (if PR content needs refinement)
- Glob, Grep (search code for related issues)

### Example Prompt

```
You are a cloud-review agent for JR Hermes VPS infrastructure.

Your job: Read the weekly findings export, diagnose issues, and take action.

Steps:
1. Clone/read the latest https://github.com/jr-oaks1/Hermes-VPS repo
2. Load docs/findings_export/latest.json (quick mode, 8-day window)
3. For each finding:
   - If code-only fix possible: open PR with fix
   - If infra-touching: document for manual follow-up
4. Write report to docs/findings_export/reviews/weekly-{timestamp}.md
5. Push report to main branch

Constraints:
- Never push code fixes directly to main (always PR)
- Never touch infra config (nginx, Prometheus, firewall, DB)
- If in doubt, flag for manual review
```

---

## Routine 2: Monthly Deep Review

**Schedule:** 1st of month, 06:00 UTC (35-day window)  
**Trigger ID:** (To be assigned by RemoteTrigger)  
**Cron:** `0 6 1 * *`  

### Responsibilities

1. **Read findings:** Load `docs/findings_export/latest.json` (35-day window, full month)
2. **Analyze patterns:** Identify recurring issues, trends, optimization opportunities
3. **Tech-debt:** Suggest refactoring, modernization, hardening
4. **Separate PR:** Open dedicated PR (distinct from weekly code-fix PR)
5. **Preemptive hardening:** Add tests, guards, documentation
6. **Write report:** Create `docs/findings_export/reviews/monthly-{YYYYMM}.md`

### Report Structure

```markdown
# JR Hermes VPS — Monthly Deep Review ({month})

**Window:** 35 days (full month)  
**Run:** {execution timestamp}  
**Agent:** Cloud-review routine (claude-sonnet-5)  

## Summary
- Total findings processed: X
- Recurring patterns: Y
- Tech-debt items: Z

## Recurring Issues
- Issue 1: {description, frequency, impact}
- Issue 2: {description, frequency, impact}

## Tech-Debt Improvements (PR Opened)
- Item 1: [PR link] {description}
- Item 2: [PR link] {description}

## Recommended Hardening
- Test addition for: {area}
- Documentation update for: {area}
- Monitoring enhancement for: {area}

## Next Month Focus
{Anticipated areas to watch}
```

### Tools Allowed
- Bash, Read, Write, Edit, Glob, Grep (same as weekly)
- Plus: ability to add tests/documentation to PRs

### Example Prompt

```
You are a cloud-review agent for JR Hermes VPS infrastructure.

Your job: Perform deep analysis of 35-day findings history and recommend improvements.

Steps:
1. Clone/read https://github.com/jr-oaks1/Hermes-VPS repo
2. Load docs/findings_export/latest.json (deep mode, 35-day window)
3. Analyze for:
   - Recurring issues (>1 occurrence in window)
   - Tech-debt patterns (areas needing refactoring)
   - Optimization opportunities
4. Open PR with:
   - Code improvements
   - New tests for fragile areas
   - Documentation updates
5. Write comprehensive report to docs/findings_export/reviews/monthly-{timestamp}.md
6. Push report + PR

Constraints:
- Open PR for improvements (code-only; no infra config)
- If infra change needed: document in PR description for manual review
- Focus on systemic improvements, not one-off fixes
```

---

## Scheduling via RemoteTrigger

### Option A: Use Anthropic API (Programmatic)

If `RemoteTrigger` tool is available in Claude Code, create routines with:

```python
# Pseudo-code example
from anthropic_sdk import RemoteTrigger

weekly = RemoteTrigger.create(
    name="hermes-vps-weekly-findings-triage",
    repository="jr-oaks1/Hermes-VPS",
    cron_schedule="0 6 * * 0",  # Sundays 06:00 UTC
    model="claude-sonnet-5",
    prompt="""[weekly prompt from section above]""",
    allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
)

monthly = RemoteTrigger.create(
    name="hermes-vps-monthly-deep-review",
    repository="jr-oaks1/Hermes-VPS",
    cron_schedule="0 6 1 * *",  # 1st of month 06:00 UTC
    model="claude-sonnet-5",
    prompt="""[monthly prompt from section above]""",
    allowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
)
```

### Option B: Manual Setup (Via Web UI or CLI)

1. Navigate to cloud-review scheduling dashboard (internal tool)
2. Create new routine:
   - Name: `hermes-vps-weekly-findings-triage`
   - Repository: `jr-oaks1/Hermes-VPS`
   - Cron: `0 6 * * 0`
   - Model: `claude-sonnet-5`
   - Paste prompt from section above
   - Allowed tools: Bash, Read, Write, Edit, Glob, Grep
3. Repeat for monthly routine (`0 6 1 * *`)

### Option C: Configuration File (If Supported)

Create `docs/remote-triggers.yaml` (checked into git):

```yaml
cloud_review_routines:
  - name: weekly-findings-triage
    schedule: "0 6 * * 0"
    model: claude-sonnet-5
    repository: jr-oaks1/Hermes-VPS
    tools: [Bash, Read, Write, Edit, Glob, Grep]
    prompt_file: docs/cloud-review-prompts/weekly-triage.md
    reports_dir: docs/findings_export/reviews/

  - name: monthly-deep-review
    schedule: "0 6 1 * *"
    model: claude-sonnet-5
    repository: jr-oaks1/Hermes-VPS
    tools: [Bash, Read, Write, Edit, Glob, Grep]
    prompt_file: docs/cloud-review-prompts/monthly-deep.md
    reports_dir: docs/findings_export/reviews/
```

Then deploy with: `cloud-review-deploy docs/remote-triggers.yaml`

---

## Verification & Testing

### Before Going Live

1. **Repo access:** RemoteTrigger can clone `jr-oaks1/Hermes-VPS` (public repo, no auth needed)
2. **Findings export:** Verify `docs/findings_export/latest.json` exists after manual health-check run
3. **Directory structure:** `docs/findings_export/reviews/` exists and is writable
4. **Model access:** claude-sonnet-5 available to remote agent (not deferred/auth-gated)

### Test Run (Optional)

Manually trigger one routine to validate:

```bash
cd /opt/hermes-vps
./.venv/bin/python3 scripts/audit/hermes_vps_health_check.py --mode quick
# Verify findings_export/latest.json created + pushed to git

# Then manually run the weekly-triage prompt (via Claude) to test
# Should generate weekly-{timestamp}.md report
```

### Monitoring

- Both routines log execution to RemoteTrigger dashboard
- Failed runs send alert to configured Telegram channel (via TELEGRAM_BOT_TOKEN)
- PRs are opened with `automated-review` label for easy filtering
- Check github.com/jr-oaks1/Hermes-VPS/pulls for new reviews weekly/monthly

---

## Cross-Project Alignment

**Parallel routines in hermes_v2:**
- Weekly findings triage (same logic, different repo)
- Monthly deep review (same logic, different repo)
- Both use identical schedule + model + tool set

**Key difference:** hermes_v2_log findings vs. hermes_vps_log findings (different sources)

**Shared pattern:** Both export via git, both reviewed by cloud agents, both open PRs for fixes

---

## Rollback / Disable

If a routine misbehaves:

```bash
# Disable routine (keep config)
cloud-review-disable hermes-vps-weekly-findings-triage

# Re-enable when fixed
cloud-review-enable hermes-vps-weekly-findings-triage

# Delete entirely (if needed)
cloud-review-delete hermes-vps-weekly-findings-triage
```

---

## Next Steps (S2.2)

1. **Decide scheduling method:** Option A (API), B (web UI), or C (config file)
2. **Create routines:** Use method above to instantiate both weekly + monthly
3. **Test:** Manually trigger health-check; verify export; manually test prompt
4. **Verify:** Check PR queue and findings_export/reviews/ after first scheduled run

---

**Last Updated:** 2026-08-22 (S2)  
**Setup Status:** Ready for implementation  
**Blocking:** None (infrastructure already in place)
