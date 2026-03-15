-- Phase 4: visibility_query_runs for query-driven analysis
-- Run after visibility_schema.sql and visibility_schema_v2.sql

CREATE TABLE IF NOT EXISTS visibility_query_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    brand_name TEXT,
    company_name TEXT,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    query_text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'generic',
    provider TEXT NOT NULL,
    run_count INT NOT NULL DEFAULT 0,
    mentioned BOOLEAN NOT NULL DEFAULT FALSE,
    in_top_5 BOOLEAN NOT NULL DEFAULT FALSE,
    in_top_10 BOOLEAN NOT NULL DEFAULT FALSE,
    appearance_rate_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    avg_position NUMERIC(4, 2),
    evidence_text TEXT,
    cost_estimate_usd NUMERIC(10, 4) NOT NULL DEFAULT 0,
    latency_ms INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'complete',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_visibility_query_runs_url_query
    ON visibility_query_runs (url, query_text, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_visibility_query_runs_job
    ON visibility_query_runs (job_id);
CREATE INDEX IF NOT EXISTS idx_visibility_query_runs_completed
    ON visibility_query_runs (completed_at, status)
    WHERE completed_at IS NOT NULL;
