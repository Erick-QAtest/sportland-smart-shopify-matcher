CREATE TABLE IF NOT EXISTS commercial_opportunities (
    opportunity_id BIGSERIAL PRIMARY KEY,
    intent_id BIGINT NOT NULL UNIQUE
        REFERENCES demand_intents(intent_id) ON DELETE CASCADE,
    customer_id BIGINT
        REFERENCES customers(customer_id) ON DELETE SET NULL,
    client_uuid TEXT,
    opportunity_type TEXT NOT NULL DEFAULT 'RESTOCK',
    source_state TEXT NOT NULL,
    action TEXT NOT NULL
        CHECK (action IN ('CONTACT_CANDIDATE', 'HOLD', 'DEMAND_SIGNAL_ONLY')),
    eligible_for_contact BOOLEAN NOT NULL DEFAULT FALSE,
    reason_code TEXT NOT NULL,
    reason TEXT,
    hold_until TIMESTAMPTZ,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_commercial_opportunities_action_time
    ON commercial_opportunities(action, evaluated_at DESC);

CREATE INDEX IF NOT EXISTS ix_commercial_opportunities_client
    ON commercial_opportunities(client_uuid, evaluated_at DESC);

ALTER TABLE decision_history
    ADD COLUMN IF NOT EXISTS decision_key TEXT;

ALTER TABLE decision_history
    ADD COLUMN IF NOT EXISTS intent_id BIGINT
        REFERENCES demand_intents(intent_id) ON DELETE SET NULL;

ALTER TABLE decision_history
    ADD COLUMN IF NOT EXISTS opportunity_id BIGINT
        REFERENCES commercial_opportunities(opportunity_id) ON DELETE SET NULL;

ALTER TABLE decision_history
    ADD COLUMN IF NOT EXISTS customer_id BIGINT
        REFERENCES customers(customer_id) ON DELETE SET NULL;

ALTER TABLE decision_history
    ADD COLUMN IF NOT EXISTS client_uuid TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_history_decision_key
    ON decision_history(decision_key);

DROP VIEW IF EXISTS smart_memory_health_v;

CREATE VIEW smart_memory_health_v AS
SELECT
    (SELECT COUNT(*) FROM customers) AS customers,
    (SELECT COUNT(*) FROM customer_events) AS events,
    (SELECT COUNT(*) FROM customer_events WHERE customer_id IS NULL) AS events_without_customer,
    (SELECT COUNT(*) FROM demand_intents) AS demand_intents,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'WAITING_STOCK') AS waiting_stock,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'RESTOCK_MATCH') AS restock_matches,
    (SELECT COUNT(*) FROM commercial_opportunities) AS commercial_opportunities,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE action = 'CONTACT_CANDIDATE') AS contact_candidates,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE action = 'HOLD') AS opportunities_on_hold,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE action = 'DEMAND_SIGNAL_ONLY') AS demand_signal_only,
    (SELECT MAX(occurred_at) FROM customer_events) AS latest_event_at,
    (SELECT MAX(captured_at) FROM inventory_snapshots) AS latest_inventory_snapshot_at,
    (SELECT MAX(captured_at) FROM decision_history) AS latest_decision_at;
