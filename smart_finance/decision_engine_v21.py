from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smart_finance.decision_engine_v2 import DecisionRules as BaseDecisionRules
from smart_finance.decision_engine_v2 import build_decisions as build_base_decisions
from smart_finance.demand_intelligence_v21 import DemandRules, build_demand_intelligence


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _norm(v: Any) -> str:
    text = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")


@dataclass
class DecisionRulesV21:
    # Demand thresholds
    moderate_demand_score: float = 1.00
    strong_demand_score: float = 3.00
    strong_product_demand_score: float = 4.00
    # Product-level liquidation guardrails
    product_liquidation_slow_variant_share: float = 0.65
    min_product_stock_units_for_liquidation: int = 2
    min_events_for_product_liquidation_confidence: int = 20
    # Pricing guardrails (still read-only; no automatic price updates)
    min_markup_over_cost_pct: float = 0.10
    max_discount_pct: float = 0.30
    discount_score_70: float = 0.15
    discount_score_75: float = 0.20
    discount_score_82: float = 0.25
    discount_score_90: float = 0.30

    @classmethod
    def from_json(cls, path: str | Path | None) -> "DecisionRulesV21":
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        allowed = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)


def _product_key(row: dict[str, Any]) -> str:
    # Current Shopify snapshots used by Sprint 2 expose product_title reliably.
    # If product_id/handle become available later, they take precedence automatically.
    for key in ("product_id", "shopify_product_id"):
        if row.get(key):
            return f"id:{row[key]}"
    for key in ("product_handle", "shopify_handle"):
        if row.get(key):
            return f"handle:{_norm(row[key])}"
    title = row.get("product_title") or ""
    return f"title:{_norm(title)}" if title else f"sku:{row.get('sku','')}"


def _discount_from_score(score: float, rules: DecisionRulesV21) -> float:
    if score >= 90:
        return rules.discount_score_90
    if score >= 82:
        return rules.discount_score_82
    if score >= 75:
        return rules.discount_score_75
    if score >= 70:
        return rules.discount_score_70
    return 0.10


def _pricing(row: dict[str, Any], action: str, rules: DecisionRulesV21) -> dict[str, Any]:
    price = row.get("price")
    cost = row.get("unit_cost")
    stock = _i(row.get("inventory_quantity"))
    if price in (None, "") or cost in (None, ""):
        return {
            "price_floor": None,
            "recommended_discount_pct": None,
            "recommended_price": None,
            "recoverable_cash_est": None,
            "recoverable_gross_profit_est": None,
        }
    price_f = _f(price)
    cost_f = _f(cost)
    if price_f <= 0 or cost_f < 0:
        return {
            "price_floor": None,
            "recommended_discount_pct": None,
            "recommended_price": None,
            "recoverable_cash_est": None,
            "recoverable_gross_profit_est": None,
        }

    floor = round(cost_f * (1.0 + rules.min_markup_over_cost_pct), 2)
    if action not in {"LIQUIDAR_VARIANTE", "LIQUIDAR_PRODUCTO"}:
        discount = 0.0
        recommended = price_f
    else:
        discount = min(rules.max_discount_pct, _discount_from_score(_f(row.get("liquidation_score")), rules))
        proposed = round(price_f * (1.0 - discount), 2)
        recommended = max(floor, proposed)
        # Recompute actual discount if floor blocks the nominal discount.
        discount = max(0.0, min(rules.max_discount_pct, 1.0 - (recommended / price_f))) if price_f else 0.0

    recoverable_cash = round(recommended * stock, 2)
    recoverable_gp = round((recommended - cost_f) * stock, 2)
    return {
        "price_floor": floor,
        "recommended_discount_pct": round(discount, 4),
        "recommended_price": round(recommended, 2),
        "recoverable_cash_est": recoverable_cash,
        "recoverable_gross_profit_est": recoverable_gp,
    }


def build_decisions_v21(
    snapshot: dict[str, Any],
    shopify: dict[str, Any],
    matches: list[dict[str, Any]],
    *,
    base_rules: BaseDecisionRules | None = None,
    rules: DecisionRulesV21 | None = None,
    demand_rules: DemandRules | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rules = rules or DecisionRulesV21()
    base = build_base_decisions(snapshot, shopify, matches, base_rules or BaseDecisionRules())
    demand = build_demand_intelligence(matches, rules=demand_rules or DemandRules(
        moderate_threshold=rules.moderate_demand_score,
        strong_threshold=rules.strong_demand_score,
        product_strong_threshold=rules.strong_product_demand_score,
    ))

    demand_sku = {str(r.get("sku") or ""): r for r in demand.get("by_sku", [])}
    demand_product = {str(r.get("product_key") or ""): r for r in demand.get("by_product", [])}
    confidence = str((demand.get("summary") or {}).get("data_confidence") or "LOW")
    total_events = _i((demand.get("summary") or {}).get("total_events"))

    # First pass: enrich every SKU and build product aggregates from Shopify + Smart demand.
    enriched: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in base:
        x = dict(row)
        key = _product_key(x)
        ds = demand_sku.get(str(x.get("sku") or ""), {})
        dp = demand_product.get(key, {})
        x["product_key"] = key
        x["demand_score"] = round(_f(ds.get("demand_score")), 2)
        x["demand_strength"] = ds.get("demand_strength") or ("NONE" if not x["demand_score"] else "WEAK")
        x["demand_events_7d"] = _i(ds.get("events_7d"))
        x["demand_events_30d"] = _i(ds.get("events_30d"))
        x["demand_events_60d"] = _i(ds.get("events_60d"))
        x["last_demand_at"] = ds.get("last_event_at")
        x["product_demand_score"] = round(_f(dp.get("demand_score")), 2)
        x["product_demand_strength"] = dp.get("demand_strength") or "NONE"
        x["demand_data_confidence"] = confidence
        groups[key].append(x)
        enriched.append(x)

    product_decisions: list[dict[str, Any]] = []
    product_map: dict[str, dict[str, Any]] = {}
    for key, rows in groups.items():
        stock_units = sum(_i(r.get("inventory_quantity")) for r in rows)
        sold30 = sum(_i(r.get("units_sold_30d")) for r in rows)
        sold_prev = sum(_i(r.get("units_sold_prev_30d")) for r in rows)
        capital = round(sum(_f(r.get("capital_at_cost")) for r in rows), 2)
        retail = round(sum(_f(r.get("retail_value")) for r in rows), 2)
        stocked = [r for r in rows if _i(r.get("inventory_quantity")) > 0]
        slow = [r for r in stocked if _i(r.get("units_sold_30d")) == 0 and _i(r.get("units_sold_prev_30d")) == 0]
        slow_share = (len(slow) / len(stocked)) if stocked else 0.0
        demand_score = max([_f(r.get("product_demand_score")) for r in rows] + [0.0])
        strong_demand = demand_score >= rules.strong_product_demand_score

        if strong_demand or sold30 >= 2:
            action = "PROTEGER_PRODUCTO"
            reason = "El producto completo muestra demanda/rotación; no aplicar liquidación general por una talla lenta."
        elif (
            total_events >= rules.min_events_for_product_liquidation_confidence
            and stock_units >= rules.min_product_stock_units_for_liquidation
            and sold30 == 0 and sold_prev == 0
            and demand_score < rules.moderate_demand_score
            and slow_share >= rules.product_liquidation_slow_variant_share
        ):
            action = "LIQUIDAR_PRODUCTO"
            reason = "La mayoría de variantes con stock están lentas, sin ventas recientes ni señal Smart suficiente."
        else:
            action = "REVISAR_PRODUCTO"
            if confidence == "LOW":
                reason = "La señal de eventos Smart todavía tiene baja cobertura; evitar una liquidación de producto completo basada en ausencia de demanda."
            else:
                reason = "La evidencia no alcanza para proteger ni liquidar el producto completo."

        p = {
            "product_key": key,
            "product_title": next((str(r.get("product_title") or "") for r in rows if r.get("product_title")), ""),
            "product_action": action,
            "variant_count": len(rows),
            "stocked_variant_count": len(stocked),
            "slow_stocked_variant_count": len(slow),
            "slow_variant_share": round(slow_share, 4),
            "stock_units": stock_units,
            "units_sold_30d": sold30,
            "units_sold_prev_30d": sold_prev,
            "product_demand_score": round(demand_score, 2),
            "demand_data_confidence": confidence,
            "capital_at_cost": capital,
            "retail_value": retail,
            "reason": reason,
        }
        product_decisions.append(p)
        product_map[key] = p

    # Second pass: decide scope and price recommendation per variant.
    out: list[dict[str, Any]] = []
    for x in enriched:
        p = product_map[x["product_key"]]
        base_action = str(x.get("action") or "OBSERVAR")
        dscore = _f(x.get("demand_score"))
        pdscore = _f(x.get("product_demand_score"))
        stock = _i(x.get("inventory_quantity"))
        sold30 = _i(x.get("units_sold_30d"))
        sold_prev = _i(x.get("units_sold_prev_30d"))

        action = base_action
        scope = "VARIANT"
        reason = str(x.get("reason") or "")
        guardrail = str(x.get("guardrail") or "")

        if stock > 0 and dscore >= rules.strong_demand_score:
            action = "PROTEGER_STOCK"
            reason = "La variante tiene demanda Smart fuerte; evitar descuento y priorizar conversión."
        elif stock > 0 and dscore >= rules.moderate_demand_score:
            action = "VENDER_AHORA"
            reason = "La variante tiene intención reciente suficiente y stock; priorizar convertir demanda en caja."
        elif base_action == "LIQUIDAR":
            if p["product_action"] == "LIQUIDAR_PRODUCTO":
                action = "LIQUIDAR_PRODUCTO"
                scope = "PRODUCT"
                reason = p["reason"]
            else:
                action = "LIQUIDAR_VARIANTE"
                scope = "VARIANT"
                reason = "Esta talla/SKU está lenta; no implica rebajar automáticamente el producto completo."
                if confidence == "LOW":
                    guardrail = (guardrail + " " if guardrail else "") + "Cobertura Smart baja: validar comercialmente antes de ejecutar el descuento."
        elif base_action == "REVISAR_ROTACION" and (pdscore >= rules.strong_product_demand_score or p["product_action"] == "PROTEGER_PRODUCTO"):
            action = "REVISAR_VARIANTE"
            reason = "La variante está lenta, pero el producto completo sí muestra demanda/rotación; revisar talla antes de descontar."

        pricing = _pricing(x, action, rules)
        x.update({
            "base_action_v2": base_action,
            "action": action,
            "decision_scope": scope,
            "product_action": p["product_action"],
            "product_stock_units": p["stock_units"],
            "product_units_sold_30d": p["units_sold_30d"],
            "product_units_sold_prev_30d": p["units_sold_prev_30d"],
            "product_slow_variant_share": p["slow_variant_share"],
            "reason": reason,
            "guardrail": guardrail,
            **pricing,
        })
        out.append(x)

    rank = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda r: (
        rank.get(str(r.get("priority")), 9),
        0 if str(r.get("action")).startswith("LIQUIDAR") else 1,
        -_f(r.get("demand_score")),
        -_f(r.get("capital_at_cost")),
        str(r.get("sku")),
    ))
    product_decisions.sort(key=lambda r: (
        0 if r["product_action"] == "LIQUIDAR_PRODUCTO" else 1 if r["product_action"] == "PROTEGER_PRODUCTO" else 2,
        -_f(r.get("capital_at_cost")),
        str(r.get("product_title")),
    ))
    return out, product_decisions, demand


def build_action_plan_v21(snapshot: dict[str, Any], decisions: list[dict[str, Any]], product_decisions: list[dict[str, Any]], demand: dict[str, Any]) -> dict[str, Any]:
    k = snapshot.get("kpis") or {}
    health = snapshot.get("financial_health") or {}
    summary = demand.get("summary") or {}

    def rows(action: str) -> list[dict[str, Any]]:
        return [r for r in decisions if r.get("action") == action]

    liq_variant = rows("LIQUIDAR_VARIANTE")
    liq_product = rows("LIQUIDAR_PRODUCTO")
    sell_now = rows("VENDER_AHORA")
    protect = rows("PROTEGER_STOCK")
    lost = [r for r in decisions if r.get("action") in {"NO_RECOMPRAR_AUN", "DEMANDA_PERDIDA"}]
    product_liq_keys = {r.get("product_key") for r in product_decisions if r.get("product_action") == "LIQUIDAR_PRODUCTO"}

    liquidation_rows = liq_variant + liq_product
    unique_liquidation = {str(r.get("sku")): r for r in liquidation_rows}.values()
    capital = round(sum(_f(r.get("capital_at_cost")) for r in unique_liquidation), 2)
    recoverable = round(sum(_f(r.get("recoverable_cash_est")) for r in unique_liquidation), 2)
    expected_gp = round(sum(_f(r.get("recoverable_gross_profit_est")) for r in unique_liquidation), 2)

    priorities: list[dict[str, Any]] = []
    coverage = k.get("cash_coverage_ratio")
    if coverage is not None and _f(coverage) < 1:
        priorities.append({"priority": "P0", "action": "PROTEGER_LIQUIDEZ", "reason": f"Cobertura de caja {_f(coverage):.2f}x; evitar recompras no financiadas."})
    if liquidation_rows:
        priorities.append({"priority": "P0", "action": "LIBERAR_CAPITAL_CON_GUARDRAILS", "reason": f"{len(list(unique_liquidation))} SKU(s) candidatos; capital a costo ${capital:,.2f}; caja potencial estimada ${recoverable:,.2f}."})
    if summary.get("data_confidence") == "LOW":
        priorities.append({"priority": "P0", "action": "AMPLIAR_EVENTOS_SMART", "reason": f"Solo {summary.get('total_events', 0)} eventos alimentan la señal de demanda; no usar ausencia de eventos como prueba fuerte de falta de interés."})
    if sell_now:
        priorities.append({"priority": "P1", "action": "CONVERTIR_DEMANDA_EN_CAJA", "reason": f"{len(sell_now)} SKU(s) tienen demanda ponderada y stock disponible."})
    if lost:
        priorities.append({"priority": "P1", "action": "CAPTURAR_DEMANDA_PERDIDA", "reason": f"{len(lost)} SKU(s) tienen demanda sin stock; medir antes de recomprar."})

    return {
        "health": health,
        "liquidity": {
            "cash_available": k.get("cash_available"),
            "obligations_30d": k.get("projected_obligations_30d"),
            "cash_coverage_ratio": coverage,
            "cash_gap": k.get("projected_cash_gap"),
        },
        "demand": summary,
        "summary": {
            "total_decisions": len(decisions),
            "sell_now": len(sell_now),
            "protect_stock": len(protect),
            "liquidate_variant": len(liq_variant),
            "liquidate_product_skus": len(liq_product),
            "liquidate_product_count": len(product_liq_keys),
            "lost_demand_watchlist": len(lost),
            "liquidation_capital_at_cost": capital,
            "liquidation_recoverable_cash_est": recoverable,
            "liquidation_recoverable_gross_profit_est": expected_gp,
        },
        "priorities": priorities,
    }
