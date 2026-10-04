ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS opportunity_score NUMERIC(5,2);

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS priority_band TEXT
        CHECK (priority_band IN ('HIGH', 'MEDIUM', 'LOW', 'HOLD', 'SIGNAL'));

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS score_version TEXT;

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS scored_at TIMESTAMPTZ;

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS ix_commercial_opportunities_priority_score
    ON commercial_opportunities(priority_band, opportunity_score DESC);
