from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb


PURCHASE_EVENTS = {
    "COMPRA",
    "COMPRA_TIENDA_FISICA",
    "COMPRA_ECOMMERCE",
    "COMPRA_MARKETPLACE",
}

NEGATIVE_30D_EVENTS = {
    "EVENTO_NEGATIVO",
    "REVIEW_NEGATIVA",
    "SALIDA_COMUNIDAD_WHATSAPP",
}

SILENCE_EVENTS = {"SILENCIO_PROLONGADO"}


@dataclass(frozen=True)
class ContactDecision:
    action: str
    eligible_for_contact: bool
    reason_code: str
    reason: str
    hold_until: datetime | None = None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_of(
    events: Iterable[dict[str, Any]],
    event_types: set[str],
) -> datetime | None:
    found: list[datetime] = []
    for event in events:
        typ = str(event.get("event_type_name") or "").strip().upper()
        if typ not in event_types:
            continue
        dt = _aware(event.get("occurred_at"))
        if dt is not None:
            found.append(dt)
    return max(found) if found else None


def evaluate_contactability(
    *,
    client_uuid: str | None,
    customer_id: int | None,
    events: Iterable[dict[str, Any]],
    as_of: datetime | None = None,
) -> ContactDecision:
    """Conservative eligibility only. Never sends a message."""
    now = _aware(as_of) or datetime.now(timezone.utc)
    identity = str(client_uuid or "").strip()

    if not identity:
        return ContactDecision(
            action="DEMAND_SIGNAL_ONLY",
            eligible_for_contact=False,
            reason_code="NO_CLIENT_IDENTITY",
            reason="Demand is valid, but there is no client_uuid. Keep as aggregate demand only.",
        )

    if customer_id is None:
        return ContactDecision(
            action="HOLD",
            eligible_for_contact=False,
            reason_code="CUSTOMER_NOT_RESOLVED",
            reason="client_uuid exists, but no durable customer record is resolved yet.",
        )

    rows = list(events)

    latest_negative = _latest_of(rows, NEGATIVE_30D_EVENTS)
    if latest_negative is not None:
        hold_until = latest_negative + timedelta(days=30)
        if now < hold_until:
            return ContactDecision(
                action="HOLD",
                eligible_for_contact=False,
                reason_code="RECENT_NEGATIVE_SIGNAL",
                reason="Recent negative/exit signal activates a 30-day contact hold.",
                hold_until=hold_until,
            )

    latest_purchase = _latest_of(rows, PURCHASE_EVENTS)
    if latest_purchase is not None:
        hold_until = latest_purchase + timedelta(days=7)
        if now < hold_until:
            return ContactDecision(
                action="HOLD",
                eligible_for_contact=False,
                reason_code="RECENT_PURCHASE_COOLDOWN",
                reason="Recent purchase activates a 7-day cooldown.",
                hold_until=hold_until,
            )

    latest_silence = _latest_of(rows, SILENCE_EVENTS)
    if latest_silence is not None:
        hold_until = latest_silence + timedelta(days=14)
        if now < hold_until:
            return ContactDecision(
                action="HOLD",
                eligible_for_contact=False,
                reason_code="RECENT_SILENCE",
                reason="Recent prolonged-silence signal activates a 14-day hold.",
                hold_until=hold_until,
            )

    return ContactDecision(
        action="CONTACT_CANDIDATE",
        eligible_for_contact=True,
        reason_code="IDENTIFIED_NO_ACTIVE_GATE",
        reason=(
            "Identified client and no active safety/contactability gate. "
            "Candidate only; no message is sent automatically."
        ),
    )


def _resolve_customer(
    conn: Connection,
    *,
    customer_id: int | None,
    client_uuid: str | None,
) -> dict[str, Any] | None:
    if customer_id is not None:
        row = conn.execute(
            """
            SELECT customer_id, client_uuid, current_stage
            FROM customers
            WHERE customer_id = %s
            LIMIT 1
            """,
            (customer_id,),
        ).fetchone()
        if row:
            return dict(row)

    identity = str(client_uuid or "").strip()
    if identity:
        row = conn.execute(
            """
            SELECT customer_id, client_uuid, current_stage
            FROM customers
            WHERE client_uuid = %s
            LIMIT 1
            """,
            (identity,),
        ).fetchone()
        if row:
            return dict(row)

    return None


def _customer_events(
    conn: Connection,
    *,
    customer_id: int | None,
    client_uuid: str | None,
) -> list[dict[str, Any]]:
    identity = str(client_uuid or "").strip() or None
    if customer_id is None and identity is None:
        return []

    rows = conn.execute(
        """
        SELECT event_type_name, occurred_at, channel, sku, size
        FROM customer_events
        WHERE (%s::bigint IS NOT NULL AND customer_id = %s)
           OR (%s::text IS NOT NULL AND client_uuid = %s)
        ORDER BY occurred_at DESC NULLS LAST, event_id DESC
        """,
        (customer_id, customer_id, identity, identity),
    ).fetchall()
    return [dict(row) for row in rows]


def evaluate_restock_opportunities(
    conn: Connection,
    *,
    as_of: datetime | None = None,
) -> dict[str, int]:
    evaluated_at = _aware(as_of) or datetime.now(timezone.utc)

    intents = conn.execute(
        """
        SELECT
            intent_id,
            customer_id,
            client_uuid,
            shopify_product_id,
            shopify_variant_id,
            smart_sku,
            resolved_sku,
            requested_size,
            state,
            metadata
        FROM demand_intents
        WHERE state = 'RESTOCK_MATCH'
        ORDER BY intent_id
        """
    ).fetchall()

    stats = {
        "restock_matches": len(intents),
        "contact_candidates": 0,
        "hold": 0,
        "demand_signal_only": 0,
        "opportunities_upserted": 0,
        "decision_rows_inserted": 0,
    }

    with conn.transaction():
        for raw in intents:
            intent = dict(raw)
            customer = _resolve_customer(
                conn,
                customer_id=intent["customer_id"],
                client_uuid=intent["client_uuid"],
            )
            customer_id = customer["customer_id"] if customer else intent["customer_id"]
            client_uuid = (
                (customer["client_uuid"] if customer else None)
                or intent["client_uuid"]
                or None
            )

            events = _customer_events(
                conn,
                customer_id=customer_id,
                client_uuid=client_uuid,
            )
            decision = evaluate_contactability(
                client_uuid=client_uuid,
                customer_id=customer_id,
                events=events,
                as_of=evaluated_at,
            )

            if decision.action == "CONTACT_CANDIDATE":
                stats["contact_candidates"] += 1
            elif decision.action == "HOLD":
                stats["hold"] += 1
            else:
                stats["demand_signal_only"] += 1

            opportunity = conn.execute(
                """
                INSERT INTO commercial_opportunities(
                    intent_id,
                    customer_id,
                    client_uuid,
                    opportunity_type,
                    source_state,
                    action,
                    eligible_for_contact,
                    reason_code,
                    reason,
                    hold_until,
                    evaluated_at,
                    metadata
                )
                VALUES (
                    %s, %s, %s,
                    'RESTOCK', %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (intent_id)
                DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    client_uuid = EXCLUDED.client_uuid,
                    source_state = EXCLUDED.source_state,
                    action = EXCLUDED.action,
                    eligible_for_contact = EXCLUDED.eligible_for_contact,
                    reason_code = EXCLUDED.reason_code,
                    reason = EXCLUDED.reason,
                    hold_until = EXCLUDED.hold_until,
                    evaluated_at = EXCLUDED.evaluated_at,
                    metadata = EXCLUDED.metadata
                RETURNING opportunity_id
                """,
                (
                    intent["intent_id"],
                    customer_id,
                    client_uuid,
                    intent["state"],
                    decision.action,
                    decision.eligible_for_contact,
                    decision.reason_code,
                    decision.reason,
                    decision.hold_until,
                    evaluated_at,
                    Jsonb({
                        "smart_sku": intent["smart_sku"],
                        "resolved_sku": intent["resolved_sku"],
                        "requested_size": intent["requested_size"],
                        "shopify_variant_id": intent["shopify_variant_id"],
                        "automatic_contact": False,
                    }),
                ),
            ).fetchone()
            opportunity_id = opportunity["opportunity_id"]
            stats["opportunities_upserted"] += 1

            decision_key = (
                f"commercial:{intent['intent_id']}:"
                f"{decision.action}:{decision.reason_code}"
            )
            inserted = conn.execute(
                """
                INSERT INTO decision_history(
                    decision_key,
                    captured_at,
                    run_id,
                    intent_id,
                    opportunity_id,
                    customer_id,
                    client_uuid,
                    sku,
                    shopify_product_id,
                    action,
                    reason,
                    metadata
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                ON CONFLICT (decision_key) DO NOTHING
                RETURNING decision_id
                """,
                (
                    decision_key,
                    evaluated_at,
                    "memory-commercial-v3.3",
                    intent["intent_id"],
                    opportunity_id,
                    customer_id,
                    client_uuid,
                    intent["resolved_sku"] or intent["smart_sku"],
                    intent["shopify_product_id"],
                    decision.action,
                    decision.reason,
                    Jsonb({
                        "reason_code": decision.reason_code,
                        "source_state": intent["state"],
                        "eligible_for_contact": decision.eligible_for_contact,
                        "hold_until": (
                            decision.hold_until.isoformat()
                            if decision.hold_until else None
                        ),
                        "automatic_contact": False,
                    }),
                ),
            ).fetchone()
            if inserted:
                stats["decision_rows_inserted"] += 1

    return stats
