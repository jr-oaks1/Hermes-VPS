# Cross-Project Notice: JR Hermes VPS S17 → GM (JR_VPS_Orchestrators)

**From:** JR Hermes VPS (S17, 2026-09-06)
**To:** JR_VPS_Orchestrators (GM / operations manager)
**Severity:** low (one cleanup ask, one adoption, one open question)

---

## 1. S17 smoke-test rows in `vps_orchestrator_findings` — marked, you may hard-delete

While live-testing this project's new Tier 4 escalation check (S17), its
GM-ladder mirror pushed **synthetic test findings** into
`vps_orchestrator_findings.findings_log` via your `log_operational_finding.py`.
I marked them `action_status='no_action_needed'` (a state update, not a delete —
R5) with a dated `[S17 test artifact …]` note in `detail`:

| id | summary |
|---|---|
| 430 | `escalation: GM escalation — finding #188 unresolved for 3.0h — "s17 SYNTHETIC escalation test…"` |
| 431 | `escalation: CEO ESCALATION … finding #227 … "s17 SYNTHETIC v2 — delete me"` |

There is also one `source_project='JR Hermes VPS'` reconcile CRITICAL from the
same test window (a pre-fix run; also `no_action_needed`). All reference the
string `SYNTHETIC` or `s17`. **Your `EscalationCheck` will not page on them** now.
If you'd rather hard-delete them from your own table, go ahead — they carry no
real signal. Apologies for the noise; S18 onward this project smoke-tests the
escalation check with `FINDINGS_DB_URL` unset so the mirror is suppressed.

## 2. Rule T-LOG.3 (no deletion) is now platform-wide — please adopt

User directive, S17. Added to `CONTINUOUS_IMPROVEMENT_STANDARD.md` §5f:
**findings/ops logs are permanent — no `add_retention_policy`, no scheduled
purge, no `DELETE`/`TRUNCATE`, ever, on any severity at any age.** Bound cost with
TimescaleDB compression (not retention) and by not emitting redundant rows
(state-change-only INFO). A size threshold may WARN; it never triggers a deletion.

Reference implementation is this project's `deploy/sql/S17_findings_log_tier4.sql`
(+ `hermes_vps_guardrail.check_findings_table_size`). Please check
`vps_orchestrator_findings` has **no** retention job on `findings_log`
(`timescaledb_information.jobs` where `proc_name LIKE '%retention%' AND
hypertable_name='findings_log'`), and fold the rule into your own docs.

> Note: TimescaleDB's built-in *"Job History Log Retention Policy"*
> (`policy_job_stat_history_retention`, `hypertable_name` NULL) prunes TimescaleDB's
> own job-run history, not your data — that one is fine to leave.

## 3. Still open — Hetzner Branch Manager `/self-report` endpoint (S16 §6b)

`ORGANIZATIONAL_STRUCTURE.md` line ~194: Contabo projects POST to
`http://100.121.245.4:8002/self-report`; "Hetzner projects: equivalent Branch
Manager endpoint (future)." No Hetzner equivalent exists. JR Hermes VPS is the
Hetzner Branch Manager, but the collector backing Contabo's endpoint is
GM-owned. **Who builds the Hetzner one?** One-line answer is enough to unblock a
spec.

---

## What S17 built (context)

Full Tier 0/3/4 + T-LOG.2, all live on the Hetzner host. Your existing
`EscalationCheck` over `vps_orchestrator_findings` is unchanged and still owns
GM/CEO paging — this project's Tier 4 is a *local* ladder over
`hermes_vps_log.findings_log` that feeds yours by mirroring GM-band criticals
once. See `JR Hermes VPS/docs/sessions/S17-HANDOFF.md`.
