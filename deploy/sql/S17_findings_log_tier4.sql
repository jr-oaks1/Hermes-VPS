-- ===================================================================== --
-- S17 / JR Hermes VPS — findings_log: Tier 4 escalation columns +
--                        TimescaleDB hypertable + compression
-- ===================================================================== --
--
-- Run as a SUPERUSER against hermes_vps_log (the runtime role `hermes_vps`
-- is not the table owner; this is a one-time schema migration, reversible,
-- with explicit user OK — HERMES_PLATFORM_STANDARD R5):
--
--     sudo -u postgres psql -v ON_ERROR_STOP=1 -d hermes_vps_log \
--          -f deploy/sql/S17_findings_log_tier4.sql
--
-- Idempotent: safe to re-run. Take a manual pg_dump first (R-RESTORE-4):
--     pg_dump -Fc hermes_vps_log > /opt/backups/hermes_vps_log/manual/hermes_vps_log_pre-s17.dump
--
-- RETENTION: none. findings_log is a permanent historical record for
-- continuous improvement (CONTINUOUS_IMPROVEMENT_STANDARD.md Rule T-LOG.3).
-- This script adds a COMPRESSION policy only — never add_retention_policy.
--
-- ROLLBACK (noted per R5):
--   SELECT remove_compression_policy('findings_log', if_exists => true);
--   ALTER TABLE findings_log SET (timescaledb.compress = false);
--   -- (hypertable -> plain table is not reversible in place; restore the
--   --  pre-s17 dump into a scratch DB if a full revert is ever needed)
--   DROP INDEX IF EXISTS findings_log_escalation_idx;
--   ALTER TABLE findings_log DROP CONSTRAINT IF EXISTS findings_log_action_status_chk;
--   ALTER TABLE findings_log
--     DROP COLUMN IF EXISTS action_status,   DROP COLUMN IF EXISTS owner_project,
--     DROP COLUMN IF EXISTS event_uid,       DROP COLUMN IF EXISTS escalated_gm_at,
--     DROP COLUMN IF EXISTS escalated_ceo_at;
-- ===================================================================== --

\echo '== 1. Tier 4 columns =='
ALTER TABLE findings_log ADD COLUMN IF NOT EXISTS action_status    text NOT NULL DEFAULT 'open';
ALTER TABLE findings_log ADD COLUMN IF NOT EXISTS owner_project    text;
ALTER TABLE findings_log ADD COLUMN IF NOT EXISTS event_uid        text;
ALTER TABLE findings_log ADD COLUMN IF NOT EXISTS escalated_gm_at  timestamptz;
ALTER TABLE findings_log ADD COLUMN IF NOT EXISTS escalated_ceo_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'findings_log_action_status_chk') THEN
    ALTER TABLE findings_log ADD CONSTRAINT findings_log_action_status_chk
      CHECK (action_status IN ('open','in_progress','resolved','closed','no_action_needed'));
  END IF;
END $$;

\echo '== 2. Backfill: retro-close pre-S17 rows older than 7 days (user-approved S17) =='
\echo '   (affected row count:)'
SELECT count(*) AS rows_to_retro_close
  FROM findings_log
 WHERE ts < now() - interval '7 days' AND action_status = 'open';

UPDATE findings_log
   SET action_status = 'no_action_needed',
       detail = coalesce(detail,'') || ' [S17 backfill: pre-Tier4 row, retro-closed]'
 WHERE ts < now() - interval '7 days' AND action_status = 'open';

\echo '== 3. TimescaleDB extension (shared_preload_libraries already loads it cluster-wide) =='
CREATE EXTENSION IF NOT EXISTS timescaledb;

\echo '== 4. Widen primary key to (id, ts) — hypertable partitioning column must be in every unique index =='
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'findings_log' AND c.conname = 'findings_log_pkey'
      AND pg_get_constraintdef(c.oid) = 'PRIMARY KEY (id)'
  ) THEN
    ALTER TABLE findings_log DROP CONSTRAINT findings_log_pkey;
    ALTER TABLE findings_log ADD CONSTRAINT findings_log_pkey PRIMARY KEY (id, ts);
  END IF;
END $$;

\echo '== 5. Convert to hypertable (1-month chunks) =='
SELECT create_hypertable(
  'findings_log', 'ts',
  chunk_time_interval => interval '1 month',
  migrate_data        => true,
  if_not_exists       => true
);

\echo '== 6. Indexes =='
-- Reconciliation / dedup join key — unique index must carry the partition column.
CREATE UNIQUE INDEX IF NOT EXISTS findings_log_event_uid_ts_uidx
  ON findings_log (event_uid, ts) WHERE event_uid IS NOT NULL;

-- Tier 4 escalation hot path: open/in_progress CRITICALs, newest first.
CREATE INDEX IF NOT EXISTS findings_log_escalation_idx
  ON findings_log (ts DESC)
  WHERE severity = 'critical' AND action_status IN ('open','in_progress');

-- Reconciliation window scan (WARNING and above).
CREATE INDEX IF NOT EXISTS findings_log_nonfinfo_idx
  ON findings_log (ts DESC) WHERE severity <> 'info';

\echo '== 7. Compression policy — compress chunks older than 90 days. NO retention policy. =='
ALTER TABLE findings_log SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'severity, source',
  timescaledb.compress_orderby   = 'ts DESC'
);

SELECT add_compression_policy('findings_log', compress_after => interval '90 days', if_not_exists => true);

\echo '== 8. Verify — no retention job may exist =='
SELECT count(*) AS retention_jobs_MUST_BE_ZERO
  FROM timescaledb_information.jobs
 WHERE proc_name LIKE '%retention%';

\echo '== 9. Final shape =='
\d findings_log
SELECT hypertable_name, num_chunks, compression_enabled
  FROM timescaledb_information.hypertables WHERE hypertable_name = 'findings_log';
SELECT action_status, severity, count(*)
  FROM findings_log GROUP BY 1,2 ORDER BY 1,2;
