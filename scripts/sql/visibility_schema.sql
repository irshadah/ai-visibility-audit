CREATE TABLE IF NOT EXISTS visibility_runs (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    brand_name TEXT,
    company_name TEXT,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt_set_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    overall_score INT,
    overall_label TEXT,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    provider_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cost_estimate_usd NUMERIC(10, 4) NOT NULL DEFAULT 0,
    latency_ms INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_visibility_runs_url_started
    ON visibility_runs (url, started_at DESC);

CREATE TABLE IF NOT EXISTS visibility_provider_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES visibility_runs(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    mentions INT NOT NULL DEFAULT 0,
    citations INT NOT NULL DEFAULT 0,
    mention_rate NUMERIC(6, 4) NOT NULL DEFAULT 0,
    citation_rate NUMERIC(6, 4) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_visibility_provider_metrics_run
    ON visibility_provider_metrics (run_id);

CREATE TABLE IF NOT EXISTS visibility_topics (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES visibility_runs(id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL,
    topic_label TEXT NOT NULL,
    visibility_score INT NOT NULL DEFAULT 0,
    ai_volume_bucket TEXT,
    chatgpt_mentioned BOOLEAN NOT NULL DEFAULT FALSE,
    gemini_mentioned BOOLEAN NOT NULL DEFAULT FALSE,
    claude_mentioned BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_visibility_topics_run
    ON visibility_topics (run_id);

CREATE TABLE IF NOT EXISTS visibility_probes (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES visibility_runs(id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    response_text TEXT,
    mentioned BOOLEAN NOT NULL DEFAULT FALSE,
    cited BOOLEAN NOT NULL DEFAULT FALSE,
    brand_context TEXT,
    response_latency_ms INT NOT NULL DEFAULT 0,
    error_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_visibility_probes_run
    ON visibility_probes (run_id);
