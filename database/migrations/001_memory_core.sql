CREATE TABLE IF NOT EXISTS event_catalog (
    event_type_id INTEGER PRIMARY KEY,
    event_type_name TEXT NOT NULL UNIQUE,
    event_scope TEXT NOT NULL DEFAULT 'customer'
        CHECK (event_scope IN ('customer', 'system', 'both')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO event_catalog(event_type_id, event_type_name, event_scope) VALUES
    (1,  'ENTRADA_WHATSAPP', 'customer'),
    (2,  'REACCION_CONTENIDO', 'customer'),
    (3,  'CLICK', 'customer'),
    (4,  'PREGUNTA_TALLA_PRECIO', 'customer'),
    (5,  'DM_ACTIVO', 'customer'),
    (6,  'APARTADO', 'customer'),
    (7,  'COMPRA', 'customer'),
    (8,  'SILENCIO_PROLONGADO', 'customer'),
    (9,  'EVENTO_NEGATIVO', 'customer'),
    (10, 'UNION_COMUNIDAD_WHATSAPP', 'customer'),
    (11, 'SALIDA_COMUNIDAD_WHATSAPP', 'customer'),
    (12, 'OFERTA_LLEGADA_PROXIMA', 'both'),
    (20, 'PREGUNTA_SISTEMA_APARTADO', 'customer'),
    (21, 'PREGUNTA_MODELO_ESPECIFICO', 'customer'),
    (22, 'PRUEBA_MULTIPLES_MODELOS', 'customer'),
    (23, 'SALE_SIN_COMPRA', 'customer'),
    (30, 'ABONO_APARTADO', 'customer'),
    (31, 'LIQUIDACION_APARTADO', 'customer'),
    (40, 'COMPRA_TIENDA_FISICA', 'customer'),
    (41, 'COMPRA_ECOMMERCE', 'customer'),
    (42, 'COMPRA_MARKETPLACE', 'customer'),
    (50, 'REVIEW_POSITIVA', 'customer'),
    (51, 'REVIEW_NEGATIVA', 'customer'),
    (52, 'MODELO_NUEVO_INGRESADO', 'system'),
    (60, 'PROMO_MONEDERO_120', 'system'),
    (61, 'PROMO_SEGUNDO_PAR_20', 'system'),
    (62, 'PROMO_ENVIO_GRATIS', 'system')
ON CONFLICT (event_type_id) DO UPDATE
SET event_type_name = EXCLUDED.event_type_name,
    event_scope = EXCLUDED.event_scope;

CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    client_uuid TEXT NOT NULL UNIQUE,
    phone_e164 TEXT,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    first_channel TEXT,
    current_stage TEXT NOT NULL DEFAULT 'UNKNOWN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_uuid TEXT UNIQUE,
    event_hash TEXT,
    source TEXT NOT NULL,
    source_row_hash TEXT,
    customer_id BIGINT REFERENCES customers(customer_id) ON DELETE SET NULL,
    client_uuid TEXT,
    event_type_id INTEGER REFERENCES event_catalog(event_type_id),
    event_type_name TEXT NOT NULL,
    detail TEXT,
    occurred_at TIMESTAMPTZ,
    logged_at TIMESTAMPTZ,
    sku TEXT,
    size TEXT,
    amount NUMERIC(14,2),
    channel TEXT,
    pct NUMERIC(10,4),
    currency TEXT NOT NULL DEFAULT 'MXN',
    actor TEXT,
    device TEXT,
    origin TEXT,
    silence_flag_system BOOLEAN,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_row_hash)
);

CREATE INDEX IF NOT EXISTS ix_customer_events_customer_time
    ON customer_events(customer_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ix_customer_events_sku_time
    ON customer_events(sku, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ix_customer_events_type_time
    ON customer_events(event_type_name, occurred_at DESC);

CREATE INDEX IF NOT EXISTS ix_customer_events_event_hash
    ON customer_events(event_hash);
