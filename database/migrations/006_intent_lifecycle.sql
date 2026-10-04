ALTER TABLE demand_intents
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

ALTER TABLE demand_intents
    ADD COLUMN IF NOT EXISTS lifecycle_version TEXT;

ALTER TABLE demand_intents
    ADD COLUMN IF NOT EXISTS lifecycle_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_demand_intents_state_expires
    ON demand_intents(state, expires_at);

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (lifecycle_status IN ('OPEN', 'CLOSED'));

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

ALTER TABLE commercial_opportunities
    ADD COLUMN IF NOT EXISTS close_reason TEXT;

CREATE INDEX IF NOT EXISTS ix_commercial_opportunities_lifecycle
    ON commercial_opportunities(lifecycle_status, evaluated_at DESC);

DROP VIEW IF EXISTS smart_memory_health_v;

CREATE VIEW smart_memory_health_v AS
SELECT
    (SELECT COUNT(*) FROM customers) AS customers,
    (SELECT COUNT(*) FROM customer_events) AS events,
    (SELECT COUNT(*) FROM customer_events WHERE customer_id IS NULL) AS events_without_customer,
    (SELECT COUNT(*) FROM demand_intents) AS demand_intents,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'WAITING_STOCK') AS waiting_stock,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'RESTOCK_MATCH') AS restock_matches,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'PURCHASED') AS purchased_intents,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'EXPIRED') AS expired_intents,
    (SELECT COUNT(*) FROM commercial_opportunities) AS commercial_opportunities,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE lifecycle_status = 'OPEN') AS open_commercial_opportunities,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE lifecycle_status = 'CLOSED') AS closed_commercial_opportunities,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE lifecycle_status = 'OPEN' AND action = 'CONTACT_CANDIDATE') AS contact_candidates,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE lifecycle_status = 'OPEN' AND action = 'HOLD') AS opportunities_on_hold,
    (SELECT COUNT(*) FROM commercial_opportunities WHERE lifecycle_status = 'OPEN' AND action = 'DEMAND_SIGNAL_ONLY') AS demand_signal_only,
    (SELECT MAX(occurred_at) FROM customer_events) AS latest_event_at,
    (SELECT MAX(captured_at) FROM inventory_snapshots) AS latest_inventory_snapshot_at,
    (SELECT MAX(captured_at) FROM decision_history) AS latest_decision_at;
