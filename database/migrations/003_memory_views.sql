CREATE OR REPLACE VIEW customer_profile_v AS
SELECT
    c.customer_id,
    c.client_uuid,
    c.first_seen_at,
    c.last_seen_at,
    c.first_channel,
    c.current_stage,
    MAX(e.occurred_at) FILTER (
        WHERE e.event_type_name IN (
            'COMPRA',
            'COMPRA_TIENDA_FISICA',
            'COMPRA_ECOMMERCE',
            'COMPRA_MARKETPLACE'
        )
    ) AS last_purchase_at,
    COUNT(*) FILTER (
        WHERE e.event_type_name IN (
            'COMPRA',
            'COMPRA_TIENDA_FISICA',
            'COMPRA_ECOMMERCE',
            'COMPRA_MARKETPLACE'
        )
    ) AS purchase_events,
    COALESCE(SUM(e.amount) FILTER (
        WHERE e.event_type_name IN (
            'COMPRA',
            'COMPRA_TIENDA_FISICA',
            'COMPRA_ECOMMERCE',
            'COMPRA_MARKETPLACE'
        )
    ), 0) AS observed_purchase_value,
    AVG(e.amount) FILTER (
        WHERE e.event_type_name IN (
            'COMPRA',
            'COMPRA_TIENDA_FISICA',
            'COMPRA_ECOMMERCE',
            'COMPRA_MARKETPLACE'
        )
    ) AS average_observed_ticket,
    ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(e.size, '')), NULL) AS observed_sizes,
    ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(e.channel, '')), NULL) AS observed_channels
FROM customers c
LEFT JOIN customer_events e ON e.customer_id = c.customer_id
GROUP BY
    c.customer_id,
    c.client_uuid,
    c.first_seen_at,
    c.last_seen_at,
    c.first_channel,
    c.current_stage;

CREATE OR REPLACE VIEW smart_memory_health_v AS
SELECT
    (SELECT COUNT(*) FROM customers) AS customers,
    (SELECT COUNT(*) FROM customer_events) AS events,
    (SELECT COUNT(*) FROM customer_events WHERE customer_id IS NULL) AS events_without_customer,
    (SELECT COUNT(*) FROM demand_intents) AS demand_intents,
    (SELECT COUNT(*) FROM demand_intents WHERE state = 'WAITING_STOCK') AS waiting_stock,
    (SELECT MAX(occurred_at) FROM customer_events) AS latest_event_at,
    (SELECT MAX(captured_at) FROM inventory_snapshots) AS latest_inventory_snapshot_at,
    (SELECT MAX(captured_at) FROM decision_history) AS latest_decision_at;
