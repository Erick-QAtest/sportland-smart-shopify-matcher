CREATE TABLE IF NOT EXISTS demand_intents (
    intent_id BIGSERIAL PRIMARY KEY,
    source_event_id BIGINT UNIQUE
        REFERENCES customer_events(event_id) ON DELETE SET NULL,
    customer_id BIGINT REFERENCES customers(customer_id) ON DELETE SET NULL,
    client_uuid TEXT,
    shopify_product_id TEXT,
    shopify_variant_id TEXT,
    smart_sku TEXT,
    resolved_sku TEXT,
    requested_size TEXT,
    match_status TEXT,
    match_confidence TEXT,
    state TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (state IN (
            'OPEN',
            'AVAILABLE',
            'WAITING_STOCK',
            'RESTOCK_MATCH',
            'PURCHASED',
            'EXPIRED',
            'UNRESOLVED'
        )),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_demand_intents_state_variant
    ON demand_intents(state, shopify_variant_id);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL,
    shopify_product_id TEXT,
    shopify_variant_id TEXT NOT NULL,
    sku TEXT,
    inventory_quantity INTEGER NOT NULL,
    price NUMERIC(14,2),
    compare_at_price NUMERIC(14,2),
    source TEXT NOT NULL DEFAULT 'shopify',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (shopify_variant_id, captured_at)
);

CREATE INDEX IF NOT EXISTS ix_inventory_snapshots_variant_time
    ON inventory_snapshots(shopify_variant_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS decision_history (
    decision_id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id TEXT,
    sku TEXT,
    shopify_product_id TEXT,
    action TEXT NOT NULL,
    reason TEXT,
    behavior_score NUMERIC(14,4),
    demand_score NUMERIC(14,4),
    conversion_score NUMERIC(14,4),
    finance_health NUMERIC(8,2),
    finance_state TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_decision_history_sku_time
    ON decision_history(sku, captured_at DESC);
