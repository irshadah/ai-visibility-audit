-- Phase 4 v2: Add in_top_10, drop confidence from visibility_query_runs
-- Run after visibility_schema_query_runs.sql

ALTER TABLE visibility_query_runs ADD COLUMN IF NOT EXISTS in_top_10 BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE visibility_query_runs DROP COLUMN IF EXISTS confidence;
