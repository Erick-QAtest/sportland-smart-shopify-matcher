from datetime import datetime, timedelta, timezone

from smart_memory.lifecycle import (
    LifecycleRules,
    expiration_at,
    lifecycle_reference_at,
    purchase_matches_intent,
    should_expire,
)


NOW = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)


def purchase(*, sku="2072-27", size="27", days_after=2):
    return {
        "event_type_name": "COMPRA_ECOMMERCE",
        "occurred_at": NOW + timedelta(days=days_after),
        "sku": sku,
        "size": size,
    }


def test_waiting_stock_expires_after_90_days():
    opened = NOW - timedelta(days=91)
    assert should_expire(
        state="WAITING_STOCK",
        source_event_at=opened,
        opened_at=opened,
        as_of=NOW,
    ) is True


def test_waiting_stock_stays_active_before_90_days():
    opened = NOW - timedelta(days=89)
    assert should_expire(
        state="WAITING_STOCK",
        source_event_at=opened,
        opened_at=opened,
        as_of=NOW,
    ) is False


def test_restock_uses_restock_timestamp_as_reference():
    source = NOW - timedelta(days=100)
    restock = NOW - timedelta(days=3)
    ref = lifecycle_reference_at(
        state="RESTOCK_MATCH",
        source_event_at=source,
        opened_at=source,
        metadata={"restock_detected_at": restock.isoformat()},
    )
    assert ref == restock


def test_restock_match_expires_after_14_days_from_restock():
    source = NOW - timedelta(days=100)
    restock = NOW - timedelta(days=15)
    assert should_expire(
        state="RESTOCK_MATCH",
        source_event_at=source,
        opened_at=source,
        metadata={"restock_detected_at": restock.isoformat()},
        as_of=NOW,
    ) is True


def test_unresolved_expiry_is_30_days():
    opened = NOW
    expires = expiration_at(
        state="UNRESOLVED",
        source_event_at=opened,
        opened_at=opened,
        rules=LifecycleRules(),
    )
    assert expires == opened + timedelta(days=30)


def test_matching_purchase_closes_intent():
    event = purchase()
    assert purchase_matches_intent(
        event,
        candidate_skus=["2072-27", "2072-26"],
        requested_size="27",
        intent_started_at=NOW,
    ) is True


def test_wrong_sku_does_not_close_intent():
    event = purchase(sku="OTHER-27")
    assert purchase_matches_intent(
        event,
        candidate_skus=["2072-27", "2072-26"],
        requested_size="27",
        intent_started_at=NOW,
    ) is False


def test_purchase_before_intent_does_not_close_intent():
    event = purchase(days_after=-1)
    assert purchase_matches_intent(
        event,
        candidate_skus=["2072-27"],
        requested_size="27",
        intent_started_at=NOW,
    ) is False


def test_conflicting_purchase_size_does_not_close_intent():
    event = purchase(size="26")
    assert purchase_matches_intent(
        event,
        candidate_skus=["2072-27"],
        requested_size="27",
        intent_started_at=NOW,
    ) is False


def test_purchase_without_sku_does_not_close_intent():
    event = purchase(sku="")
    assert purchase_matches_intent(
        event,
        candidate_skus=["2072-27"],
        requested_size="27",
        intent_started_at=NOW,
    ) is False
