from datetime import datetime, timedelta, timezone

from smart_memory.commercial import evaluate_contactability


NOW = datetime(2026, 10, 4, 17, 0, tzinfo=timezone.utc)


def event(name: str, days_ago: int) -> dict:
    return {
        "event_type_name": name,
        "occurred_at": NOW - timedelta(days=days_ago),
    }


def test_missing_identity_is_demand_signal_only():
    result = evaluate_contactability(
        client_uuid=None,
        customer_id=None,
        events=[],
        as_of=NOW,
    )
    assert result.action == "DEMAND_SIGNAL_ONLY"
    assert result.eligible_for_contact is False
    assert result.reason_code == "NO_CLIENT_IDENTITY"


def test_unresolved_customer_is_hold():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=None,
        events=[],
        as_of=NOW,
    )
    assert result.action == "HOLD"
    assert result.reason_code == "CUSTOMER_NOT_RESOLVED"


def test_recent_negative_is_hold():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=1,
        events=[event("EVENTO_NEGATIVO", 2)],
        as_of=NOW,
    )
    assert result.action == "HOLD"
    assert result.reason_code == "RECENT_NEGATIVE_SIGNAL"


def test_recent_purchase_is_cooldown():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=1,
        events=[event("COMPRA_ECOMMERCE", 2)],
        as_of=NOW,
    )
    assert result.action == "HOLD"
    assert result.reason_code == "RECENT_PURCHASE_COOLDOWN"


def test_recent_silence_is_hold():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=1,
        events=[event("SILENCIO_PROLONGADO", 3)],
        as_of=NOW,
    )
    assert result.action == "HOLD"
    assert result.reason_code == "RECENT_SILENCE"


def test_old_negative_does_not_block_candidate():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=1,
        events=[event("EVENTO_NEGATIVO", 45)],
        as_of=NOW,
    )
    assert result.action == "CONTACT_CANDIDATE"
    assert result.eligible_for_contact is True


def test_identified_customer_without_gate_is_candidate():
    result = evaluate_contactability(
        client_uuid="client-123",
        customer_id=1,
        events=[event("PREGUNTA_TALLA_PRECIO", 1)],
        as_of=NOW,
    )
    assert result.action == "CONTACT_CANDIDATE"
    assert result.reason_code == "IDENTIFIED_NO_ACTIVE_GATE"
