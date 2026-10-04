from datetime import datetime, timedelta, timezone

from smart_memory.scoring import (
    calculate_opportunity_score,
    priority_for,
)


NOW = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)


def ev(name: str, days_ago: int, size: str = "") -> dict:
    return {
        "event_type_name": name,
        "occurred_at": NOW - timedelta(days=days_ago),
        "size": size,
    }


def base(**overrides):
    args = dict(
        action="CONTACT_CANDIDATE",
        source_state="RESTOCK_MATCH",
        source_event_at=NOW - timedelta(days=2),
        requested_size="27",
        resolved_sku="2072-27",
        shopify_variant_id="gid://shopify/ProductVariant/1",
        current_stock=2,
        client_uuid="client-1",
        events=[
            ev("PREGUNTA_TALLA_PRECIO", 2, "27"),
            ev("DM_ACTIVO", 1, "27"),
        ],
        as_of=NOW,
    )
    args.update(overrides)
    return args


def test_high_priority_candidate():
    result = calculate_opportunity_score(**base())
    assert result.score >= 75
    assert result.priority_band == "HIGH"


def test_signal_is_never_contact_priority():
    result = calculate_opportunity_score(
        **base(action="DEMAND_SIGNAL_ONLY", client_uuid=None, events=[])
    )
    assert result.priority_band == "SIGNAL"


def test_hold_is_never_contact_priority():
    result = calculate_opportunity_score(**base(action="HOLD"))
    assert result.priority_band == "HOLD"


def test_negative_signal_reduces_score():
    normal = calculate_opportunity_score(**base())
    negative = calculate_opportunity_score(
        **base(events=base()["events"] + [ev("EVENTO_NEGATIVO", 1)])
    )
    assert negative.score < normal.score
    assert negative.penalty == -15.0


def test_old_intent_scores_lower_than_recent():
    recent = calculate_opportunity_score(**base())
    old = calculate_opportunity_score(
        **base(source_event_at=NOW - timedelta(days=120))
    )
    assert old.score < recent.score


def test_no_stock_reduces_opportunity_component():
    in_stock = calculate_opportunity_score(**base())
    no_stock = calculate_opportunity_score(**base(current_stock=0))
    assert no_stock.opportunity < in_stock.opportunity


def test_purchase_history_adds_value():
    without_purchase = calculate_opportunity_score(**base())
    with_purchase = calculate_opportunity_score(
        **base(events=base()["events"] + [ev("COMPRA_ECOMMERCE", 60)])
    )
    assert with_purchase.value > without_purchase.value


def test_priority_thresholds():
    assert priority_for("CONTACT_CANDIDATE", 75) == "HIGH"
    assert priority_for("CONTACT_CANDIDATE", 55) == "MEDIUM"
    assert priority_for("CONTACT_CANDIDATE", 54.99) == "LOW"
