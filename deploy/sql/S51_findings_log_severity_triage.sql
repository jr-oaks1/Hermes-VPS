-- ===================================================================== --
-- S51 (cross-project, run from Clevious VPS S51) / JR Hermes VPS
--   findings_log: individually triage the 26 WARNING/CRITICAL rows that
--   S17's severity-blind age backfill swept to 'no_action_needed'
-- ===================================================================== --
--
-- Run as a SUPERUSER against hermes_vps_log (runtime role hermes_vps is
-- not the table owner -- HERMES_PLATFORM_STANDARD R5; one-time, reversible):
--
--     sudo -u postgres psql -v ON_ERROR_STOP=1 -d hermes_vps_log \
--          -f deploy/sql/S51_findings_log_severity_triage.sql
--
-- Take a manual pg_dump first (R-RESTORE-4):
--     pg_dump -Fc hermes_vps_log \
--       > /opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s51.dump
--
-- WHY: deploy/sql/S17_findings_log_tier4.sql lines 54-57 ran
--     UPDATE findings_log SET action_status='no_action_needed'
--      WHERE ts < now() - interval '7 days' AND action_status='open';
-- age-based, NOT severity-filtered. It retro-closed every WARNING/CRITICAL
-- row older than 7 days along with the INFO rows it was meant for, plus a
-- second off-repo hand pass (see docs/sessions/S17-HANDOFF.md:94-100). Net
-- effect: the Tier 4 escalation ladder (log_finding.open_critical selects
-- action_status IN ('open','in_progress')) had an empty input set and
-- "0 open actionable findings" became a false all-clear.
--
-- This migration does NOT blindly re-open. Every one of the 26 rows was
-- reviewed live this session against present host state and confirmed
-- stale / false-positive / already-resolved (evidence per group below).
-- None is genuinely actionable, so all stay 'no_action_needed' -- but each
-- now carries an explicit '[S51 triage: <reason>]' stamp, which is the
-- marker the new guard (deploy_guardrail.sh step 7b +
-- log_finding.settled_without_triage) keys on: a WARNING/CRITICAL row may
-- sit in 'no_action_needed' ONLY with a human triage stamp, never swept
-- there by a bulk UPDATE again.
--
-- T-LOG.3: STATE UPDATE ONLY. No DELETE, no retention policy, no purge.
--
-- ROLLBACK (per R5):
--   UPDATE findings_log SET action_status='open'
--    WHERE detail LIKE '%[S51 triage:%' AND severity IN ('warning','critical');
--   (then strip the ' [S51 triage: ...]' suffix if desired)
-- ===================================================================== --

\set ON_ERROR_STOP on

\echo '== 0. Pre-flight: no compressed chunks (UPDATE on a compressed chunk fails) =='
SELECT count(*) AS compressed_chunks_MUST_BE_ZERO
  FROM timescaledb_information.chunks
 WHERE hypertable_name = 'findings_log' AND is_compressed;

\echo '== 1. Target rows BEFORE -- 26 WARNING/CRITICAL, all no_action_needed, none stamped =='
SELECT id, ts::date, severity, left(summary, 55) AS summary
  FROM findings_log
 WHERE severity IN ('warning','critical')
   AND action_status = 'no_action_needed'
   AND (detail IS NULL OR detail NOT LIKE '%[S51 triage:%')
 ORDER BY id;

\echo '== 2. Apply per-row triage reason (state stays no_action_needed; stamp appended) =='
BEGIN;

WITH triage(id, reason) AS (VALUES
  -- Group A: service.hermes_v2 false-positive. hermes_v2.service decommissioned
  -- 2026-08-26; removed from health_check SYSTEMD_SERVICES in S13. Not a real service.
  (105, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  (111, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  (124, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  (130, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  (143, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  (149, 'hermes_v2.service decommissioned 2026-08-26; dropped from SYSTEMD_SERVICES S13 - false positive, no such service'),
  -- Group B: api.health. fred_data=disabled is the intended steady state (benign
  -- since S13); the "ok"/"degraded" summary+critical severity is the health_check
  -- summary/severity bug (fixed this session). Live api.health = status ok,
  -- all agents healthy except fred_data:disabled, verified 2026-09-07.
  (108, 'api.health summary/severity bug (fixed S51); fred_data:disabled is intended steady state - live api.health ok 2026-09-07'),
  (114, 'transient 2026-09-01 agent degradation (cvd_ingestion/multitf_aggregation) since recovered + fred_data:disabled benign - live api.health ok 2026-09-07'),
  (127, 'api.health summary/severity bug (fixed S51); fred_data:disabled is intended steady state - live api.health ok 2026-09-07'),
  (133, 'api.health summary/severity bug (fixed S51); fred_data:disabled is intended steady state - live api.health ok 2026-09-07'),
  (146, 'api.health summary/severity bug (fixed S51); fred_data:disabled is intended steady state - live api.health ok 2026-09-07'),
  (152, 'api.health summary/severity bug (fixed S51); fred_data:disabled is intended steady state - live api.health ok 2026-09-07'),
  -- Group C: api.health transient boot state -- agents "starting" during a
  -- 2026-08-22 restart window; cleared within minutes.
  (13, 'transient boot state: agents starting during 2026-08-22 restart window - cleared same day, live api.health ok'),
  (19, 'transient boot state: agents starting during 2026-08-22 restart window - cleared same day, live api.health ok'),
  (25, 'transient boot state: agents starting during 2026-08-22 restart window - cleared same day, live api.health ok'),
  (96, 'transient boot state: onchain_data starting during 2026-08-26 restart window - cleared same day, live api.health ok'),
  -- Group D: psql auth failure during the S08 hermes_v2 credential rotation.
  -- Replication now streaming/async/0-byte lag, ingestion live -- verified 2026-09-07.
  (97, 'password auth failure during S08 hermes_v2 credential rotation - resolved; replication streaming/0 verified 2026-09-07'),
  (98, 'password auth failure during S08 hermes_v2 credential rotation - resolved; ingestion live, replication streaming/0 verified 2026-09-07'),
  -- Group E: git-divergence findings from before S13 made export_hermes_vps_findings
  -- self-healing (_sync_repo_to_origin + push-rollback). Both clones reconciled S13.
  (122, 'pre-S13 git-divergence finding; findings-export made self-healing S13, both /opt clones reconciled - root cause fixed'),
  (123, 'pre-S13 git-divergence finding; findings-export made self-healing S13, both /opt clones reconciled - root cause fixed'),
  (141, 'pre-S13 git-divergence finding; findings-export made self-healing S13, both /opt clones reconciled - root cause fixed'),
  (142, 'pre-S13 git-divergence finding; findings-export made self-healing S13, both /opt clones reconciled - root cause fixed'),
  -- Group F: one-offs, each resolved in the same session it was found.
  (5,  'findings_log infrastructure gap - RESOLVED same session (S17 built hermes_vps_log DB + findings_log table + hermes_vps_writer role)'),
  (30, 'backups.hermes_vps_log had no dump yet at first run - dumps now present (daily + manual/), /etc/pg_backup.conf registered, verified 2026-09-07'),
  -- Group G: hermes_v2 application data staleness -- non-blocking, and the app that
  -- owned that table was decommissioned 2026-08-26.
  (4,  'hermes_v2 ohlcv_1m deprecated-symbol staleness, explicitly non-blocking (S79-era); hermes_v2 app decommissioned 2026-08-26'),
  -- Group H: S17 smoke-test synthetic artifact.
  (239, 'reconcile orphan_telegram from S17 SYNTHETIC test rows; synthetic rows cleaned same session, live reconcile orphan_telegram=0')
)
UPDATE findings_log f
   SET detail = coalesce(f.detail, '') || ' [S51 triage: ' || t.reason || ']'
  FROM triage t
 WHERE f.id = t.id
   AND f.severity IN ('warning','critical')
   AND f.action_status = 'no_action_needed'
   AND (f.detail IS NULL OR f.detail NOT LIKE '%[S51 triage:%');

\echo '== 3. Verify -- every WARNING/CRITICAL no_action_needed row is now stamped; MUST be zero =='
SELECT count(*) AS unstamped_settled_wc_rows_MUST_BE_ZERO
  FROM findings_log
 WHERE severity IN ('warning','critical')
   AND action_status = 'no_action_needed'
   AND (detail IS NULL OR detail NOT LIKE '%[S51 triage:%');

\echo '== 4. Verify row count unchanged (no DELETE) -- expect 26 stamped =='
SELECT count(*) AS stamped_rows_expect_26
  FROM findings_log WHERE detail LIKE '%[S51 triage:%';

\echo '== 5. T-LOG.3 re-assert -- retention jobs on findings_log MUST be zero =='
SELECT count(*) AS findings_log_retention_jobs_MUST_BE_ZERO
  FROM timescaledb_information.jobs
 WHERE proc_name LIKE '%retention%' AND hypertable_name = 'findings_log';

COMMIT;

\echo '== 6. Post-state snapshot =='
SELECT action_status, severity, count(*)
  FROM findings_log GROUP BY 1, 2 ORDER BY 1, 2;
