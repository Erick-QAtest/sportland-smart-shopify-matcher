from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    # JS Date.toISOString-compatible milliseconds.
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


@dataclass
class CapturedEvent:
    occurred_at: datetime
    event_type: str
    detail: str
    channel: str
    sku: str = ""
    size: str = ""
    amount: float | None = None
    phone_e164: str = ""
    pct: float | None = None
    currency: str = "MXN"
    actor: str = "sportland-event-capture"
    device: str = "unknown"
    origin: str = "event_capture_v22"
    raw_text: str = ""
    source_event_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    resolver_confidence: float = 0.0
    resolver_reason: str = ""

    def normalized_type(self) -> str:
        return (self.event_type or "").strip().upper()
