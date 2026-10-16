CREATE TABLE IF NOT EXISTS amazon_import_runs (
    import_run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','OK','FAILED')),
    source_files INTEGER NOT NULL DEFAULT 0,
    rows_read INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    rows_skipped INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS amazon_content_map (
    map_key TEXT PRIMARY KEY,
    tracking_id TEXT,
    link_id TEXT,
    content_url TEXT,
    content_title TEXT,
    channel TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS amazon_attribution_rows (
    amazon_row_id BIGSERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    tracking_id TEXT,
    link_id TEXT,
    content_url TEXT,
    content_title TEXT,
    channel TEXT,
    clicks INTEGER NOT NULL DEFAULT 0,
    ordered_items INTEGER NOT NULL DEFAULT 0,
    shipped_items INTEGER NOT NULL DEFAULT 0,
    ordered_revenue NUMERIC(14,2),
    earnings NUMERIC(14,2),
    currency TEXT NOT NULL DEFAULT 'MXN',
    conversion_rate NUMERIC(10,6),
    earnings_per_click NUMERIC(14,6),
    source_file TEXT,
    source_row_hash TEXT NOT NULL UNIQUE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_amazon_attribution_date
    ON amazon_attribution_rows(metric_date DESC);

CREATE INDEX IF NOT EXISTS ix_amazon_attribution_content
    ON amazon_attribution_rows(content_url, metric_date DESC)
    WHERE content_url IS NOT NULL;

CREATE OR REPLACE VIEW amazon_performance_daily_v AS
SELECT
    metric_date,
    COALESCE(content_url, tracking_id, link_id, 'SIN_ATRIBUCION') AS content_key,
    MAX(content_title) AS content_title,
    MAX(content_url) AS content_url,
    MAX(channel) AS channel,
    SUM(clicks) AS clicks,
    SUM(ordered_items) AS ordered_items,
    SUM(shipped_items) AS shipped_items,
    SUM(COALESCE(ordered_revenue,0))::NUMERIC(14,2) AS ordered_revenue,
    SUM(COALESCE(earnings,0))::NUMERIC(14,2) AS earnings,
    CASE WHEN SUM(clicks) > 0
      THEN ROUND(SUM(ordered_items)::NUMERIC / SUM(clicks), 6)
      ELSE NULL END AS conversion_rate,
    CASE WHEN SUM(clicks) > 0
      THEN ROUND(SUM(COALESCE(earnings,0))::NUMERIC / SUM(clicks), 6)
      ELSE NULL END AS earnings_per_click
FROM amazon_attribution_rows
GROUP BY metric_date, COALESCE(content_url, tracking_id, link_id, 'SIN_ATRIBUCION');
