-- Marketing Intelligence v8.0 — Fase 1: campañas, flujo de aprobación del calendario,
-- bitácora de cambios y biblioteca de recursos.
-- Solo agrega: no borra ni renombra nada. La columna `status` original del calendario
-- (estado de planeación que viene del CSV) se conserva; el flujo de aprobación vive en
-- `workflow_status`, así una reimportación del CSV nunca reinicia una aprobación.

CREATE TABLE IF NOT EXISTS marketing_campaigns (
    campaign_id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    objective TEXT,
    theme TEXT,
    starts_on DATE NOT NULL,
    ends_on DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANEADA'
        CHECK (status IN ('PLANEADA', 'ACTIVA', 'CERRADA', 'CANCELADA')),
    budget_mxn NUMERIC(14,2) CHECK (budget_mxn IS NULL OR budget_mxn >= 0),
    sales_goal_mxn NUMERIC(14,2) CHECK (sales_goal_mxn IS NULL OR sales_goal_mxn >= 0),
    notes TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_on >= starts_on)
);

CREATE INDEX IF NOT EXISTS ix_marketing_campaigns_dates
    ON marketing_campaigns(starts_on, ends_on);

ALTER TABLE marketing_calendar_items
    ADD COLUMN IF NOT EXISTS campaign_id BIGINT
        REFERENCES marketing_campaigns(campaign_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS community_code TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS objective TEXT,
    ADD COLUMN IF NOT EXISTS shopify_product_id TEXT,
    ADD COLUMN IF NOT EXISTS shopify_variant_ids TEXT[],
    ADD COLUMN IF NOT EXISTS copy_text TEXT,
    ADD COLUMN IF NOT EXISTS recommendation_episode_id BIGINT
        REFERENCES recommendation_episodes(recommendation_episode_id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS workflow_status TEXT NOT NULL DEFAULT 'BORRADOR',
    ADD COLUMN IF NOT EXISTS approved_by TEXT,
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS published_ref TEXT,
    ADD COLUMN IF NOT EXISTS measured_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS result_notes TEXT,
    ADD COLUMN IF NOT EXISTS created_by TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_marketing_calendar_workflow_status'
    ) THEN
        ALTER TABLE marketing_calendar_items
            ADD CONSTRAINT ck_marketing_calendar_workflow_status CHECK (
                workflow_status IN (
                    'BORRADOR', 'EN_REVISION', 'APROBADO', 'PROGRAMADO',
                    'PUBLICADO', 'MEDIDO', 'DESCARTADO'
                )
            );
    END IF;
    -- Regla dura: nada llega a Publicado o Medido sin una aprobación registrada.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_marketing_calendar_publish_needs_approval'
    ) THEN
        ALTER TABLE marketing_calendar_items
            ADD CONSTRAINT ck_marketing_calendar_publish_needs_approval CHECK (
                workflow_status NOT IN ('PUBLICADO', 'MEDIDO') OR approved_at IS NOT NULL
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_marketing_calendar_content_type'
    ) THEN
        ALTER TABLE marketing_calendar_items
            ADD CONSTRAINT ck_marketing_calendar_content_type CHECK (
                content_type IS NULL OR content_type IN (
                    'PRODUCTO', 'ENCUESTA', 'OFERTA', 'EDUCATIVO', 'PAGOS', 'OTRO'
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_marketing_calendar_workflow
    ON marketing_calendar_items(workflow_status, scheduled_date);
CREATE INDEX IF NOT EXISTS ix_marketing_calendar_campaign
    ON marketing_calendar_items(campaign_id, scheduled_date);

CREATE TABLE IF NOT EXISTS marketing_change_log (
    change_id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('CALENDARIO', 'CAMPANA', 'ENCUESTA', 'RECURSO')),
    entity_key TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    before_data JSONB,
    after_data JSONB,
    note TEXT,
    actor TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_marketing_change_log_entity
    ON marketing_change_log(entity_type, entity_key, changed_at DESC);

-- Biblioteca de recursos (V1: referencias a archivos que ya viven en Drive, Shopify,
-- Instagram, etc.; el portal no recibe archivos).
CREATE TABLE IF NOT EXISTS marketing_assets (
    asset_id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'FOTO'
        CHECK (kind IN ('FOTO', 'VIDEO', 'CREATIVO', 'COPY', 'OTRO')),
    location_url TEXT,
    shopify_product_id TEXT,
    brand TEXT,
    notes TEXT,
    parent_asset_id BIGINT REFERENCES marketing_assets(asset_id) ON DELETE SET NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS marketing_item_assets (
    calendar_key TEXT NOT NULL
        REFERENCES marketing_calendar_items(calendar_key) ON DELETE CASCADE,
    asset_id BIGINT NOT NULL
        REFERENCES marketing_assets(asset_id) ON DELETE CASCADE,
    format_note TEXT,
    PRIMARY KEY (calendar_key, asset_id)
);

-- Campañas noviembre–diciembre 2026 (fechas del plan; El Buen Fin 2026 = 13–17 nov).
INSERT INTO marketing_campaigns (code, name, objective, theme, starts_on, ends_on, notes, created_by)
VALUES
    ('2026-11-COMODIDAD', 'Comodidad diaria', 'Visitas y ventas de producto en stock',
     'Comodidad diaria y tecnologías de confort', DATE '2026-11-02', DATE '2026-11-08', NULL, 'migracion_018'),
    ('2026-11-CALIDAD-PRECIO', 'Originales con buena relación calidad-precio', 'Ventas de producto en stock',
     'Tenis originales con buena relación calidad-precio', DATE '2026-11-09', DATE '2026-11-12', NULL, 'migracion_018'),
    ('2026-11-BUEN-FIN', 'El Buen Fin 2026', 'Ventas con ofertas que respeten el piso de margen',
     'El Buen Fin', DATE '2026-11-13', DATE '2026-11-17',
     'Sujeto a la participación y requisitos aplicables.', 'migracion_018'),
    ('2026-11-TALLAS', 'Destacados y tallas disponibles', 'Ventas por talla disponible',
     'Productos destacados y tallas disponibles', DATE '2026-11-18', DATE '2026-11-26', NULL, 'migracion_018'),
    ('2026-11-BF-CM', 'Black Friday y Cyber Monday', 'Ventas con ofertas que respeten el piso de margen',
     'Black Friday y Cyber Monday', DATE '2026-11-27', DATE '2026-11-30', NULL, 'migracion_018'),
    ('2026-12-REGALOS', 'Regalos originales', 'Ventas de temporada',
     'Regalos, sneakers originales y comodidad', DATE '2026-12-01', DATE '2026-12-13', NULL, 'migracion_018'),
    ('2026-12-GUIAS', 'Guías de tallas y regalos', 'Ventas de temporada con talla correcta',
     'Guías de tallas y regalos', DATE '2026-12-14', DATE '2026-12-20', NULL, 'migracion_018'),
    ('2026-12-CIERRE', 'Cierre de año', 'Últimas compras y retención',
     'Últimas compras, oportunidades de cierre de año y retención', DATE '2026-12-21', DATE '2026-12-31', NULL, 'migracion_018')
ON CONFLICT (code) DO NOTHING;
