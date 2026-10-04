from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def text(value: Any) -> str:
    return str(value or "").strip()


def parse_datetime(value: Any) -> datetime | None:
    raw = text(value)
    if not raw:
        return None
    for candidate in (raw.replace("Z", "+00:00"), raw):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def parse_decimal(value: Any) -> Decimal | None:
    raw = text(value).replace(",", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_bool(value: Any) -> bool | None:
    raw = text(value).lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "si", "sí", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raw = text(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"raw_meta_json": raw}
    return parsed if isinstance(parsed, dict) else {"raw_meta_json": parsed}


def event_payload(
    row: dict[str, Any],
    *,
    source_name: str = "sportland_smart_v5",
    store_phone: bool = False,
) -> dict[str, Any]:
    """Map canonical eventos_log_v5 rows to the persistent DB contract."""
    phone = text(row.get("telefono_e164")) if store_phone else None
    event_hash = text(row.get("event_hash")) or None

    event_type_id = None
    raw_event_type_id = text(row.get("tipo_evento_id"))
    if raw_event_type_id:
        try:
            event_type_id = int(float(raw_event_type_id))
        except (TypeError, ValueError):
            event_type_id = None

    return {
        "event_uuid": text(row.get("event_uuid")) or None,
        "event_hash": event_hash,
        "source": source_name,
        "source_row_hash": event_hash,
        "client_uuid": text(row.get("client_uuid")) or None,
        "phone_e164": phone,
        "event_type_id": event_type_id,
        "event_type_name": text(row.get("tipo_evento_nombre")).upper() or "UNKNOWN",
        "detail": text(row.get("detalle_evento")) or None,
        "occurred_at": parse_datetime(row.get("fecha_evento")),
        "logged_at": parse_datetime(row.get("ts_log")),
        "sku": text(row.get("sku")) or None,
        "size": text(row.get("talla")) or None,
        "amount": parse_decimal(row.get("monto")),
        "channel": text(row.get("canal")) or None,
        "pct": parse_decimal(row.get("pct")),
        "currency": text(row.get("moneda")) or "MXN",
        "actor": text(row.get("actor")) or None,
        "device": text(row.get("device")) or None,
        "origin": text(row.get("origen")) or None,
        "silence_flag_system": parse_bool(row.get("silencio_flag_system")),
        "metadata": parse_json(row.get("meta_json")),
        "raw_status": text(row.get("status")).upper() or None,
    }
