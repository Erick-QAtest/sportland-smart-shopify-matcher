from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Handles common WhatsApp iOS/Android export shapes. Exact locale variants can
# still be passed through a CSV/JSON integration endpoint if needed.
LINE_RE = re.compile(
    r"^\[?(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})[,\s]+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)(?:\s*(?P<ampm>[ap]\.?\s*m\.?))?\]?\s*(?:-\s*)?(?P<sender>[^:]+):\s*(?P<text>.*)$",
    re.I,
)


@dataclass
class WhatsAppMessage:
    occurred_at: datetime
    sender: str
    text: str
    source_event_id: str


def _parse_dt(date: str, time: str, ampm: str = "") -> datetime:
    d, m, y = re.split(r"[/-]", date)
    if len(y) == 2:
        y = "20" + y
    hh, mm, *ss = time.split(":")
    h = int(hh)
    a = (ampm or "").replace(".", "").replace(" ", "").lower()
    if a.startswith("p") and h < 12:
        h += 12
    if a.startswith("a") and h == 12:
        h = 0
    return datetime(int(y), int(m), int(d), h, int(mm), int(ss[0]) if ss else 0).astimezone()


def parse_whatsapp_export(path: str | Path) -> list[WhatsAppMessage]:
    out: list[WhatsAppMessage] = []
    current: WhatsAppMessage | None = None
    for raw in Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines():
        m = LINE_RE.match(raw)
        if m:
            dt = _parse_dt(m.group("date"), m.group("time"), m.group("ampm") or "")
            sender = m.group("sender").strip()
            text = m.group("text").strip()
            sid = hashlib.sha1(f"{dt.isoformat()}|{sender}|{text}".encode("utf-8")).hexdigest()
            current = WhatsAppMessage(dt, sender, text, f"wa-export:{sid}")
            out.append(current)
        elif current and raw.strip():
            current.text += " " + raw.strip()
    return out
