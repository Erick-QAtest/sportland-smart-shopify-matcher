from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


SIZE_RE = re.compile(r"(?:talla|numero|n[uú]mero|num\.?|#)\s*[:\-]?\s*(\d{1,2}(?:[\.,]\d)?)", re.I)
MONEY_RE = re.compile(r"(?:\$|mxn\s*)\s*(\d{2,6}(?:[\.,]\d{1,2})?)", re.I)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONEISH_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)")


def norm_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")


def sanitize_text(value: str) -> str:
    text = str(value or "")
    text = EMAIL_RE.sub("[email]", text)
    text = PHONEISH_RE.sub("[telefono]", text)
    return " ".join(text.split())[:1200]


def extract_size(text: str) -> str:
    m = SIZE_RE.search(text or "")
    if not m:
        return ""
    return m.group(1).replace(",", ".")


def extract_amount(text: str) -> float | None:
    m = MONEY_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


@dataclass
class Classification:
    event_type: str
    detail: str
    size: str = ""
    amount: float | None = None
    demand_relevant: bool = False
    reason: str = ""


def classify_message(
    text: str,
    *,
    channel: str = "whatsapp",
    sku: str = "",
    action: str = "",
) -> Classification:
    """Conservative classifier. It never invents SKU or size.

    Rich web actions are mapped to broad, observed Smart events and preserved in
    detail/metadata by the caller.
    """
    raw = str(text or "")
    t = norm_text(raw)
    a = norm_text(action)
    size = extract_size(raw)
    amount = extract_amount(raw)

    if a in {"product_view", "view_item", "add_to_cart", "size_select"}:
        if a == "size_select" and sku and size:
            return Classification(
                "PREGUNTA_TALLA_PRECIO",
                "seleccion talla en ecommerce",
                size=size,
                demand_relevant=True,
                reason="web_size_select_with_sku_and_size",
            )
        return Classification(
            "OBSERVA_PRODUCTO",
            a,
            size=size,
            demand_relevant=True,
            reason="observed_product_interaction",
        )

    if a in {"search", "site_search"}:
        # Only becomes matcher-ready when the resolver supplies a SKU.
        return Classification(
            "PREGUNTA_MODELO_ESPECIFICO",
            "busqueda ecommerce: " + sanitize_text(raw)[:180],
            size=size,
            demand_relevant=True,
            reason="site_search",
        )

    if any(k in t for k in ("quiero comprar", "me lo llevo", "comprarlo", "comprar este", "comprar esos")):
        return Classification(
            "DM_ACTIVO",
            "intencion explicita de compra",
            size=size,
            amount=amount,
            demand_relevant=True,
            reason="explicit_purchase_intent",
        )

    if any(k in t for k in ("apartame", "apartamelo", "apartar", "apartado")):
        if "como" in t or "sistema" in t or "funciona" in t:
            et = "PREGUNTA_SISTEMA_APARTADO"
            detail = "pregunta sistema apartado"
        else:
            et = "APARTADO"
            detail = "intencion de apartado"
        return Classification(et, detail, size=size, amount=amount, demand_relevant=True, reason="apartado_signal")

    has_price = any(k in t for k in ("precio", "cuanto", "cuesta", "vale", "costo"))
    has_size = bool(size) or any(k in t for k in ("talla", "numero", "medida"))
    has_stock = any(k in t for k in ("tienes", "hay", "disponible", "stock", "queda"))

    if (has_size or has_price or has_stock) and sku:
        # Existing matcher contract has one high-value size/price event. We only
        # promote it when product identity exists; size is enforced later.
        return Classification(
            "PREGUNTA_TALLA_PRECIO",
            "pregunta talla/precio/disponibilidad",
            size=size,
            amount=amount,
            demand_relevant=True,
            reason="commercial_question_with_resolved_sku",
        )

    if sku:
        return Classification(
            "PREGUNTA_MODELO_ESPECIFICO",
            "pregunta o interes por modelo especifico",
            size=size,
            amount=amount,
            demand_relevant=True,
            reason="resolved_product_interest",
        )

    # A WhatsApp message is still an observed interaction even if it cannot yet
    # be tied safely to a product. It remains valuable for the inbox/behavior log.
    if norm_text(channel) == "whatsapp":
        return Classification(
            "ENTRADA_WHATSAPP",
            "mensaje whatsapp: " + sanitize_text(raw)[:180],
            size=size,
            amount=amount,
            demand_relevant=bool(has_size or has_price or has_stock),
            reason="unresolved_whatsapp_message",
        )

    return Classification(
        "REACCION_CONTENIDO",
        "interaccion ecommerce",
        size=size,
        amount=amount,
        demand_relevant=False,
        reason="generic_interaction",
    )
