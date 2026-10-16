"""Importa una vez el mapa teléfono → client_uuid de la hoja (`client_identity_map`) a `customers`.

Con esto el Registro del día del portal reconoce a los clientes que ya existían en la hoja.
"""
from __future__ import annotations

from typing import Any

import psycopg

from smart_memory.mapping import parse_datetime
from smart_portal.registro_v72 import normalize_phone


def _tail(phone: str) -> str:
    return f"···{phone[-4:]}" if phone else "—"


def import_identity_map(conn, rows: list[dict[str, Any]], *, apply: bool) -> dict[str, Any]:
    """Sin `apply` hace todo dentro de una transacción y la revierte: sirve como simulación exacta."""
    stats: dict[str, Any] = {
        "rows": len(rows), "invalid": 0, "already_ok": 0, "phone_added": 0,
        "customers_created": 0, "conflicts": [],
    }

    # Un mismo teléfono con dos client_uuid en la hoja es un conflicto que hay que resolver a mano.
    uuids_by_phone: dict[str, set[str]] = {}
    clean: list[tuple[str, str, dict[str, Any]]] = []
    for row in rows:
        phone, error = normalize_phone(str(row.get("telefono_e164") or ""))
        client_uuid = str(row.get("client_uuid") or "").strip()
        if error or not phone or not client_uuid:
            stats["invalid"] += 1
            continue
        uuids_by_phone.setdefault(phone, set()).add(client_uuid)
        clean.append((phone, client_uuid, row))
    ambiguous = {phone for phone, ids in uuids_by_phone.items() if len(ids) > 1}
    for phone in sorted(ambiguous):
        stats["conflicts"].append(f"{_tail(phone)}: aparece en la hoja con {len(uuids_by_phone[phone])} clientes distintos")

    try:
        with conn.transaction() as tx:
            seen: set[tuple[str, str]] = set()
            for phone, client_uuid, row in clean:
                if phone in ambiguous or (phone, client_uuid) in seen:
                    continue
                seen.add((phone, client_uuid))
                customer = conn.execute(
                    "SELECT customer_id, phone_e164 FROM customers WHERE client_uuid = %s", (client_uuid,)
                ).fetchone()
                owner = conn.execute(
                    "SELECT client_uuid FROM customers WHERE phone_e164 = %s AND client_uuid <> %s LIMIT 1",
                    (phone, client_uuid),
                ).fetchone()
                if owner:
                    stats["conflicts"].append(f"{_tail(phone)}: ya pertenece a otro cliente en la base")
                    continue
                if customer and customer["phone_e164"] == phone:
                    stats["already_ok"] += 1
                elif customer and customer["phone_e164"]:
                    stats["conflicts"].append(f"{_tail(phone)}: el cliente ya tiene otro teléfono ({_tail(customer['phone_e164'])})")
                elif customer:
                    conn.execute(
                        "UPDATE customers SET phone_e164 = %s, updated_at = now() WHERE customer_id = %s",
                        (phone, customer["customer_id"]),
                    )
                    stats["phone_added"] += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO customers(client_uuid, phone_e164, first_seen_at, last_seen_at, first_channel)
                        VALUES (%s, %s, %s, %s, 'sheet_identity_map')
                        """,
                        (client_uuid, phone, parse_datetime(row.get("first_seen_at")), parse_datetime(row.get("last_seen_at"))),
                    )
                    stats["customers_created"] += 1
            if not apply:
                raise psycopg.Rollback(tx)
    finally:
        stats["applied"] = apply
    return stats
