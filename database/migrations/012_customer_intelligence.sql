ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS shopify_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS first_name TEXT,
    ADD COLUMN IF NOT EXISTS last_name TEXT,
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS shopify_orders_count INTEGER,
    ADD COLUMN IF NOT EXISTS shopify_total_spent NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS shopify_currency TEXT,
    ADD COLUMN IF NOT EXISTS last_shopify_sync_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS preferred_size TEXT,
    ADD COLUMN IF NOT EXISTS last_purchase_size TEXT,
    ADD COLUMN IF NOT EXISTS size_confidence NUMERIC(6,4),
    ADD COLUMN IF NOT EXISTS size_confidence_band TEXT,
    ADD COLUMN IF NOT EXISTS size_observation_count INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_shopify_customer_id
    ON customers(shopify_customer_id)
    WHERE shopify_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_customers_phone_e164
    ON customers(phone_e164) WHERE phone_e164 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_customers_email_lower
    ON customers(lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS customer_identity_aliases (
    alias_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    alias_type TEXT NOT NULL CHECK (alias_type IN ('CLIENT_UUID','SHOPIFY_CUSTOMER_ID')),
    alias_value TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(alias_type, alias_value)
);
CREATE INDEX IF NOT EXISTS ix_customer_identity_aliases_customer ON customer_identity_aliases(customer_id);

CREATE TABLE IF NOT EXISTS customer_sync_runs (
    sync_run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING','OK','FAILED')),
    mode TEXT NOT NULL CHECK (mode IN ('FULL','INCREMENTAL')),
    since_at TIMESTAMPTZ,
    customers_read INTEGER NOT NULL DEFAULT 0,
    orders_read INTEGER NOT NULL DEFAULT 0,
    purchase_items_read INTEGER NOT NULL DEFAULT 0,
    customers_inserted INTEGER NOT NULL DEFAULT 0,
    customers_updated INTEGER NOT NULL DEFAULT 0,
    purchase_items_inserted INTEGER NOT NULL DEFAULT 0,
    purchase_items_updated INTEGER NOT NULL DEFAULT 0,
    purchase_events_inserted INTEGER NOT NULL DEFAULT 0,
    size_profiles_updated INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS customer_purchase_items (
    purchase_item_id BIGSERIAL PRIMARY KEY,
    shopify_line_item_id TEXT NOT NULL UNIQUE,
    shopify_order_id TEXT NOT NULL,
    shopify_order_name TEXT,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    shopify_product_id TEXT,
    shopify_variant_id TEXT,
    sku TEXT,
    product_title TEXT,
    brand TEXT,
    variant_title TEXT,
    size TEXT,
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_price NUMERIC(14,2),
    currency TEXT,
    purchased_at TIMESTAMPTZ NOT NULL,
    order_updated_at TIMESTAMPTZ,
    cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT NOT NULL DEFAULT 'shopify',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_customer_purchase_items_customer_time ON customer_purchase_items(customer_id,purchased_at DESC);
CREATE INDEX IF NOT EXISTS ix_customer_purchase_items_customer_size ON customer_purchase_items(customer_id,size) WHERE size IS NOT NULL AND quantity > 0 AND cancelled = FALSE;
CREATE INDEX IF NOT EXISTS ix_customer_purchase_items_brand_size ON customer_purchase_items(customer_id,brand,size) WHERE size IS NOT NULL AND quantity > 0 AND cancelled = FALSE;

CREATE TABLE IF NOT EXISTS customer_size_profiles (
    customer_id BIGINT PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    preferred_size TEXT,
    last_purchase_size TEXT,
    observation_count INTEGER NOT NULL DEFAULT 0,
    unique_sizes INTEGER NOT NULL DEFAULT 0,
    confidence NUMERIC(6,4),
    confidence_band TEXT CHECK (confidence_band IN ('HIGH','MEDIUM','LOW','NONE')),
    first_observed_at TIMESTAMPTZ,
    last_observed_at TIMESTAMPTZ,
    size_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customer_brand_size_profiles (
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    brand TEXT NOT NULL,
    preferred_size TEXT,
    last_purchase_size TEXT,
    observation_count INTEGER NOT NULL DEFAULT 0,
    unique_sizes INTEGER NOT NULL DEFAULT 0,
    confidence NUMERIC(6,4),
    confidence_band TEXT CHECK (confidence_band IN ('HIGH','MEDIUM','LOW','NONE')),
    size_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_observed_at TIMESTAMPTZ,
    last_observed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(customer_id,brand)
);

CREATE OR REPLACE VIEW customer_size_intelligence_v AS
SELECT c.customer_id,c.shopify_customer_id,c.client_uuid,c.preferred_size,c.last_purchase_size,
       c.size_confidence,c.size_confidence_band,c.size_observation_count,c.shopify_orders_count,
       c.shopify_total_spent,c.shopify_currency,c.last_shopify_sync_at,sp.unique_sizes,sp.size_counts,
       sp.first_observed_at,sp.last_observed_at
FROM customers c LEFT JOIN customer_size_profiles sp ON sp.customer_id=c.customer_id;

CREATE OR REPLACE VIEW customer_brand_size_intelligence_v AS
SELECT c.customer_id,c.client_uuid,c.shopify_customer_id,bp.brand,bp.preferred_size,bp.last_purchase_size,
       bp.observation_count,bp.unique_sizes,bp.confidence,bp.confidence_band,bp.size_counts,
       bp.first_observed_at,bp.last_observed_at
FROM customer_brand_size_profiles bp JOIN customers c ON c.customer_id=bp.customer_id;
