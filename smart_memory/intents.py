from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


UNRESOLVED_STATUSES = {
    "NEEDS_PRODUCT_RESOLUTION",
    "NEEDS_PRODUCT_AND_SIZE_RESOLUTION",
    "NEEDS_SIZE_RESOLUTION",
    "NO_SHOPIFY_MATCH",
    "AMBIGUOUS_MATCH",
    "SIZE_CONFLICT",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def state_from_match(match_status: str) -> str:
    status = _text(match_status).upper()
    if status == "MATCH_AVAILABLE":
        return "AVAILABLE"
    if status == "MATCH_OUT_OF_STOCK":
        return "WAITING_STOCK"
    if status in UNRESOLVED_STATUSES:
        return "UNRESOLVED"
    return "UNRESOLVED"


def read_match_rows(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe matcher artifact: {p}")
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _find_source_event(conn: Connection, row: dict[str, str]) -> dict[str, Any] | None:
    event_uuid = _text(row.get("event_uuid"))
    event_hash = _text(row.get("event_hash"))

    if event_uuid:
        found = conn.execute(
            """
            SELECT event_id, customer_id, client_uuid
            FROM customer_events
            WHERE event_uuid = %s
            LIMIT 1
            """,
            (event_uuid,),
        ).fetchone()
        if found:
            return dict(found)

    if event_hash:
        found = conn.execute(
            """
            SELECT event_id, customer_id, client_uuid
            FROM customer_events
            WHERE event_hash = %s
            ORDER BY event_id
            LIMIT 1
            """,
            (event_hash,),
        ).fetchone()
        if found:
            return dict(found)

    return None


def sync_match_rows(
    conn: Connection,
    rows: list[dict[str, str]],
) -> dict[str, int]:
    stats = {
        "matcher_rows": len(rows),
        "inserted": 0,
        "updated": 0,
        "missing_source_event": 0,
        "available": 0,
        "waiting_stock": 0,
        "unresolved": 0,
    }

    with conn.transaction():
        for row in rows:
            source = _find_source_event(conn, row)
            if not source:
                stats["missing_source_event"] += 1
                continue

            state = state_from_match(row.get("match_status", ""))
            if state == "AVAILABLE":
                stats["available"] += 1
            elif state == "WAITING_STOCK":
                stats["waiting_stock"] += 1
            else:
                stats["unresolved"] += 1

            payload = {
                "source_event_id": source["event_id"],
                "customer_id": source["customer_id"],
                "client_uuid": source["client_uuid"] or _text(row.get("client_uuid")) or None,
                "shopify_product_id": _text(row.get("product_id")) or None,
                "shopify_variant_id": _text(row.get("variant_id")) or None,
                "smart_sku": _text(row.get("smart_sku")) or None,
                "resolved_sku": _text(row.get("shopify_sku")) or None,
                "requested_size": _text(row.get("requested_size")) or None,
                "match_status": _text(row.get("match_status")) or None,
                "match_confidence": _text(row.get("match_confidence")) or None,
                "state": state,
                "resolution": _text(row.get("reason")) or None,
                "metadata": Jsonb({
                    "product_handle": _text(row.get("product_handle")),
                    "product_title": _text(row.get("product_title")),
                    "shopify_size": _text(row.get("shopify_size")),
                    "inventory_total": _text(row.get("inventory_total")),
                    "price": _text(row.get("price")),
                    "compare_at_price": _text(row.get("compare_at_price")),
                    "size_source": _text(row.get("size_source")),
                }),
            }

            existing = conn.execute(
                "SELECT intent_id FROM demand_intents WHERE source_event_id = %s",
                (payload["source_event_id"],),
            ).fetchone()

            result = conn.execute(
                """
                INSERT INTO demand_intents(
                    source_event_id, customer_id, client_uuid,
                    shopify_product_id, shopify_variant_id,
                    smart_sku, resolved_sku, requested_size,
                    match_status, match_confidence, state,
                    resolution, metadata
                )
                VALUES (
                    %(source_event_id)s, %(customer_id)s, %(client_uuid)s,
                    %(shopify_product_id)s, %(shopify_variant_id)s,
                    %(smart_sku)s, %(resolved_sku)s, %(requested_size)s,
                    %(match_status)s, %(match_confidence)s, %(state)s,
                    %(resolution)s, %(metadata)s
                )
                ON CONFLICT (source_event_id)
                DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    client_uuid = EXCLUDED.client_uuid,
                    shopify_product_id = EXCLUDED.shopify_product_id,
                    shopify_variant_id = EXCLUDED.shopify_variant_id,
                    smart_sku = EXCLUDED.smart_sku,
                    resolved_sku = EXCLUDED.resolved_sku,
                    requested_size = EXCLUDED.requested_size,
                    match_status = EXCLUDED.match_status,
                    match_confidence = EXCLUDED.match_confidence,
                    state = EXCLUDED.state,
                    resolution = EXCLUDED.resolution,
                    metadata = EXCLUDED.metadata,
                    last_seen_at = now()
                RETURNING intent_id
                """,
                payload,
            ).fetchone()

            if result:
                stats["updated" if existing else "inserted"] += 1

    return stats
