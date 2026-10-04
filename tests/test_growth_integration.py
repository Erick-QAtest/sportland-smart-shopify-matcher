from smart_growth.planner import (
    actions_from_behavior_decisions,
    actions_from_commercial_opportunities,
    dedupe_actions,
)


def row(action: str, **extra):
    base = {
        "action": action,
        "sku": "TEST-27",
        "product_key": "title:test",
        "product_title": "Test Shoe",
        "priority": "P1",
        "inventory_quantity": "2",
        "conversion_score": "2",
        "history_demand_score": "2",
    }
    base.update(extra)
    return base


def test_sell_now_routes_to_meta_and_whatsapp():
    actions = actions_from_behavior_decisions([row("VENDER_AHORA")])
    assert {a.channel for a in actions} == {"META", "WHATSAPP"}
    assert all(a.activation_mode == "MANUAL_REVIEW" for a in actions)


def test_protect_stock_avoids_paid_meta_activation():
    actions = actions_from_behavior_decisions([row("PROTEGER_STOCK")])
    assert {a.channel for a in actions} == {"GOOGLE_SEO", "YOUTUBE"}
    assert "META" not in {a.channel for a in actions}


def test_liquidation_routes_to_review_not_auto_activation():
    actions = actions_from_behavior_decisions([row("LIQUIDAR_VARIANTE")])
    assert {a.channel for a in actions} == {"META", "WHATSAPP"}
    assert all(a.metadata["automatic_activation"] is False for a in actions)


def test_review_variant_generates_search_review_only():
    actions = actions_from_behavior_decisions([row("REVISAR_VARIANTE")])
    assert len(actions) == 1
    assert actions[0].channel == "GOOGLE_SEO"
    assert actions[0].objective == "SEARCH_DEMAND_REVIEW"


def test_lost_demand_generates_signal_not_paid_sale():
    actions = actions_from_behavior_decisions([row("DEMANDA_PERDIDA")])
    assert len(actions) == 1
    assert actions[0].priority_band == "SIGNAL"
    assert actions[0].channel == "GOOGLE_SEO"


def test_contact_candidate_becomes_whatsapp_review_without_identity():
    actions = actions_from_commercial_opportunities([{
        "opportunity_id": 10,
        "action": "CONTACT_CANDIDATE",
        "priority_band": "HIGH",
        "lifecycle_status": "OPEN",
        "sku": "TEST-27",
    }])
    assert len(actions) == 1
    item = actions[0]
    assert item.channel == "WHATSAPP"
    assert item.activation_mode == "INDIVIDUAL_REVIEW"
    assert "client_uuid" not in item.metadata


def test_demand_signal_only_stays_aggregate():
    actions = actions_from_commercial_opportunities([{
        "opportunity_id": 11,
        "action": "DEMAND_SIGNAL_ONLY",
        "priority_band": "SIGNAL",
        "lifecycle_status": "OPEN",
        "sku": "TEST-27",
    }])
    assert len(actions) == 1
    assert actions[0].channel == "META"
    assert actions[0].objective == "AGGREGATE_AUDIENCE_SIGNAL"


def test_hold_opportunity_creates_no_growth_action():
    actions = actions_from_commercial_opportunities([{
        "opportunity_id": 12,
        "action": "HOLD",
        "priority_band": "HOLD",
        "lifecycle_status": "OPEN",
        "sku": "TEST-27",
    }])
    assert actions == []


def test_dedupe_is_idempotent():
    original = actions_from_behavior_decisions([row("VENDER_AHORA")])
    doubled = dedupe_actions(original + original)
    assert len(doubled) == len(original)
