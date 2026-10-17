"""Semana tipo por comunidad: genera borradores del calendario para una campaña.

Mix inicial del plan (hipótesis experimental, se ajusta con ventas y saturación):
- WhatsApp SPORTLAND (local): 3 productos + 1 encuesta + 1 oferta por semana.
- WhatsApp Sportland Mx (online): 2 productos + 1 publicación de pagos u oferta.
Jueves y domingo de la comunidad local quedan libres a propósito (descanso / reactivo).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
from typing import Any

COMMUNITIES = {
    "WA_LOCAL": "WhatsApp SPORTLAND (local)",
    "WA_ONLINE": "WhatsApp Sportland Mx (online)",
    "WA_SPORTLAND_PUNTO": "WhatsApp «Sportland.» (por definir)",
}

WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass(frozen=True)
class Slot:
    weekday: int  # 0 = lunes
    code: str
    content_type: str
    topic: str
    cta: str
    objective: str
    pillar: str


WEEK_TEMPLATES: dict[str, tuple[Slot, ...]] = {
    "WA_LOCAL": (
        Slot(0, "producto-comodidad", "PRODUCTO", "Producto destacado con la comodidad como beneficio",
             "Visítanos en tienda", "Visita a tienda", "Producto"),
        Slot(1, "encuesta", "ENCUESTA", "Encuesta o consulta de preferencias",
             "Vota en la encuesta", "Participación", "Encuestas"),
        Slot(2, "producto-tallas", "PRODUCTO", "Producto con tallas disponibles",
             "Visítanos en tienda", "Visita a tienda", "Producto"),
        Slot(4, "oferta", "OFERTA", "Oferta especial (validar margen y stock antes de aprobar)",
             "Visítanos en tienda", "Visita a tienda", "Ofertas"),
        Slot(5, "producto-visita", "PRODUCTO", "Producto que motive la visita del fin de semana",
             "Te esperamos hoy en tienda", "Visita a tienda", "Producto"),
    ),
    "WA_ONLINE": (
        Slot(0, "producto-enlace", "PRODUCTO", "Producto con enlace directo",
             "Compra en línea", "Compra online", "Producto"),
        Slot(2, "producto-destacado", "PRODUCTO", "Producto destacado",
             "Compra en línea", "Compra online", "Producto"),
        Slot(3, "pagos-oferta", "PAGOS", "Facilidades de pago verificadas u oferta",
             "Compra en línea", "Compra online", "Ofertas"),
    ),
}


def template_key(day: date, community: str, slot_code: str) -> str:
    """Clave estable: la misma fecha + comunidad + espacio nunca se duplica,
    aunque se genere dos veces o desde otra campaña."""
    raw = f"tpl|{day.isoformat()}|{community}|{slot_code}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_drafts(
    campaign: dict[str, Any],
    communities: list[str] | tuple[str, ...],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[dict[str, Any]]:
    """Borradores de la semana tipo para cada día de la campaña (o del rango dado)."""
    first = max(start or campaign["starts_on"], campaign["starts_on"])
    last = min(end or campaign["ends_on"], campaign["ends_on"])
    theme = str(campaign.get("theme") or campaign.get("name") or "").strip()
    out: list[dict[str, Any]] = []
    day = first
    while day <= last:
        for community in communities:
            for slot in WEEK_TEMPLATES.get(community, ()):
                if slot.weekday != day.weekday():
                    continue
                out.append({
                    "calendar_key": template_key(day, community, slot.code),
                    "scheduled_date": day,
                    "weekday_name": WEEKDAYS[day.weekday()],
                    "channel": "WhatsApp comunidad",
                    "community_code": community,
                    "content_type": slot.content_type,
                    "objective": slot.objective,
                    "pillar": slot.pillar,
                    "topic": f"{slot.topic} · {theme}" if theme else slot.topic,
                    "cta": slot.cta,
                    "campaign_id": campaign.get("campaign_id"),
                    "priority": "ALTA" if slot.content_type in {"PRODUCTO", "OFERTA"} else "MEDIA",
                })
        day += timedelta(days=1)
    return out
