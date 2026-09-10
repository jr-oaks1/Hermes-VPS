-- ===================================================================== --
-- S19b / JR Hermes VPS — findings_log: settle the guardrail/escalation
--                        deadlock storm (2026-09-08 → 2026-09-10)
-- ===================================================================== --
--
-- Run as a SUPERUSER against hermes_vps_log (runtime role `hermes_vps` is not
-- the table owner — HERMES_PLATFORM_STANDARD R5; one-time, reversible):
--
--     sudo -u postgres psql -v ON_ERROR_STOP=1 -d hermes_vps_log \
--          -f deploy/sql/S19b_findings_log_storm_triage.sql
--
-- Take a manual pg_dump FIRST (R-RESTORE-4):
--     pg_dump -Fc hermes_vps_log \
--       > /opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s19b.dump
--
-- WHY: on 2026-09-08 00:00 UTC `hermes-healthcheck.service` (Ingestor's Tier-3
-- check; unit owned by this project) exited non-zero on a real CRITICAL
-- (raw_onchain ~48h stale — since recovered). That made it a `failed` unit.
-- At 00:04 the Tier 3 guardrail saw it, emitted `systemd: 1 failed unit(s)`
-- CRITICAL, and — because run() returned 1 on any critical — became a `failed`
-- unit ITSELF. From then on the guardrail alarmed on its own failure and the
-- Tier 4 escalation check escalated that CRITICAL every 15 min, re-emitting a
-- Finding per open row per cycle and nesting "CEO ESCALATION ... 'CEO
-- ESCALATION ...'". Net: ~39,700 self-generated open WARNING/CRITICAL rows in
-- ~56h, ~13.6k Telegram delivery failures.
--
-- S19b fixes the source (exit 0 = "audit ran"; guardrail excludes its own two
-- units; escalation emits once per band-crossing latch and never re-selects its
-- own output). This migration settles the rows the storm already wrote.
--
-- SCOPE: only rows whose SUMMARY matches a known self-generated class AND
-- ts >= 2026-09-08 00:00 UTC AND action_status = 'open'. Pattern-scoped by
-- construction — a row about anything else cannot be touched. Step 2 prints the
-- open WARNING/CRITICAL rows that will REMAIN open — eyeball them before step 4.
--
-- T-LOG.3 / T-LOG.4: STATE UPDATE only, never a DELETE, no retention policy
-- added, and every settled row is stamped with an explicit reason (not an
-- age-blind sweep — that is the S51 Rule T-LOG.4 lesson).
--
-- ORDERING: run AFTER the S19b code is deployed and both timers restarted
-- clean, else the next cycle writes fresh storm rows and step 5 fails.
--
-- ROLLBACK:
--   UPDATE findings_log SET action_status = 'open'
--    WHERE detail LIKE '%[S19b triage:%';
-- ===================================================================== --

\set STORM_SINCE '2026-09-08 00:00:00+00'

\echo '== 0. Pre-flight: no compressed chunks (UPDATE on a compressed chunk fails) =='
SELECT count(*) AS compressed_chunks_MUST_BE_ZERO
  FROM timescaledb_information.chunks
 WHERE hypertable_name = 'findings_log' AND is_compressed;

\echo '== 1. Storm inventory — open WARNING/CRITICAL rows by class (since 2026-09-08) =='
SELECT
  CASE
    WHEN summary LIKE 'escalation:%'                     THEN 'escalation ladder (self-generated)'
    WHEN summary LIKE 'systemd:%failed unit(s)%'         THEN 'guardrail systemd self-alarm'
    WHEN summary LIKE 'reconcile:%'                      THEN 'reconcile (storm fallout)'
    WHEN summary LIKE 'log_finding: dual-write incomplete%' THEN 'self-report (Telegram 429 fallout)'
    WHEN summary LIKE 'guardrail:%'
      OR summary LIKE 'guardrail.heartbeat:%'            THEN 'guardrail misc (storm fallout)'
    ELSE '>>> NOT A STORM CLASS — WILL REMAIN OPEN <<<'
  END AS class,
  severity, count(*)
  FROM findings_log
 WHERE action_status = 'open'
   AND severity IN ('warning','critical')
   AND ts >= :'STORM_SINCE'
 GROUP BY 1, 2 ORDER BY 1, 2;

\echo '== 2. Rows that will REMAIN open after this migration — VERIFY each is genuinely actionable =='
SELECT id, ts, severity, left(summary, 90) AS summary
  FROM findings_log
 WHERE action_status = 'open'
   AND severity IN ('warning','critical')
   AND NOT (
        summary LIKE 'escalation:%'
     OR summary LIKE 'systemd:%failed unit(s)%'
     OR summary LIKE 'reconcile:%'
     OR summary LIKE 'log_finding: dual-write incomplete%'
     OR summary LIKE 'guardrail:%'
     OR summary LIKE 'guardrail.heartbeat:%'
   )
 ORDER BY ts DESC
 LIMIT 100;

\echo '== 3. Count to be settled =='
SELECT count(*) AS rows_to_settle
  FROM findings_log
 WHERE action_status = 'open'
   AND ts >= :'STORM_SINCE'
   AND (
        summary LIKE 'escalation:%'
     OR summary LIKE 'systemd:%failed unit(s)%'
     OR summary LIKE 'reconcile:%'
     OR summary LIKE 'log_finding: dual-write incomplete%'
     OR summary LIKE 'guardrail:%'
     OR summary LIKE 'guardrail.heartbeat:%'
   );

\echo '== 4. Settle — state update only, NEVER a DELETE (T-LOG.3); each row stamped (T-LOG.4) =='
UPDATE findings_log
   SET action_status = 'no_action_needed',
       detail = coalesce(detail, '')
              || ' [S19b triage: guardrail/escalation deadlock storm 2026-09-08..10;'
              || ' seed = hermes-healthcheck.service exit-nonzero on a now-recovered CRITICAL;'
              || ' self-sustaining via exit-1-on-finding + guardrail self-alarm + per-cycle'
              || ' re-emission. Source fixed S19b (exit-0 contract, own-unit exclusion,'
              || ' latch-gated emission, open_critical self-exclusion). Not individually actionable.]'
 WHERE action_status = 'open'
   AND ts >= :'STORM_SINCE'
   AND (
        summary LIKE 'escalation:%'
     OR summary LIKE 'systemd:%failed unit(s)%'
     OR summary LIKE 'reconcile:%'
     OR summary LIKE 'log_finding: dual-write incomplete%'
     OR summary LIKE 'guardrail:%'
     OR summary LIKE 'guardrail.heartbeat:%'
   )
   AND (detail IS NULL OR detail NOT LIKE '%[S19b triage:%');

\echo '== 5. Verify — open storm-class rows MUST be zero =='
SELECT count(*) AS open_storm_rows_MUST_BE_ZERO
  FROM findings_log
 WHERE action_status = 'open'
   AND ts >= :'STORM_SINCE'
   AND (
        summary LIKE 'escalation:%'
     OR summary LIKE 'systemd:%failed unit(s)%'
     OR summary LIKE 'reconcile:%'
     OR summary LIKE 'log_finding: dual-write incomplete%'
     OR summary LIKE 'guardrail:%'
     OR summary LIKE 'guardrail.heartbeat:%'
   );

\echo '== 6. T-LOG.3 re-assert — retention jobs on findings_log MUST be zero =='
SELECT count(*) AS findings_log_retention_jobs_MUST_BE_ZERO
  FROM timescaledb_information.jobs
 WHERE proc_name LIKE '%retention%' AND hypertable_name = 'findings_log';

\echo '== 7. T-LOG.4 re-assert — no settled WARNING/CRITICAL row without a triage/meta stamp =='
SELECT count(*) AS untriaged_settled_MUST_BE_ZERO
  FROM findings_log
 WHERE severity IN ('warning','critical')
   AND action_status = 'no_action_needed'
   AND (detail IS NULL
        OR (position('triage:' in lower(detail)) = 0
            AND position('[meta:' in lower(detail)) = 0));

\echo '== 8. Post-state snapshot =='
SELECT action_status, severity, count(*)
  FROM findings_log GROUP BY 1, 2 ORDER BY 1, 2;
