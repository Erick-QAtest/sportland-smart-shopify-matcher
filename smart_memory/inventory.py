from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb

from sportland_matcher.shopify_source import ShopifyVariant


@dataclass(frozen=True)
class RestockTransition:
    shopify_variant_id: str
    sku: str
    previous_quantity: int
    current_quantity: int


def is_restock(previous_quantity: int | None, current_quantity: int) -> bool:
    """A restock is a known transition from zero-or-less to positive stock."""
    return previous_quantity is not None and previous_quantity <= 0 and current_quantity > 0


def _decimal_or_none(value: str | None) -> Decimal | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _latest_quantity(conn: Connection, variant_id: str) -> int | None:
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


def capture_inventory(
    conn: Connection,
    variants: Iterable[ShopifyVariant],
    *,
    captured_at: datetime | None = None,
) -> tuple[dict[str, int], list[RestockTransition]]:
    variants = list(variants)
    captured_at = captured_at or datetime.now(timezone.utc)

    stats = {
        "variants": len(variants),
        "snapshots_inserted": 0,
        "restock_transitions": 0,
        "intents_promoted": 0,
    }
    transitions: list[RestockTransition] = []

    with conn.transaction():
        for variant in variants:
            previous = _latest_quantity(conn, variant.variant_id)
            current = int(variant.inventory_total)

            conn.execute(
                """
                INSERT INTO inventory_snapshots(
                    captured_at,
                    shopify_product_id,
                    shopify_variant_id,
                    sku,
                    inventory_quantity,
                    price,
                    compare_at_price,
                    source,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'shopify', %s)
                ON CONFLICT (shopify_variant_id, captured_at) DO NOTHING
                """,
                (
                    captured_at,
                    variant.product_id or None,
                    variant.variant_id,
                    variant.sku or None,
                    current,
                    _decimal_or_none(variant.price),
                    _decimal_or_none(variant.compare_at_price),
                    Jsonb({
                        "product_handle": variant.product_handle,
                        "product_title": variant.product_title,
                        "variant_title": variant.variant_title,
                        "size": variant.size,
                        "available_locations": [
                            {
                                "location_id": x.location_id,
                                "location_name": x.location_name,
                                "available": x.available,
                            }
                            for x in variant.locations
                        ],
                    }),
                ),
            )
            stats["snapshots_inserted"] += 1

            if not is_restock(previous, current):
                continue

            transition = RestockTransition(
                shopify_variant_id=variant.variant_id,
                sku=variant.sku,
                previous_quantity=previous,
                current_quantity=current,
            )
            transitions.append(transition)

            promoted = conn.execute(
                """
                UPDATE demand_intents
                SET
                    state = 'RESTOCK_MATCH',
                    last_seen_at = now(),
                    resolution = COALESCE(resolution, '') ||
                        CASE
                            WHEN COALESCE(resolution, '') = '' THEN ''
                            ELSE ' | '
                        END ||
                        'Restock detected: stock ' || %s || ' -> ' || %s,
                    metadata = COALESCE(metadata, '{}'::jsonb) ||
                        jsonb_build_object(
                            'restock_detected_at', %s::text,
                            'restock_previous_quantity', %s,
                            'restock_current_quantity', %s
                        )
                WHERE state = 'WAITING_STOCK'
                  AND shopify_variant_id = %s
                RETURNING intent_id
                """,
                (
                    previous,
                    current,
                    captured_at.isoformat(),
                    previous,
                    current,
                    variant.variant_id,
                ),
            ).fetchall()

            stats["intents_promoted"] += len(promoted)

    stats["restock_transitions"] = len(transitions)
    return stats, transitions
