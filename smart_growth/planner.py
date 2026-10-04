from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from typing import Any, Iterable


ACTIONABLE = {
    "VENDER_AHORA",
    "PROTEGER_STOCK",
    "LIQUIDAR_VARIANTE",
    "LIQUIDAR_PRODUCTO",
    "REVISAR_VARIANTE",
    "NO_RECOMPRAR_AUN",
    "DEMANDA_PERDIDA",
}


@dataclass(frozen=True)
class GrowthAction:
    action_key: str
    source_type: str
    source_ref: str
    sku: str
    product_key: str
    product_title: str
    channel: str
    objective: str
    priority_band: str
    activation_mode: str
    reason: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _priority(row: dict[str, Any], action: str) -> str:
    raw = _text(row.get("priority")).upper()
    mapping = {"P0": "HIGH", "P1": "MEDIUM", "P2": "LOW"}
    if raw in mapping:
        return mapping[raw]

    conversion = _float(row.get("conversion_score"))
    demand = max(
        _float(row.get("history_demand_score")),
        _float(row.get("demand_score")),
    )

    if action in {"VENDER_AHORA", "PROTEGER_STOCK"} and (
        conversion >= 4.0 or demand >= 3.0
    ):
        return "HIGH"
    if action.startswith("LIQUIDAR"):
        return "MEDIUM"
    return "LOW"


def _key(
    *,
    source_type: str,
    source_ref: str,
    sku: str,
    channel: str,
    objective: str,
) -> str:
    raw = "|".join([
        source_type,
        source_ref,
        sku,
        channel,
        objective,
    ])
    return sha256(raw.encode("utf-8")).hexdigest()


def _action(
    row: dict[str, Any],
    *,
    source_type: str,
    source_ref: str,
    channel: str,
    objective: str,
    priority_band: str,
    activation_mode: str,
    reason: str,
) -> GrowthAction:
    sku = _text(row.get("sku"))
    product_key = _text(row.get("product_key"))
    product_title = _text(row.get("product_title"))

    return GrowthAction(
        action_key=_key(
            source_type=source_type,
            source_ref=source_ref,
            sku=sku,
            channel=channel,
            objective=objective,
        ),
        source_type=source_type,
        source_ref=source_ref,
        sku=sku,
        product_key=product_key,
        product_title=product_title,
        channel=channel,
        objective=objective,
        priority_band=priority_band,
        activation_mode=activation_mode,
        reason=reason,
        metadata={
            "decision_action": _text(row.get("action")),
            "inventory_quantity": row.get("inventory_quantity"),
            "price": row.get("price"),
            "recommended_price": row.get("recommended_price"),
            "recommended_discount_pct": row.get("recommended_discount_pct"),
            "behavior_score": row.get("behavior_score"),
            "conversion_score": row.get("conversion_score"),
            "history_demand_score": row.get("history_demand_score"),
            "demand_score": row.get("demand_score"),
            "automatic_activation": False,
        },
    )


def actions_from_behavior_decisions(
    rows: Iterable[dict[str, Any]],
) -> list[GrowthAction]:
    out: list[GrowthAction] = []

    for index, row in enumerate(rows, start=1):
        action = _text(row.get("action")).upper()
        if action not in ACTIONABLE:
            continue

        source_ref = _text(row.get("sku")) or f"row-{index}"
        priority = _priority(row, action)

        if action == "VENDER_AHORA":
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="META",
                objective="CONVERSION_CAMPAIGN_REVIEW",
                priority_band=priority,
                activation_mode="MANUAL_REVIEW",
                reason="Hay stock y señal de demanda/conversión; revisar activación pagada sin modificar precio automáticamente.",
            ))
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="WHATSAPP",
                objective="COMMUNITY_PROMOTION_REVIEW",
                priority_band=priority,
                activation_mode="MANUAL_REVIEW",
                reason="Hay stock vendible; preparar promoción para comunidad sin envío automático.",
            ))

        elif action == "PROTEGER_STOCK":
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="GOOGLE_SEO",
                objective="ORGANIC_DEMAND_CAPTURE",
                priority_band=priority,
                activation_mode="CONTENT_REVIEW",
                reason="Demanda fuerte con stock limitado; priorizar tráfico orgánico y evitar presión pagada innecesaria.",
            ))
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="YOUTUBE",
                objective="CONTENT_SUPPORT",
                priority_band=priority,
                activation_mode="CONTENT_REVIEW",
                reason="Producto con demanda protegida; reforzar contenido educativo/comercial sin descuento automático.",
            ))

        elif action in {"LIQUIDAR_VARIANTE", "LIQUIDAR_PRODUCTO"}:
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="META",
                objective="CLEARANCE_CAMPAIGN_REVIEW",
                priority_band=priority,
                activation_mode="MANUAL_REVIEW",
                reason="Candidato de liquidación con guardrails financieros; revisar campaña antes de gastar presupuesto.",
            ))
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="WHATSAPP",
                objective="COMMUNITY_CLEARANCE_REVIEW",
                priority_band=priority,
                activation_mode="MANUAL_REVIEW",
                reason="Candidato de liquidación; preparar comunicación de comunidad sin envío automático.",
            ))

        elif action == "REVISAR_VARIANTE":
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="GOOGLE_SEO",
                objective="SEARCH_DEMAND_REVIEW",
                priority_band=priority,
                activation_mode="CONTENT_REVIEW",
                reason="La variante requiere revisión; usar señales de búsqueda/contenido antes de activar gasto pagado.",
            ))

        elif action in {"NO_RECOMPRAR_AUN", "DEMANDA_PERDIDA"}:
            out.append(_action(
                row,
                source_type="BEHAVIOR_DECISION_V23",
                source_ref=source_ref,
                channel="GOOGLE_SEO",
                objective="OUT_OF_STOCK_DEMAND_CAPTURE",
                priority_band="SIGNAL",
                activation_mode="CONTENT_REVIEW",
                reason="Existe demanda sin inventario o restricción de recompra; capturar señal sin promover una venta no disponible.",
            ))

    return out


def actions_from_commercial_opportunities(
    rows: Iterable[dict[str, Any]],
) -> list[GrowthAction]:
    out: list[GrowthAction] = []

    for row in rows:
        action = _text(row.get("action")).upper()
        band = _text(row.get("priority_band")).upper() or "LOW"
        lifecycle = _text(row.get("lifecycle_status")).upper()

        if lifecycle and lifecycle != "OPEN":
            continue

        sku = _text(row.get("sku"))
        source_ref = _text(row.get("opportunity_id"))

        base = {
            "sku": sku,
            "product_key": "",
            "product_title": "",
            "action": action,
        }

        if action == "CONTACT_CANDIDATE" and band in {"HIGH", "MEDIUM"}:
            out.append(_action(
                base,
                source_type="COMMERCIAL_OPPORTUNITY",
                source_ref=source_ref,
                channel="WHATSAPP",
                objective="ONE_TO_ONE_CONTACT_REVIEW",
                priority_band=band,
                activation_mode="INDIVIDUAL_REVIEW",
                reason="Oportunidad comercial identificada y contactable; requiere revisión humana antes de cualquier contacto.",
            ))

        elif action == "DEMAND_SIGNAL_ONLY":
            out.append(_action(
                base,
                source_type="COMMERCIAL_OPPORTUNITY",
                source_ref=source_ref,
                channel="META",
                objective="AGGREGATE_AUDIENCE_SIGNAL",
                priority_band="SIGNAL",
                activation_mode="MANUAL_REVIEW",
                reason="Señal de demanda sin identidad contactable; usar solo como señal agregada, nunca para contacto individual.",
            ))

    return out


def dedupe_actions(actions: Iterable[GrowthAction]) -> list[GrowthAction]:
    unique: dict[str, GrowthAction] = {}
    for item in actions:
        unique[item.action_key] = item

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SIGNAL": 3}
    return sorted(
        unique.values(),
        key=lambda x: (
            order.get(x.priority_band, 9),
            x.channel,
            x.objective,
            x.sku,
            x.action_key,
        ),
    )
