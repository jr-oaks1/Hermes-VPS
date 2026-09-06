-- ===================================================================== --
-- S18 / JR Hermes VPS — findings_log: settle steady-state INFO rows that
--                        were born 'open' before the S18 emission fix
-- ===================================================================== --
--
-- Run as a SUPERUSER against hermes_vps_log (the runtime role `hermes_vps`
-- is not the table owner — HERMES_PLATFORM_STANDARD R5, one-time, reversible):
--
--     sudo -u postgres psql -v ON_ERROR_STOP=1 -d hermes_vps_log \
--          -f deploy/sql/S18_findings_log_info_settle.sql
--
-- Take a manual pg_dump first (R-RESTORE-4):
--     pg_dump -Fc hermes_vps_log > /opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s18.dump
--
-- WHY: before S18, scripts/log_finding.insert_findings never named action_status,
-- so every row — INFO included — took the DB default 'open'. The Tier 4
-- escalation check emitted 3 INFO rows every 15 min (288/day), all landing
-- 'open', so "open" stopped meaning "a human must act". S18 fixes the source
-- (initial_action_status() → INFO enters 'no_action_needed'; emission_state.py
-- throttles the steady-state chatter). This migration settles the ~105 rows
-- that already accumulated.
--
-- T-LOG.3: this is a STATE UPDATE, never a DELETE, and adds NO retention policy.
-- findings_log stays the permanent continuous-improvement record.
--
-- ORDERING: run this AFTER the S18 code is deployed. Otherwise the next 15-min
-- cycle inserts 3 fresh 'open' INFO rows and step 3 fails.
--
-- ROLLBACK (noted per R5):
--   UPDATE findings_log SET action_status = 'open'
--    WHERE severity = 'info' AND detail LIKE '%[S18 settle:%';
-- ===================================================================== --

\echo '== 0. Pre-flight: no compressed chunks (UPDATE on a compressed chunk fails) =='
SELECT count(*) AS compressed_chunks_MUST_BE_ZERO
  FROM timescaledb_information.chunks
 WHERE hypertable_name = 'findings_log' AND is_compressed;

\echo '== 1. Affected rows (INFO born open) — expect ~105 =='
SELECT session_ref, count(*)
  FROM findings_log
 WHERE severity = 'info' AND action_status = 'open'
 GROUP BY 1 ORDER BY 2 DESC;

\echo '== 2. Settle — state update only, NEVER a DELETE (T-LOG.3) =='
UPDATE findings_log
   SET action_status = 'no_action_needed',
       detail = coalesce(detail, '')
              || ' [S18 settle: informational row, never actionable — reclassified so'
              || ' "open" means actionable; source fixed in log_finding.initial_action_status'
              || ' + emission_state.py throttle]'
 WHERE severity = 'info'
   AND action_status = 'open'
   AND (detail IS NULL OR detail NOT LIKE '%[S18 settle:%');

\echo '== 3. Verify — MUST be zero =='
SELECT count(*) AS open_info_rows_MUST_BE_ZERO
  FROM findings_log WHERE severity = 'info' AND action_status = 'open';

\echo '== 4. T-LOG.3 re-assert — retention jobs on findings_log MUST be zero =='
SELECT count(*) AS findings_log_retention_jobs_MUST_BE_ZERO
  FROM timescaledb_information.jobs
 WHERE proc_name LIKE '%retention%' AND hypertable_name = 'findings_log';

\echo '== 5. Post-state snapshot =='
SELECT action_status, severity, count(*)
  FROM findings_log GROUP BY 1, 2 ORDER BY 1, 2;
