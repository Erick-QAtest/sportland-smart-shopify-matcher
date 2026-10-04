from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def enhance_variant_decisions(
    decisions: list[dict[str, Any]],
    intelligence_by_sku: list[dict[str, Any]],
    intelligence_by_product: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    smap = {str(r.get("sku") or "").strip(): r for r in intelligence_by_sku}
    pmap = {str(r.get("product_key") or "").strip(): r for r in intelligence_by_product}
    out: list[dict[str, Any]] = []

    for row in decisions:
        x = dict(row)
        sku = str(x.get("sku") or "").strip()
        pkey = str(x.get("product_key") or "").strip()
        s = smap.get(sku, {})
        p = pmap.get(pkey, {})
        base_action = str(x.get("action") or "OBSERVAR")
        stock = _i(x.get("inventory_quantity"))
        demand = _f(s.get("demand_score"))
        conversion = _f(s.get("conversion_score"))
        behavior = _f(s.get("behavior_score"))
        product_demand = _f(p.get("demand_score"))
        product_conversion = _f(p.get("conversion_score"))

        x.update({
            "action_v21": base_action,
            "history_events": s.get("events", 0),
            "history_events_30d": s.get("events_30d", 0),
            "behavior_score": round(behavior, 2),
            "history_demand_score": round(demand, 2),
            "conversion_score": round(conversion, 2),
            "history_demand_strength": s.get("demand_strength", "NONE"),
            "conversion_strength": s.get("conversion_strength", "NONE"),
            "product_history_demand_score": round(product_demand, 2),
            "product_conversion_score": round(product_conversion, 2),
            "history_unique_clients": s.get("unique_clients", 0),
        })

        # Liquidity/restock guardrail remains authoritative.
        if base_action in {"NO_RECOMPRAR_AUN", "DEMANDA_PERDIDA"}:
            x["action"] = base_action
            x["reason_v23"] = (
                "Histórico comercial incorporado, pero la restricción financiera de recompra conserva prioridad."
            )
        elif stock > 0 and (conversion >= 4.0 or demand >= 3.0 or product_conversion >= 6.0):
            x["action"] = "PROTEGER_STOCK"
            x["reason_v23"] = (
                "Histórico fuerte de demanda/conversión con stock actual; frenar liquidación y priorizar cierre de venta."
            )
        elif stock > 0 and (conversion >= 1.0 or demand >= 1.0):
            x["action"] = "VENDER_AHORA"
            x["reason_v23"] = (
                "Existe intención o conversión histórica suficiente; intentar convertir stock en caja antes de descontar."
            )
        elif base_action in {"LIQUIDAR_VARIANTE", "LIQUIDAR_PRODUCTO"} and (
            demand >= 0.50 or conversion > 0 or product_demand >= 2.0 or product_conversion >= 2.0
        ):
            x["action"] = "REVISAR_VARIANTE"
            x["decision_scope"] = "VARIANT"
            x["reason_v23"] = (
                "El histórico del cliente contradice una liquidación automática; revisar talla/variante antes de rebajar."
            )
        elif base_action == "REVISAR_ROTACION" and (product_demand >= 3.0 or product_conversion >= 4.0):
            x["action"] = "REVISAR_VARIANTE"
            x["reason_v23"] = (
                "La variante está lenta, pero el producto tiene historial comercial fuerte; no castigar el modelo completo."
            )
        else:
            x["action"] = base_action
            x["reason_v23"] = "El histórico no alcanza el umbral para modificar la decisión 2.1."
        out.append(x)

    rank = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda r: (
        rank.get(str(r.get("priority")), 9),
        0 if r.get("action") == "PROTEGER_STOCK" else 1 if r.get("action") == "VENDER_AHORA" else 2,
        -_f(r.get("history_demand_score")),
        -_f(r.get("conversion_score")),
        -_f(r.get("capital_at_cost")),
        str(r.get("sku")),
    ))
    return out


def enhance_product_decisions(
    products: list[dict[str, Any]],
    intelligence_by_product: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pmap = {str(r.get("product_key") or "").strip(): r for r in intelligence_by_product}
    out: list[dict[str, Any]] = []
    for row in products:
        x = dict(row)
        pkey = str(x.get("product_key") or "").strip()
        h = pmap.get(pkey, {})
        base = str(x.get("product_action") or "REVISAR_PRODUCTO")
        demand = _f(h.get("demand_score"))
        conversion = _f(h.get("conversion_score"))
        behavior = _f(h.get("behavior_score"))
        x.update({
            "product_action_v21": base,
            "behavior_score": round(behavior, 2),
            "history_demand_score": round(demand, 2),
            "conversion_score": round(conversion, 2),
            "history_events": h.get("events", 0),
            "history_unique_clients": h.get("unique_clients", 0),
        })
        if conversion >= 6.0 or demand >= 4.0:
            x["product_action"] = "PROTEGER_PRODUCTO"
            x["reason_v23"] = "El producto tiene historial comercial fuerte; no liquidarlo de forma general."
        elif base == "LIQUIDAR_PRODUCTO" and (conversion > 0 or demand >= 1.0):
            x["product_action"] = "REVISAR_PRODUCTO"
            x["reason_v23"] = "Hay evidencia histórica de interés/conversión; revisar antes de liquidar todo el producto."
        else:
            x["product_action"] = base
            x["reason_v23"] = "El histórico no modifica la decisión de producto 2.1."
        out.append(x)
    return out
