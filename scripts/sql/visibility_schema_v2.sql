-- Visibility schema v2: MVP Phase 1 + 2b
-- Run after visibility_schema.sql (base tables).
-- See docs/tasks/TASK-0-schema-migrations.md.

-- 1. probe_status for visibility_probes (TASK 2b.3)
ALTER TABLE visibility_probes
  ADD COLUMN IF NOT EXISTS probe_status TEXT NOT NULL DEFAULT 'success';

-- 2. Optional: region, language, user_id on visibility_runs
ALTER TABLE visibility_runs
  ADD COLUMN IF NOT EXISTS region_code TEXT DEFAULT 'us';
ALTER TABLE visibility_runs
  ADD COLUMN IF NOT EXISTS language_code TEXT DEFAULT 'en';
ALTER TABLE visibility_runs
  ADD COLUMN IF NOT EXISTS user_id BIGINT NULL;

-- 3. Migrate legacy status 'done' -> 'complete'
UPDATE visibility_runs SET status = 'complete' WHERE status = 'done';

-- 4. visibility_run_cache for competitor comparison (TASK 1.6)
CREATE TABLE IF NOT EXISTS visibility_run_cache (
    id BIGSERIAL PRIMARY KEY,
    cache_key TEXT UNIQUE NOT NULL,
    run_id BIGINT NOT NULL REFERENCES visibility_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_visibility_run_cache_key
    ON visibility_run_cache (cache_key);
CREATE INDEX IF NOT EXISTS idx_visibility_run_cache_created
    ON visibility_run_cache (created_at);

-- 5. Index for rate limit / cost queries (TASK 2b.2)
CREATE INDEX IF NOT EXISTS idx_visibility_runs_completed_status
    ON visibility_runs (completed_at, status)
    WHERE completed_at IS NOT NULL;
