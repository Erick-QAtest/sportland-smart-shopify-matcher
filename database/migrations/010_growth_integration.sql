CREATE TABLE IF NOT EXISTS growth_runs (
    growth_run_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_artifact TEXT,
    actions_generated INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS growth_actions (
    growth_action_id BIGSERIAL PRIMARY KEY,
    action_key TEXT NOT NULL UNIQUE,
    growth_run_id TEXT
        REFERENCES growth_runs(growth_run_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    source_type TEXT NOT NULL,
    source_ref TEXT,
    sku TEXT,
    product_key TEXT,
    product_title TEXT,

    channel TEXT NOT NULL
        CHECK (channel IN ('META', 'WHATSAPP', 'YOUTUBE', 'GOOGLE_SEO')),
    objective TEXT NOT NULL,
    priority_band TEXT NOT NULL
        CHECK (priority_band IN ('HIGH', 'MEDIUM', 'LOW', 'SIGNAL')),
    activation_mode TEXT NOT NULL
        CHECK (activation_mode IN ('MANUAL_REVIEW', 'CONTENT_REVIEW', 'INDIVIDUAL_REVIEW')),
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'APPROVED', 'REJECTED', 'EXECUTED', 'MEASURED', 'CLOSED')),

    requires_human_approval BOOLEAN NOT NULL DEFAULT TRUE,
    automatic_activation BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_growth_actions_channel_status
    ON growth_actions(channel, status, priority_band);

CREATE INDEX IF NOT EXISTS ix_growth_actions_sku
    ON growth_actions(sku, created_at DESC);

CREATE TABLE IF NOT EXISTS growth_results (
    growth_result_id BIGSERIAL PRIMARY KEY,
    growth_action_id BIGINT NOT NULL
        REFERENCES growth_actions(growth_action_id) ON DELETE CASCADE,
    external_ref TEXT,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    impressions BIGINT,
    clicks BIGINT,
    conversations BIGINT,
    orders BIGINT,
    revenue NUMERIC(14,2),
    spend NUMERIC(14,2),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_growth_results_action_time
    ON growth_results(growth_action_id, captured_at DESC);
