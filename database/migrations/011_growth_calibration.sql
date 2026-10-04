ALTER TABLE growth_actions
    ADD COLUMN IF NOT EXISTS initial_priority_band TEXT,
    ADD COLUMN IF NOT EXISTS priority_score NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS calibration_version TEXT,
    ADD COLUMN IF NOT EXISTS calibrated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS priority_reason TEXT,
    ADD COLUMN IF NOT EXISTS performance_context JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE growth_actions
SET initial_priority_band = priority_band
WHERE initial_priority_band IS NULL;

ALTER TABLE growth_results
    ADD COLUMN IF NOT EXISTS result_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_growth_results_result_key
    ON growth_results(result_key)
    WHERE result_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_growth_actions_priority_score
    ON growth_actions(priority_band, priority_score DESC, created_at DESC);

CREATE OR REPLACE VIEW growth_performance_by_channel_objective AS
SELECT
    ga.channel,
    ga.objective,
    COUNT(DISTINCT ga.growth_action_id) AS actions_with_results,
    COUNT(gr.growth_result_id) AS result_rows,
    COALESCE(SUM(gr.impressions), 0) AS impressions,
    COALESCE(SUM(gr.clicks), 0) AS clicks,
    COALESCE(SUM(gr.conversations), 0) AS conversations,
    COALESCE(SUM(gr.orders), 0) AS orders,
    COALESCE(SUM(gr.revenue), 0)::NUMERIC(14,2) AS revenue,
    COALESCE(SUM(gr.spend), 0)::NUMERIC(14,2) AS spend,
    CASE
        WHEN COALESCE(SUM(gr.impressions), 0) > 0
        THEN ROUND(SUM(gr.clicks)::NUMERIC / SUM(gr.impressions), 6)
        ELSE NULL
    END AS ctr,
    CASE
        WHEN COALESCE(SUM(gr.clicks), 0) > 0
        THEN ROUND(SUM(gr.orders)::NUMERIC / SUM(gr.clicks), 6)
        ELSE NULL
    END AS click_to_order_rate,
    CASE
        WHEN COALESCE(SUM(gr.spend), 0) > 0
        THEN ROUND(SUM(gr.revenue)::NUMERIC / SUM(gr.spend), 4)
        ELSE NULL
    END AS roas
FROM growth_actions ga
JOIN growth_results gr
  ON gr.growth_action_id = ga.growth_action_id
GROUP BY ga.channel, ga.objective;

CREATE OR REPLACE VIEW growth_action_performance AS
SELECT
    ga.growth_action_id,
    ga.channel,
    ga.objective,
    ga.priority_band,
    ga.priority_score,
    COUNT(gr.growth_result_id) AS result_rows,
    COALESCE(SUM(gr.impressions), 0) AS impressions,
    COALESCE(SUM(gr.clicks), 0) AS clicks,
    COALESCE(SUM(gr.conversations), 0) AS conversations,
    COALESCE(SUM(gr.orders), 0) AS orders,
    COALESCE(SUM(gr.revenue), 0)::NUMERIC(14,2) AS revenue,
    COALESCE(SUM(gr.spend), 0)::NUMERIC(14,2) AS spend,
    CASE
        WHEN COALESCE(SUM(gr.impressions), 0) > 0
        THEN ROUND(SUM(gr.clicks)::NUMERIC / SUM(gr.impressions), 6)
        ELSE NULL
    END AS ctr,
    CASE
        WHEN COALESCE(SUM(gr.clicks), 0) > 0
        THEN ROUND(SUM(gr.orders)::NUMERIC / SUM(gr.clicks), 6)
        ELSE NULL
    END AS click_to_order_rate,
    CASE
        WHEN COALESCE(SUM(gr.spend), 0) > 0
        THEN ROUND(SUM(gr.revenue)::NUMERIC / SUM(gr.spend), 4)
        ELSE NULL
    END AS roas
FROM growth_actions ga
LEFT JOIN growth_results gr
  ON gr.growth_action_id = ga.growth_action_id
GROUP BY
    ga.growth_action_id,
    ga.channel,
    ga.objective,
    ga.priority_band,
    ga.priority_score;
