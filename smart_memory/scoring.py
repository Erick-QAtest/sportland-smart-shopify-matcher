from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb


SCORE_VERSION = "opportunity-v3.4.0"

PURCHASE_EVENTS = {
    "COMPRA",
    "COMPRA_TIENDA_FISICA",
    "COMPRA_ECOMMERCE",
    "COMPRA_MARKETPLACE",
}
COMMITMENT_EVENTS = {
    "APARTADO",
    "ABONO_APARTADO",
    "LIQUIDACION_APARTADO",
}
POSITIVE_EVENTS = {"REVIEW_POSITIVA"}
NEGATIVE_EVENTS = {
    "EVENTO_NEGATIVO",
    "REVIEW_NEGATIVA",
    "SALIDA_COMUNIDAD_WHATSAPP",
}
SILENCE_EVENTS = {"SILENCIO_PROLONGADO"}


@dataclass(frozen=True)
class OpportunityScore:
    score: float
    priority_band: str
    fit: float
    intent: float
    opportunity: float
    value: float
    trust: float
    penalty: float

    def breakdown(self) -> dict[str, float]:
        return {
            "fit": self.fit,
            "intent": self.intent,
            "opportunity": self.opportunity,
            "value": self.value,
            "trust": self.trust,
            "penalty": self.penalty,
            "total": self.score,
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_days(value: datetime | None, as_of: datetime) -> int | None:
    value = _aware(value)
    if value is None:
        return None
    return max(0, (as_of - value).days)


def _event_rows(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in events]


def _has_event_within(
    events: list[dict[str, Any]],
    names: set[str],
    *,
    days: int,
    as_of: datetime,
) -> bool:
    for row in events:
        name = str(row.get("event_type_name") or "").strip().upper()
        if name not in names:
            continue
        age = _age_days(row.get("occurred_at"), as_of)
        if age is not None and age <= days:
            return True
    return False


def _count_events_within(
    events: list[dict[str, Any]],
    names: set[str],
    *,
    days: int,
    as_of: datetime,
) -> int:
    total = 0
    for row in events:
        name = str(row.get("event_type_name") or "").strip().upper()
        if name not in names:
            continue
        age = _age_days(row.get("occurred_at"), as_of)
        if age is not None and age <= days:
            total += 1
    return total


def priority_for(action: str, score: float) -> str:
    action = str(action or "").strip().upper()
    if action == "HOLD":
        return "HOLD"
    if action == "DEMAND_SIGNAL_ONLY":
        return "SIGNAL"
    if score >= 75:
        return "HIGH"
    if score >= 55:
        return "MEDIUM"
    return "LOW"


def calculate_opportunity_score(
    *,
    action: str,
    source_state: str,
    source_event_at: datetime | None,
    requested_size: str | None,
    resolved_sku: str | None,
    shopify_variant_id: str | None,
    current_stock: int | None,
    client_uuid: str | None,
    events: Iterable[dict[str, Any]],
    as_of: datetime | None = None,
) -> OpportunityScore:
    now = _aware(as_of) or datetime.now(timezone.utc)
    rows = _event_rows(events)

    # FIT — how specifically the demand is resolved.
    fit = 0.0
    if str(resolved_sku or "").strip():
        fit += 5.0
    if str(shopify_variant_id or "").strip():
        fit += 5.0
    if str(requested_size or "").strip():
        fit += 5.0
    requested = str(requested_size or "").strip()
    if requested and any(str(row.get("size") or "").strip() == requested for row in rows):
        fit += 5.0

    # INTENT — restock context + original demand recency.
    intent = 10.0 if str(source_state or "").upper() == "RESTOCK_MATCH" else 0.0
    age = _age_days(source_event_at, now)
    if age is None:
        intent += 5.0
    elif age <= 7:
        intent += 20.0
    elif age <= 30:
        intent += 15.0
    elif age <= 60:
        intent += 8.0
    else:
        intent += 3.0

    # OPPORTUNITY — sellable stock exists now, with extra urgency when scarce.
    opportunity = 0.0
    if current_stock is not None and current_stock > 0:
        opportunity += 15.0
        if current_stock <= 3:
            opportunity += 5.0
    if str(source_state or "").upper() == "RESTOCK_MATCH":
        opportunity += 5.0

    # VALUE — prior commercial commitment/conversion.
    value = 0.0
    if _has_event_within(rows, PURCHASE_EVENTS, days=365, as_of=now):
        value += 8.0
    value += min(
        4.0,
        2.0 * _count_events_within(
            rows, COMMITMENT_EVENTS, days=365, as_of=now
        ),
    )
    if _has_event_within(rows, POSITIVE_EVENTS, days=365, as_of=now):
        value += 3.0
    value = min(value, 15.0)

    # TRUST — durable identity plus observed history.
    trust = 0.0
    if str(client_uuid or "").strip():
        trust += 5.0
    if len(rows) >= 2:
        trust += 3.0
    if len(rows) >= 5:
        trust += 2.0

    # PENALTIES — commercial risk; contactability gates remain authoritative.
    penalty = 0.0
    if _has_event_within(rows, NEGATIVE_EVENTS, days=30, as_of=now):
        penalty -= 15.0
    if _has_event_within(rows, SILENCE_EVENTS, days=14, as_of=now):
        penalty -= 5.0

    total = max(
        0.0,
        min(100.0, fit + intent + opportunity + value + trust + penalty),
    )
    total = round(total, 2)
    band = priority_for(action, total)

    return OpportunityScore(
        score=total,
        priority_band=band,
        fit=fit,
        intent=intent,
        opportunity=opportunity,
        value=value,
        trust=trust,
        penalty=penalty,
    )


def _latest_inventory(
    conn: Connection,
    variant_id: str | None,
) -> int | None:
    variant_id = str(variant_id or "").strip()
    if not variant_id:
        return None
    row = conn.execute(
        """
        SELECT inventory_quantity
        FROM inventory_snapshots
        WHERE shopify_variant_id = %s
        ORDER BY captured_at DESC, snapshot_id DESC
        LIMIT 1
        """,
        (variant_id,),
    ).fetchone()
    if not row:
        return None
    return int(row["inventory_quantity"])


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


def score_commercial_opportunities(
    conn: Connection,
    *,
    as_of: datetime | None = None,
) -> dict[str, int]:
    scored_at = _aware(as_of) or datetime.now(timezone.utc)

    rows = conn.execute(
        """
        SELECT
            co.opportunity_id,
            co.intent_id,
            co.customer_id,
            co.client_uuid,
            co.action,
            co.source_state,
            di.source_event_id,
            di.shopify_variant_id,
            di.resolved_sku,
            di.requested_size,
            ce.occurred_at AS source_event_at
        FROM commercial_opportunities co
        JOIN demand_intents di ON di.intent_id = co.intent_id
        LEFT JOIN customer_events ce ON ce.event_id = di.source_event_id
        WHERE co.lifecycle_status = 'OPEN'
        ORDER BY co.opportunity_id
        """
    ).fetchall()

    stats = {
        "opportunities": len(rows),
        "scored": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "hold": 0,
        "signal": 0,
        "decision_rows_inserted": 0,
    }

    with conn.transaction():
        for raw in rows:
            row = dict(raw)
            events = _customer_events(
                conn,
                customer_id=row["customer_id"],
                client_uuid=row["client_uuid"],
            )
            stock = _latest_inventory(conn, row["shopify_variant_id"])

            result = calculate_opportunity_score(
                action=row["action"],
                source_state=row["source_state"],
                source_event_at=row["source_event_at"],
                requested_size=row["requested_size"],
                resolved_sku=row["resolved_sku"],
                shopify_variant_id=row["shopify_variant_id"],
                current_stock=stock,
                client_uuid=row["client_uuid"],
                events=events,
                as_of=scored_at,
            )

            conn.execute(
                """
                UPDATE commercial_opportunities
                SET
                    opportunity_score = %s,
                    priority_band = %s,
                    score_version = %s,
                    scored_at = %s,
                    score_breakdown = %s
                WHERE opportunity_id = %s
                """,
                (
                    result.score,
                    result.priority_band,
                    SCORE_VERSION,
                    scored_at,
                    Jsonb(result.breakdown()),
                    row["opportunity_id"],
                ),
            )

            stats["scored"] += 1
            stats[result.priority_band.lower()] += 1

            decision_key = (
                f"score:{row['opportunity_id']}:{SCORE_VERSION}:"
                f"{result.priority_band}:{result.score:.2f}"
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
                    action,
                    reason,
                    metadata
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (decision_key) DO NOTHING
                RETURNING decision_id
                """,
                (
                    decision_key,
                    scored_at,
                    SCORE_VERSION,
                    row["intent_id"],
                    row["opportunity_id"],
                    row["customer_id"],
                    row["client_uuid"],
                    row["resolved_sku"],
                    f"PRIORITY_{result.priority_band}",
                    f"Opportunity score {result.score:.2f}/100",
                    Jsonb({
                        "score": result.score,
                        "priority_band": result.priority_band,
                        "score_version": SCORE_VERSION,
                        "breakdown": result.breakdown(),
                        "commercial_action": row["action"],
                        "automatic_contact": False,
                    }),
                ),
            ).fetchone()
            if inserted:
                stats["decision_rows_inserted"] += 1

    return stats
