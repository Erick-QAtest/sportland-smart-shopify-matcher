from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .models import CapturedEvent, iso_utc

LOG_HEADERS = [
    "ts_log", "event_uuid", "event_hash", "fecha_evento", "telefono_e164",
    "client_uuid", "tipo_evento_id", "tipo_evento_nombre", "detalle_evento",
    "sku", "talla", "monto", "canal", "pct", "moneda", "actor", "device",
    "origen", "silencio_flag_system", "meta_json", "status"
]

INBOX_HEADERS = [
    "received_at", "source_event_id", "event_uuid", "occurred_at", "channel",
    "event_type_candidate", "detail", "sku_candidate", "size_candidate",
    "resolver_confidence", "resolver_reason", "demand_relevant", "phone_hash",
    "text_sanitized", "meta_json", "promotion_status", "error_msg"
]

EVENTOS_COMPRA = {"COMPRA", "COMPRA_TIENDA_FISICA", "COMPRA_ECOMMERCE", "COMPRA_MARKETPLACE"}
EVENTOS_PROMO = {"PROMO_MONEDERO_120", "PROMO_SEGUNDO_PAR_20", "PROMO_ENVIO_GRATIS"}
EVENTOS_REQUIEREN_TALLA = {
    "PREGUNTA_TALLA_PRECIO", "PRUEBA_MULTIPLES_MODELOS", "APARTADO",
    "ABONO_APARTADO", "LIQUIDACION_APARTADO", *EVENTOS_COMPRA,
}
EVENTOS_REQUIEREN_SKU = {
    "PREGUNTA_TALLA_PRECIO", "PREGUNTA_MODELO_ESPECIFICO", "PRUEBA_MULTIPLES_MODELOS",
    "APARTADO", "ABONO_APARTADO", "LIQUIDACION_APARTADO", *EVENTOS_COMPRA,
    *EVENTOS_PROMO,
}
EVENTOS_ANONIMOS_PERMITIDOS = {
    "LLEGADA_POR_CANAL_FISICO", "OBSERVA_PRODUCTO", "ENTRA_RAPIDO_SIN_DATOS",
    "PREGUNTA_TALLA_PRECIO", "PREGUNTA_SISTEMA_APARTADO", "PREGUNTA_MODELO_ESPECIFICO",
    "PRUEBA_MULTIPLES_MODELOS", "SALE_SIN_COMPRA",
}

E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        raw = "+" + raw
    raw = re.sub(r"[\s().-]+", "", raw)
    if not E164.match(raw):
        raise ValueError("telefono_e164 debe ser E.164; no se inventa país/código")
    return raw


def phone_hash(value: str) -> str:
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def anonymous_allowed(event_name: str, channel: str) -> bool:
    n = event_name.strip().upper()
    if n in EVENTOS_ANONIMOS_PERMITIDOS:
        return True
    if channel == "tienda_fisica" and n not in EVENTOS_COMPRA and n not in {"APARTADO", "ABONO_APARTADO", "LIQUIDACION_APARTADO"}:
        return True
    return False


def validate_for_log(event: CapturedEvent, catalog: dict[str, int]) -> list[str]:
    errors: list[str] = []
    name = event.normalized_type()
    if not isinstance(event.occurred_at, datetime):
        errors.append("fecha_evento inválida")
    if name not in catalog:
        errors.append("tipo_evento no existe en catalogo_eventos_db")
    try:
        phone = normalize_phone(event.phone_e164) if event.phone_e164 else ""
    except ValueError as e:
        errors.append(str(e))
        phone = ""
    if not phone and not anonymous_allowed(name, event.channel):
        errors.append("evento no autorizado como anónimo")
    if name in EVENTOS_REQUIEREN_TALLA and not str(event.size or "").strip():
        errors.append(f"{name} requiere talla explícita")
    if name in EVENTOS_REQUIEREN_SKU and not str(event.sku or "").strip():
        errors.append(f"{name} requiere SKU para contrato matcher-ready")
    if name in EVENTOS_COMPRA:
        if not event.sku:
            errors.append("compra requiere SKU")
        if not (event.amount is not None and float(event.amount) > 0):
            errors.append("compra requiere monto > 0")
    if name in EVENTOS_PROMO:
        if not event.sku:
            errors.append("promo requiere SKU")
        if not event.channel:
            errors.append("promo requiere canal explícito")
    return errors


def semantic_payload(event: CapturedEvent, event_type_id: int) -> dict[str, Any]:
    phone = normalize_phone(event.phone_e164) if event.phone_e164 else None
    return {
        "fecha_evento": iso_utc(event.occurred_at),
        "telefono_e164": phone,
        "tipo_evento_id": int(event_type_id),
        "tipo_evento_nombre": event.normalized_type(),
        "detalle_evento": event.detail or None,
        "sku": event.sku or None,
        "talla": event.size or None,
        "monto": event.amount,
        "canal": event.channel or None,
        "pct": event.pct,
        "moneda": event.currency or None,
        "origen": event.origin or None,
    }


def semantic_hash(event: CapturedEvent, event_type_id: int) -> str:
    raw = json.dumps(semantic_payload(event, event_type_id), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_log_row(event: CapturedEvent, event_type_id: int, *, client_uuid: str = "", event_uuid: str = "") -> list[Any]:
    event_uuid = event_uuid or str(uuid.uuid4())
    phone = normalize_phone(event.phone_e164) if event.phone_e164 else ""
    meta = {
        "schema": "sportland.event.v2",
        "version": "event-capture-v2.2",
        "origen": event.origin,
        "telefono_e164": phone or None,
        "sku": event.sku or None,
        "talla": event.size or None,
        "canal": event.channel or None,
        "pct": event.pct,
        "moneda": event.currency,
        "actor": event.actor,
        "device": event.device,
        "source_event_id": event.source_event_id or None,
        "resolver_confidence": event.resolver_confidence,
        "resolver_reason": event.resolver_reason,
        "raw_action": event.metadata.get("action"),
        "silencio_flag_system": None,
    }
    return [
        iso_utc(datetime.now(timezone.utc)),
        event_uuid,
        semantic_hash(event, event_type_id),
        iso_utc(event.occurred_at),
        phone,
        client_uuid,
        int(event_type_id),
        event.normalized_type(),
        event.detail,
        event.sku,
        event.size,
        "" if event.amount is None else event.amount,
        event.channel,
        "" if event.pct is None else event.pct,
        event.currency,
        event.actor,
        event.device,
        event.origin,
        "",
        json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
        "LOGGED",
    ]
