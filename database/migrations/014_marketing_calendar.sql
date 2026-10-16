CREATE TABLE IF NOT EXISTS marketing_calendar_items (
    calendar_key TEXT PRIMARY KEY,
    scheduled_date DATE NOT NULL,
    weekday_name TEXT,
    pillar TEXT,
    target_segment TEXT,
    channel TEXT,
    format TEXT,
    topic TEXT,
    hook TEXT,
    cta TEXT,
    destination TEXT,
    event_signal TEXT,
    ads_distribution TEXT,
    suggested_time TEXT,
    kpi TEXT,
    priority TEXT,
    status TEXT NOT NULL DEFAULT 'PLANIFICADO',
    source_name TEXT NOT NULL DEFAULT 'Sportland_Calendario_Redes_Comunidad_30_dias',
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_marketing_calendar_date
    ON marketing_calendar_items(scheduled_date, priority);

CREATE TABLE IF NOT EXISTS marketing_calendar_imports (
    source_name TEXT PRIMARY KEY,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_imported INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
