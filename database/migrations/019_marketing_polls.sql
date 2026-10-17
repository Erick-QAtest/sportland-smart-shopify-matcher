-- Marketing Intelligence v8.0 — Fase 1: registro de encuestas de comunidad.
-- Las selecciones no equivalen a votantes: `unique_voters` solo se llena si se conoce.

CREATE TABLE IF NOT EXISTS marketing_polls (
    poll_id BIGSERIAL PRIMARY KEY,
    seed_key TEXT UNIQUE,
    community_code TEXT,
    channel TEXT,
    question TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'OTRO'
        CHECK (category IN ('PRECIO', 'COMODIDAD', 'MARCA', 'MODELO', 'TALLA', 'ESTILO', 'USO', 'OTRO')),
    multi_select BOOLEAN NOT NULL DEFAULT FALSE,
    asked_on DATE,
    unique_voters INTEGER CHECK (unique_voters IS NULL OR unique_voters >= 0),
    evidence_ref TEXT,
    related_brand TEXT,
    related_product TEXT,
    conclusion TEXT,
    confidence TEXT CHECK (confidence IS NULL OR confidence IN ('ALTA', 'MEDIA', 'BAJA')),
    follow_up_campaign_id BIGINT REFERENCES marketing_campaigns(campaign_id) ON DELETE SET NULL,
    outcome_notes TEXT,
    calendar_key TEXT REFERENCES marketing_calendar_items(calendar_key) ON DELETE SET NULL,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_marketing_polls_category
    ON marketing_polls(category, asked_on DESC);

CREATE TABLE IF NOT EXISTS marketing_poll_options (
    option_id BIGSERIAL PRIMARY KEY,
    poll_id BIGINT NOT NULL REFERENCES marketing_polls(poll_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    label TEXT NOT NULL,
    price_min_mxn NUMERIC(14,2),
    price_max_mxn NUMERIC(14,2),
    selections INTEGER NOT NULL DEFAULT 0 CHECK (selections >= 0),
    UNIQUE (poll_id, position)
);

-- Encuestas históricas del prompt maestro. Fecha y comunidad sin confirmar.
INSERT INTO marketing_polls (seed_key, question, category, multi_select, conclusion, confidence, created_by)
VALUES
    ('historica-precio-aceptable',
     '¿Cuánto consideras buen precio por unos tenis originales?', 'PRECIO', TRUE,
     'Mayor interés en el rango de $900 a $1,200. Son selecciones, no votantes, y no equivalen a disposición real de pago.',
     'BAJA', 'migracion_019'),
    ('historica-factores-compra',
     '¿Qué valoras más al comprar tenis?', 'COMODIDAD', TRUE,
     'Valoran comodidad y calidad a un precio accesible, no solamente el descuento más grande.',
     'BAJA', 'migracion_019')
ON CONFLICT (seed_key) DO NOTHING;

INSERT INTO marketing_poll_options (poll_id, position, label, price_min_mxn, price_max_mxn, selections)
SELECT p.poll_id, o.position, o.label, o.price_min, o.price_max, o.selections
FROM marketing_polls p
JOIN (VALUES
    ('historica-precio-aceptable', 1, '$700–$900', 700::numeric, 900::numeric, 9),
    ('historica-precio-aceptable', 2, '$900–$1,200', 900::numeric, 1200::numeric, 20),
    ('historica-precio-aceptable', 3, '$1,200–$1,500', 1200::numeric, 1500::numeric, 3),
    ('historica-precio-aceptable', 4, 'Más de $1,500', 1500::numeric, NULL::numeric, 1),
    ('historica-factores-compra', 1, 'Comodidad y calidad', NULL::numeric, NULL::numeric, 20),
    ('historica-factores-compra', 2, 'Mejor precio', NULL::numeric, NULL::numeric, 5),
    ('historica-factores-compra', 3, 'Estilo y diseño', NULL::numeric, NULL::numeric, 1),
    ('historica-factores-compra', 4, 'Entrega inmediata', NULL::numeric, NULL::numeric, 0)
) AS o(seed_key, position, label, price_min, price_max, selections)
  ON o.seed_key = p.seed_key
ON CONFLICT (poll_id, position) DO NOTHING;
