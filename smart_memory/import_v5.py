from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from .config import MemoryConfig
from .mapping import event_payload


def _upsert_catalog(conn: Connection, payload: dict[str, Any]) -> None:
    ident = payload["event_type_id"]
    if ident is None:
        return

    conn.execute(
        """
        INSERT INTO event_catalog(event_type_id, event_type_name)
        VALUES (%s, %s)
        ON CONFLICT (event_type_id)
        DO UPDATE SET event_type_name = EXCLUDED.event_type_name
        """,
        (ident, payload["event_type_name"]),
    )


def _upsert_customer(conn: Connection, payload: dict[str, Any]) -> int | None:
    client_uuid = payload["client_uuid"]
    if not client_uuid:
        return None

    row = conn.execute(
        """
        INSERT INTO customers(
            client_uuid, phone_e164, first_seen_at, last_seen_at, first_channel
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (client_uuid)
        DO UPDATE SET
            phone_e164 = COALESCE(customers.phone_e164, EXCLUDED.phone_e164),
            first_seen_at = CASE
                WHEN customers.first_seen_at IS NULL THEN EXCLUDED.first_seen_at
                WHEN EXCLUDED.first_seen_at IS NULL THEN customers.first_seen_at
                ELSE LEAST(customers.first_seen_at, EXCLUDED.first_seen_at)
            END,
            last_seen_at = CASE
                WHEN customers.last_seen_at IS NULL THEN EXCLUDED.last_seen_at
                WHEN EXCLUDED.last_seen_at IS NULL THEN customers.last_seen_at
                ELSE GREATEST(customers.last_seen_at, EXCLUDED.last_seen_at)
            END,
            first_channel = COALESCE(customers.first_channel, EXCLUDED.first_channel),
            updated_at = now()
        RETURNING customer_id
        """,
        (
            client_uuid,
            payload["phone_e164"],
            payload["occurred_at"],
            payload["occurred_at"],
            payload["channel"],
        ),
    ).fetchone()

    return int(row["customer_id"]) if row else None


def _insert_event(
    conn: Connection,
    payload: dict[str, Any],
    customer_id: int | None,
) -> bool:
    row = conn.execute(
        """
        INSERT INTO customer_events(
            event_uuid, event_hash, source, source_row_hash,
            customer_id, client_uuid,
            event_type_id, event_type_name, detail,
            occurred_at, logged_at,
            sku, size, amount, channel, pct, currency,
            actor, device, origin, silence_flag_system,
            metadata, raw_status
        )
        VALUES (
            %(event_uuid)s, %(event_hash)s, %(source)s, %(source_row_hash)s,
            %(customer_id)s, %(client_uuid)s,
            %(event_type_id)s, %(event_type_name)s, %(detail)s,
            %(occurred_at)s, %(logged_at)s,
            %(sku)s, %(size)s, %(amount)s, %(channel)s, %(pct)s, %(currency)s,
            %(actor)s, %(device)s, %(origin)s, %(silence_flag_system)s,
            %(metadata)s, %(raw_status)s
        )
        ON CONFLICT DO NOTHING
        RETURNING event_id
        """,
        {
            **payload,
            "customer_id": customer_id,
            "metadata": Jsonb(payload["metadata"]),
        },
    ).fetchone()

    return bool(row)


def import_logged_events(
    conn: Connection,
    rows: list[dict[str, Any]],
    cfg: MemoryConfig,
) -> dict[str, int]:
    stats = {
        "source_rows": len(rows),
        "inserted_events": 0,
        "duplicate_events": 0,
        "events_without_client_uuid": 0,
    }

    with conn.transaction():
        for row in rows:
            payload = event_payload(
                row,
                source_name=cfg.source_name,
                store_phone=cfg.store_phone,
            )

            _upsert_catalog(conn, payload)
            customer_id = _upsert_customer(conn, payload)

            if customer_id is None:
                stats["events_without_client_uuid"] += 1

            if _insert_event(conn, payload, customer_id):
                stats["inserted_events"] += 1
            else:
                stats["duplicate_events"] += 1

    return stats
