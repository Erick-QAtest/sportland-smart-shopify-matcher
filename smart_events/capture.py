from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .classifier import classify_message, sanitize_text
from .models import CapturedEvent
from .resolver import CatalogResolver
from .sheet_store import GoogleSheetEventStore


def parse_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("occurred_at es obligatorio; no se autocompleta en captura manual")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def capture_event(
    *,
    store: GoogleSheetEventStore,
    resolver: CatalogResolver,
    text: str = "",
    occurred_at: str | datetime,
    channel: str,
    phone_e164: str = "",
    sku: str = "",
    product_title: str = "",
    size: str = "",
    action: str = "",
    source_event_id: str = "",
    device: str = "unknown",
    origin: str = "event_capture_v22",
    actor: str = "sportland-event-capture",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    metadata["action"] = action or metadata.get("action") or ""
    resolution = resolver.resolve(text, explicit_sku=sku, product_title=product_title)
    resolved_sku = resolution.sku or sku
    cls = classify_message(text, channel=channel, sku=resolved_sku, action=action)
    final_size = size or cls.size
    event = CapturedEvent(
        occurred_at=parse_datetime(occurred_at),
        event_type=cls.event_type,
        detail=cls.detail,
        channel=channel,
        sku=resolved_sku,
        size=final_size,
        amount=cls.amount,
        phone_e164=phone_e164,
        currency="MXN",
        actor=actor,
        device=device,
        origin=origin,
        raw_text=text,
        source_event_id=source_event_id,
        metadata=metadata,
        resolver_confidence=resolution.confidence,
        resolver_reason=resolution.reason,
    )
    status, error = store.promote_to_log(event)
    inbox_written = store.append_inbox(
        event,
        sanitized_text=sanitize_text(text),
        demand_relevant=cls.demand_relevant,
        promotion_status=status,
        error_msg=error,
    )
    return {
        "status": status,
        "error": error,
        "inbox_written": inbox_written,
        "event_type": event.normalized_type(),
        "sku": event.sku,
        "size": event.size,
        "resolver_confidence": event.resolver_confidence,
        "resolver_reason": event.resolver_reason,
        "demand_relevant": cls.demand_relevant,
    }
