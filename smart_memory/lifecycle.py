from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb


LIFECYCLE_VERSION = "intent-lifecycle-v3.5.0"

ACTIVE_STATES = {
    "OPEN",
    "AVAILABLE",
    "WAITING_STOCK",
    "RESTOCK_MATCH",
    "UNRESOLVED",
}

PURCHASE_EVENTS = {
    "COMPRA",
    "COMPRA_TIENDA_FISICA",
    "COMPRA_ECOMMERCE",
    "COMPRA_MARKETPLACE",
}


@dataclass(frozen=True)
class LifecycleRules:
    open_days: int = 30
    available_days: int = 30
    waiting_stock_days: int = 90
    restock_match_days: int = 14
    unresolved_days: int = 30

    def days_for(self, state: str) -> int | None:
        return {
            "OPEN": self.open_days,
            "AVAILABLE": self.available_days,
            "WAITING_STOCK": self.waiting_stock_days,
            "RESTOCK_MATCH": self.restock_match_days,
            "UNRESOLVED": self.unresolved_days,
        }.get(str(state or "").strip().upper())


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


def lifecycle_reference_at(
    *,
    state: str,
    source_event_at: datetime | None,
    opened_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> datetime:
    state = str(state or "").strip().upper()
    metadata = metadata or {}

    if state == "RESTOCK_MATCH":
        restock_at = _parse_dt(metadata.get("restock_detected_at"))
        if restock_at is not None:
            return restock_at

    return _aware(source_event_at) or _aware(opened_at) or datetime.now(timezone.utc)


def expiration_at(
    *,
    state: str,
    source_event_at: datetime | None,
    opened_at: datetime,
    metadata: dict[str, Any] | None = None,
    rules: LifecycleRules | None = None,
) -> datetime | None:
    rules = rules or LifecycleRules()
    days = rules.days_for(state)
    if days is None:
        return None
    reference = lifecycle_reference_at(
        state=state,
        source_event_at=source_event_at,
        opened_at=opened_at,
        metadata=metadata,
    )
    return reference + timedelta(days=days)


def should_expire(
    *,
    state: str,
    source_event_at: datetime | None,
    opened_at: datetime,
    metadata: dict[str, Any] | None = None,
    as_of: datetime | None = None,
    rules: LifecycleRules | None = None,
) -> bool:
    now = _aware(as_of) or datetime.now(timezone.utc)
    expires = expiration_at(
        state=state,
        source_event_at=source_event_at,
        opened_at=opened_at,
        metadata=metadata,
        rules=rules,
    )
    return expires is not None and now >= expires


def purchase_matches_intent(
    event: dict[str, Any],
    *,
    candidate_skus: Iterable[str],
    requested_size: str | None,
    intent_started_at: datetime,
) -> bool:
    event_type = str(event.get("event_type_name") or "").strip().upper()
    if event_type not in PURCHASE_EVENTS:
        return False

    occurred_at = _parse_dt(event.get("occurred_at"))
    started_at = _aware(intent_started_at)
    if occurred_at is None or started_at is None or occurred_at < started_at:
        return False

    purchase_sku = str(event.get("sku") or "").strip().upper()
    if not purchase_sku:
        return False

    candidates = {
        str(sku or "").strip().upper()
        for sku in candidate_skus
        if str(sku or "").strip()
    }
    if purchase_sku not in candidates:
        return False

    wanted_size = str(requested_size or "").strip()
    bought_size = str(event.get("size") or "").strip()
    if wanted_size and bought_size and wanted_size != bought_size:
        return False

    return True


def _purchase_events_for_intent(
    conn: Connection,
    *,
    customer_id: int | None,
    client_uuid: str | None,
    started_at: datetime,
) -> list[dict[str, Any]]:
    identity = str(client_uuid or "").strip() or None
    if customer_id is None and identity is None:
        return []

    rows = conn.execute(
        """
        SELECT event_id, event_type_name, occurred_at, sku, size, amount, channel
        FROM customer_events
        WHERE event_type_name IN (
            'COMPRA',
            'COMPRA_TIENDA_FISICA',
            'COMPRA_ECOMMERCE',
            'COMPRA_MARKETPLACE'
        )
          AND occurred_at IS NOT NULL
          AND occurred_at >= %s
          AND (
              (%s::bigint IS NOT NULL AND customer_id = %s)
              OR
              (%s::text IS NOT NULL AND client_uuid = %s)
          )
        ORDER BY occurred_at ASC, event_id ASC
        """,
        (started_at, customer_id, customer_id, identity, identity),
    ).fetchall()
    return [dict(row) for row in rows]


def _append_resolution(
    conn: Connection,
    *,
    intent_id: int,
    state: str,
    resolved_at: datetime,
    expires_at_value: datetime | None,
    message: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE demand_intents
        SET
            state = %s,
            resolved_at = %s,
            expires_at = %s,
            lifecycle_version = %s,
            lifecycle_checked_at = %s,
            resolution = COALESCE(resolution, '') ||
                CASE
                    WHEN COALESCE(resolution, '') = '' THEN ''
                    ELSE ' | '
                END ||
                %s,
            metadata = COALESCE(metadata, '{}'::jsonb) || %s
        WHERE intent_id = %s
        """,
        (
            state,
            resolved_at,
            expires_at_value,
            LIFECYCLE_VERSION,
            resolved_at,
            message,
            Jsonb(metadata),
            intent_id,
        ),
    )


def _close_opportunity(
    conn: Connection,
    *,
    intent_id: int,
    closed_at: datetime,
    reason: str,
) -> int:
    rows = conn.execute(
        """
        UPDATE commercial_opportunities
        SET
            lifecycle_status = 'CLOSED',
            closed_at = %s,
            close_reason = %s,
            eligible_for_contact = FALSE,
            hold_until = NULL
        WHERE intent_id = %s
          AND lifecycle_status = 'OPEN'
        RETURNING opportunity_id
        """,
        (closed_at, reason, intent_id),
    ).fetchall()
    return len(rows)


def process_intent_lifecycle(
    conn: Connection,
    *,
    as_of: datetime | None = None,
    rules: LifecycleRules | None = None,
) -> dict[str, int]:
    now = _aware(as_of) or datetime.now(timezone.utc)
    rules = rules or LifecycleRules()

    intents = conn.execute(
        """
        SELECT
            di.intent_id,
            di.source_event_id,
            di.customer_id,
            di.client_uuid,
            di.smart_sku,
            di.resolved_sku,
            di.requested_size,
            di.state,
            di.opened_at,
            di.metadata,
            ce.occurred_at AS source_event_at
        FROM demand_intents di
        LEFT JOIN customer_events ce ON ce.event_id = di.source_event_id
        WHERE di.state IN (
            'OPEN',
            'AVAILABLE',
            'WAITING_STOCK',
            'RESTOCK_MATCH',
            'UNRESOLVED'
        )
        ORDER BY di.intent_id
        """
    ).fetchall()

    stats = {
        "active_evaluated": len(intents),
        "purchased": 0,
        "expired": 0,
        "still_active": 0,
        "opportunities_closed": 0,
        "decision_rows_inserted": 0,
    }

    with conn.transaction():
        for raw in intents:
            intent = dict(raw)
            state = str(intent["state"] or "").upper()
            metadata = dict(intent["metadata"] or {})
            started_at = (
                _aware(intent["source_event_at"])
                or _aware(intent["opened_at"])
                or now
            )
            expires = expiration_at(
                state=state,
                source_event_at=intent["source_event_at"],
                opened_at=intent["opened_at"],
                metadata=metadata,
                rules=rules,
            )

            # Persist the lifecycle clock even when no transition happens.
            conn.execute(
                """
                UPDATE demand_intents
                SET
                    expires_at = %s,
                    lifecycle_version = %s,
                    lifecycle_checked_at = %s
                WHERE intent_id = %s
                """,
                (expires, LIFECYCLE_VERSION, now, intent["intent_id"]),
            )

            candidate_skus = [intent["resolved_sku"], intent["smart_sku"]]
            purchase_match: dict[str, Any] | None = None

            for event in _purchase_events_for_intent(
                conn,
                customer_id=intent["customer_id"],
                client_uuid=intent["client_uuid"],
                started_at=started_at,
            ):
                if purchase_matches_intent(
                    event,
                    candidate_skus=candidate_skus,
                    requested_size=intent["requested_size"],
                    intent_started_at=started_at,
                ):
                    purchase_match = event
                    break

            target_state: str | None = None
            resolved_at = now
            reason = ""
            decision_key = ""
            decision_metadata: dict[str, Any] = {
                "from_state": state,
                "lifecycle_version": LIFECYCLE_VERSION,
                "automatic_contact": False,
            }

            if purchase_match is not None:
                target_state = "PURCHASED"
                resolved_at = _aware(purchase_match["occurred_at"]) or now
                reason = (
                    "Lifecycle closed intent as PURCHASED after matching "
                    "a purchase for the same identified customer and SKU."
                )
                decision_key = (
                    f"lifecycle:{intent['intent_id']}:PURCHASED:"
                    f"{purchase_match['event_id']}"
                )
                decision_metadata.update({
                    "purchase_event_id": purchase_match["event_id"],
                    "purchase_sku": purchase_match["sku"],
                    "purchase_size": purchase_match["size"],
                })
            elif expires is not None and now >= expires:
                target_state = "EXPIRED"
                reason = (
                    f"Lifecycle expired {state} intent after "
                    f"{rules.days_for(state)} days."
                )
                decision_key = (
                    f"lifecycle:{intent['intent_id']}:EXPIRED:"
                    f"{expires.isoformat()}"
                )
                decision_metadata.update({
                    "expires_at": expires.isoformat(),
                    "expiry_days": rules.days_for(state),
                })

            if target_state is None:
                stats["still_active"] += 1
                continue

            _append_resolution(
                conn,
                intent_id=intent["intent_id"],
                state=target_state,
                resolved_at=resolved_at,
                expires_at_value=expires,
                message=reason,
                metadata={
                    "lifecycle_terminal_state": target_state,
                    "lifecycle_resolved_at": resolved_at.isoformat(),
                },
            )

            closed = _close_opportunity(
                conn,
                intent_id=intent["intent_id"],
                closed_at=resolved_at,
                reason=f"INTENT_{target_state}",
            )
            stats["opportunities_closed"] += closed
            stats["purchased" if target_state == "PURCHASED" else "expired"] += 1

            inserted = conn.execute(
                """
                INSERT INTO decision_history(
                    decision_key,
                    captured_at,
                    run_id,
                    intent_id,
                    customer_id,
                    client_uuid,
                    sku,
                    action,
                    reason,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_key) DO NOTHING
                RETURNING decision_id
                """,
                (
                    decision_key,
                    resolved_at,
                    LIFECYCLE_VERSION,
                    intent["intent_id"],
                    intent["customer_id"],
                    intent["client_uuid"],
                    intent["resolved_sku"] or intent["smart_sku"],
                    f"INTENT_{target_state}",
                    reason,
                    Jsonb(decision_metadata),
                ),
            ).fetchone()
            if inserted:
                stats["decision_rows_inserted"] += 1

    return stats
