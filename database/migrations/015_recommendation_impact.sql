CREATE TABLE IF NOT EXISTS recommendation_episodes (
    recommendation_episode_id BIGSERIAL PRIMARY KEY,
    recommendation_key TEXT NOT NULL,
    episode_no INTEGER NOT NULL DEFAULT 1,

    active_now BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    priority TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    confidence TEXT,
    category TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    action_label TEXT,
    action_url TEXT,
    source_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    action_status TEXT NOT NULL DEFAULT 'PENDIENTE'
        CHECK (action_status IN ('PENDIENTE','EJECUTADA','IGNORADA')),
    action_at TIMESTAMPTZ,
    action_notes TEXT,

    measurement_status TEXT NOT NULL DEFAULT 'SIN_MEDIR'
        CHECK (measurement_status IN ('SIN_MEDIR','MEDIDO')),
    outcome TEXT
        CHECK (outcome IS NULL OR outcome IN ('POSITIVO','NEUTRO','NEGATIVO','INCIERTO')),

    attribution_method TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (attribution_method IN ('MANUAL','PEDIDO','ESTIMADO','NO_APLICA')),
    attribution_confidence TEXT
        CHECK (attribution_confidence IS NULL OR attribution_confidence IN ('ALTA','MEDIA','BAJA')),

    attributed_revenue NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (attributed_revenue >= 0),
    attributed_margin NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (attributed_margin >= 0),
    avoided_cost NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (avoided_cost >= 0),
    hours_saved NUMERIC(10,2) NOT NULL DEFAULT 0
        CHECK (hours_saved >= 0),
    hourly_value NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (hourly_value >= 0),

    evidence_reference TEXT,
    measurement_notes TEXT,
    measured_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (recommendation_key, episode_no)
);

CREATE INDEX IF NOT EXISTS recommendation_episodes_active_idx
    ON recommendation_episodes(active_now, action_status);

CREATE INDEX IF NOT EXISTS recommendation_episodes_last_seen_idx
    ON recommendation_episodes(last_seen_at DESC);

CREATE INDEX IF NOT EXISTS recommendation_episodes_outcome_idx
    ON recommendation_episodes(measurement_status, outcome);

CREATE TABLE IF NOT EXISTS recommendation_impact_audit (
    recommendation_impact_audit_id BIGSERIAL PRIMARY KEY,
    recommendation_episode_id BIGINT NOT NULL
        REFERENCES recommendation_episodes(recommendation_episode_id)
        ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    previous_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS recommendation_impact_audit_episode_idx
    ON recommendation_impact_audit(recommendation_episode_id, created_at DESC);

CREATE OR REPLACE VIEW recommendation_impact_v AS
SELECT
    r.*,
    ROUND(
        (
            COALESCE(r.attributed_margin, 0)
            + COALESCE(r.avoided_cost, 0)
            + COALESCE(r.hours_saved, 0) * COALESCE(r.hourly_value, 0)
        )::numeric,
        2
    ) AS economic_impact,
    ROUND(
        (
            COALESCE(r.hours_saved, 0) * COALESCE(r.hourly_value, 0)
        )::numeric,
        2
    ) AS time_value
FROM recommendation_episodes r;
