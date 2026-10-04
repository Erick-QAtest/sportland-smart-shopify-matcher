from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
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
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _ratio(a: float, b: float) -> float | None:
    if not b:
        return None
    return a / b


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def load_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class DecisionRules:
    min_liquidation_stock: int = 2
    min_protect_units_30d: int = 2
    min_restock_margin_pct: float = 0.25
    min_restock_cash_coverage: float = 1.20
    min_restock_health_score: float = 55.0
    min_restock_demand_events: int = 1
    max_days_cover_protect: float = 45.0
    min_liquidation_score: float = 60.0
    min_protect_score: float = 55.0

    @classmethod
    def from_json(cls, path: str | Path | None) -> "DecisionRules":
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        allowed = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)


def build_demand_index(matches: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    demand: dict[str, dict[str, int]] = defaultdict(
        lambda: {"events": 0, "available": 0, "oos": 0, "unresolved": 0}
    )
    for row in matches:
        sku = (row.get("shopify_sku") or row.get("smart_sku") or "").strip()
        if not sku:
            continue
        d = demand[sku]
        d["events"] += 1
        status = (row.get("match_status") or "").strip()
        if status == "MATCH_AVAILABLE":
            d["available"] += 1
        elif status == "MATCH_OUT_OF_STOCK":
            d["oos"] += 1
        elif status.startswith("NEEDS_") or status in {"NO_SHOPIFY_MATCH", "AMBIGUOUS_MATCH", "SIZE_CONFLICT"}:
            d["unresolved"] += 1
    return dict(demand)


def _liquidation_score(*, stock: int, sold30: int, sold_prev: int, demand_events: int,
                       unit_cost: float | None, price: float | None, margin_pct: float | None) -> float:
    score = 0.0
    if stock >= 2:
        score += min(25.0, stock * 3.0)
    if sold30 == 0:
        score += 25.0
    elif sold30 == 1:
        score += 12.0
    if sold_prev == 0:
        score += 20.0
    elif sold_prev == 1:
        score += 8.0
    if demand_events == 0:
        score += 15.0
    if unit_cost is not None and price is not None and unit_cost > 0:
        capital = stock * unit_cost
        score += min(10.0, capital / 1500.0 * 2.0)
    if margin_pct is None:
        score -= 5.0
    elif margin_pct < 0.10:
        score -= 10.0
    elif margin_pct >= 0.25:
        score += 5.0
    return round(_clamp(score), 1)


def _protect_score(*, stock: int, sold30: int, sold_prev: int, demand_events: int,
                   margin_pct: float | None) -> float:
    score = 0.0
    score += min(45.0, sold30 * 12.0)
    score += min(20.0, sold_prev * 5.0)
    score += min(25.0, demand_events * 12.5)
    if margin_pct is not None:
        if margin_pct >= 0.35:
            score += 10.0
        elif margin_pct >= 0.25:
            score += 7.0
        elif margin_pct >= 0.15:
            score += 3.0
    if stock <= 0:
        score -= 20.0
    return round(_clamp(score), 1)


def _restock_score(*, oos_demand: int, sold30: int, sold_prev: int,
                   margin_pct: float | None, cost_known: bool) -> float:
    score = min(45.0, oos_demand * 22.5)
    score += min(25.0, sold30 * 8.0)
    score += min(15.0, sold_prev * 4.0)
    if margin_pct is not None:
        if margin_pct >= 0.35:
            score += 15.0
        elif margin_pct >= 0.25:
            score += 10.0
        elif margin_pct >= 0.15:
            score += 4.0
    if not cost_known:
        score -= 10.0
    return round(_clamp(score), 1)


def build_decisions(
    snapshot: dict[str, Any],
    shopify: dict[str, Any],
    matches: list[dict[str, str]],
    rules: DecisionRules | None = None,
) -> list[dict[str, Any]]:
    rules = rules or DecisionRules()
    demand = build_demand_index(matches)
    perf_rows = (shopify.get("orders") or {}).get("sku_performance", []) or []
    inv_rows = (shopify.get("inventory") or {}).get("variants", []) or []

    perf = {str(r.get("sku") or "").strip(): r for r in perf_rows if str(r.get("sku") or "").strip()}
    inv = {str(r.get("sku") or "").strip(): r for r in inv_rows if str(r.get("sku") or "").strip()}
    skus = set(perf) | set(inv) | set(demand)

    k = snapshot.get("kpis") or {}
    health = snapshot.get("financial_health") or {}
    health_score = _f(health.get("score"), 0.0)
    health_status = str(health.get("status") or "UNKNOWN")
    coverage = k.get("cash_coverage_ratio")
    coverage_f = None if coverage is None else _f(coverage)
    buying_capacity = _f(k.get("buying_capacity"), 0.0)
    liquidity_tight = health_status in {"CRITICAL", "TIGHT"} or (coverage_f is not None and coverage_f < 1.0)

    out: list[dict[str, Any]] = []
    for sku in sorted(skus):
        p = perf.get(sku, {})
        i = inv.get(sku, {})
        d = demand.get(sku, {"events": 0, "available": 0, "oos": 0, "unresolved": 0})

        stock = _i(i.get("inventory_quantity"))
        sold30 = _i(p.get("units_30d"))
        sold_prev = _i(p.get("units_prev_30d"))
        net_sales = _f(p.get("net_sales_30d"))
        price = i.get("price")
        cost = i.get("unit_cost")
        price_f = None if price in (None, "") else _f(price)
        cost_f = None if cost in (None, "") else _f(cost)
        margin = i.get("margin_pct")
        margin_f = None if margin in (None, "") else _f(margin)
        demand_events = _i(d.get("events"))
        oos_demand = _i(d.get("oos"))

        capital_at_cost = round(stock * cost_f, 2) if cost_f is not None else None
        retail_value = round(stock * price_f, 2) if price_f is not None else None
        daily_velocity = sold30 / 30.0 if sold30 > 0 else 0.0
        days_cover = round(stock / daily_velocity, 1) if daily_velocity > 0 else None
        margin_amount = round((price_f - cost_f), 2) if price_f is not None and cost_f is not None else None

        liq_score = _liquidation_score(
            stock=stock, sold30=sold30, sold_prev=sold_prev, demand_events=demand_events,
            unit_cost=cost_f, price=price_f, margin_pct=margin_f,
        )
        protect_score = _protect_score(
            stock=stock, sold30=sold30, sold_prev=sold_prev, demand_events=demand_events,
            margin_pct=margin_f,
        )
        restock_score = _restock_score(
            oos_demand=oos_demand, sold30=sold30, sold_prev=sold_prev,
            margin_pct=margin_f, cost_known=cost_f is not None,
        )

        action = "OBSERVAR"
        priority = "P2"
        reason = "Sin señal suficiente para una acción inmediata."
        guardrail = ""

        if stock > 0 and demand_events > 0:
            action = "VENDER_AHORA"
            priority = "P0" if liquidity_tight else "P1"
            reason = "Existe demanda Smart y stock disponible; convertir esta demanda en caja tiene prioridad."
        elif stock <= 0 and oos_demand > 0:
            if liquidity_tight:
                action = "NO_RECOMPRAR_AUN"
                priority = "P1"
                reason = "Hay demanda no satisfecha, pero la liquidez del negocio está restringida."
                guardrail = "Recompra bloqueada por liquidez hasta mejorar cobertura de caja o existir venta/preorden suficientemente segura."
            elif (
                restock_score >= 50
                and margin_f is not None and margin_f >= rules.min_restock_margin_pct
                and cost_f is not None
                and buying_capacity >= cost_f
                and (coverage_f is None or coverage_f >= rules.min_restock_cash_coverage)
                and health_score >= rules.min_restock_health_score
            ):
                action = "RECOMPRA_CONDICIONAL"
                priority = "P1"
                reason = "Demanda no satisfecha, margen y capacidad financiera cumplen las reglas de recompra."
                guardrail = "Comprar inicialmente una unidad/lote mínimo y volver a medir conversión."
            else:
                action = "DEMANDA_PERDIDA"
                priority = "P1"
                reason = "Existe demanda sin stock; conservar en watchlist hasta que margen, costo y liquidez permitan recompra."
        elif (
            stock >= rules.min_liquidation_stock
            and sold30 == 0 and sold_prev == 0
            and demand_events == 0
            and liq_score >= rules.min_liquidation_score
        ):
            action = "LIQUIDAR"
            priority = "P0" if liquidity_tight else "P1"
            reason = "Stock sin ventas observadas en 60 días y sin señal Smart; candidato a convertir capital inmovilizado en caja."
            if margin_f is None:
                guardrail = "Costo/margen incompleto: definir precio piso antes de aplicar descuento."
            elif margin_f < 0.10:
                guardrail = "Margen estrecho: no descontar automáticamente; revisar costo y precio piso."
            else:
                guardrail = "No vender por debajo del costo; usar margen disponible como límite de descuento."
        elif stock > 0 and protect_score >= rules.min_protect_score:
            action = "PROTEGER_STOCK"
            priority = "P1"
            reason = "El SKU muestra velocidad de venta y/o demanda; evitar liquidarlo."
            if days_cover is not None and days_cover <= rules.max_days_cover_protect:
                guardrail = f"Cobertura estimada de {days_cover} días; vigilar agotamiento."
        elif stock > 0 and sold30 == 0 and sold_prev == 0:
            action = "REVISAR_ROTACION"
            priority = "P2"
            reason = "No hay ventas observadas en 60 días; todavía no alcanza umbral de liquidación."
        elif stock > 0 and cost_f is None:
            action = "COMPLETAR_COSTO"
            priority = "P2"
            reason = "Sin costo no puede calcularse margen ni precio piso con seguridad."

        if action == "OBSERVAR" and not (stock or sold30 or sold_prev or demand_events):
            continue

        out.append({
            "priority": priority,
            "action": action,
            "sku": sku,
            "product_title": i.get("product_title") or p.get("product_title") or "",
            "inventory_quantity": stock,
            "units_sold_30d": sold30,
            "units_sold_prev_30d": sold_prev,
            "net_sales_30d": round(net_sales, 2),
            "demand_events": demand_events,
            "out_of_stock_demand": oos_demand,
            "unresolved_demand": _i(d.get("unresolved")),
            "price": price_f,
            "unit_cost": cost_f,
            "cost_source": i.get("cost_source"),
            "margin_amount": margin_amount,
            "margin_pct": margin_f,
            "capital_at_cost": capital_at_cost,
            "retail_value": retail_value,
            "days_cover_30d": days_cover,
            "liquidation_score": liq_score,
            "protect_score": protect_score,
            "restock_score": restock_score,
            "reason": reason,
            "guardrail": guardrail,
        })

    rank = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda r: (
        rank.get(str(r.get("priority")), 9),
        -_f(r.get("liquidation_score")),
        -_f(r.get("protect_score")),
        -_i(r.get("demand_events")),
        str(r.get("sku")),
    ))
    return out


def build_action_plan(snapshot: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    k = snapshot.get("kpis") or {}
    health = snapshot.get("financial_health") or {}
    coverage = k.get("cash_coverage_ratio")
    cash = _f(k.get("cash_available"))
    obligations = _f(k.get("projected_obligations_30d"))
    gap = _f(k.get("projected_cash_gap"), cash - obligations)

    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        by_action[str(row.get("action") or "OBSERVAR")].append(row)

    liquidation = by_action.get("LIQUIDAR", [])
    sell_now = by_action.get("VENDER_AHORA", [])
    protect = by_action.get("PROTEGER_STOCK", [])
    lost = by_action.get("NO_RECOMPRAR_AUN", []) + by_action.get("DEMANDA_PERDIDA", [])
    restock = by_action.get("RECOMPRA_CONDICIONAL", [])

    liquid_cost = round(sum(_f(r.get("capital_at_cost")) for r in liquidation), 2)
    liquid_retail = round(sum(_f(r.get("retail_value")) for r in liquidation), 2)
    sell_now_retail = round(sum(_f(r.get("retail_value")) for r in sell_now), 2)

    priorities: list[dict[str, Any]] = []
    if coverage is not None and _f(coverage) < 1.0:
        priorities.append({
            "priority": "P0",
            "action": "PROTEGER_LIQUIDEZ",
            "reason": f"La caja cubre solo {_f(coverage):.2f}x de las obligaciones a 30 días.",
            "metric": {"cash": cash, "obligations_30d": obligations, "cash_gap": gap},
        })
    if sell_now:
        priorities.append({
            "priority": "P0" if (coverage is not None and _f(coverage) < 1.0) else "P1",
            "action": "CONVERTIR_DEMANDA_EN_CAJA",
            "reason": f"Hay {len(sell_now)} SKU(s) con demanda Smart y stock disponible.",
            "metric": {"candidate_skus": len(sell_now), "retail_value_in_candidates": sell_now_retail},
        })
    if liquidation:
        priorities.append({
            "priority": "P0" if (coverage is not None and _f(coverage) < 1.0) else "P1",
            "action": "LIBERAR_CAPITAL_DE_STOCK_LENTO",
            "reason": f"Hay {len(liquidation)} SKU(s) sin ventas observadas en 60 días y sin señal Smart.",
            "metric": {"capital_at_cost": liquid_cost, "retail_value": liquid_retail},
        })
    if lost:
        priorities.append({
            "priority": "P1",
            "action": "MEDIR_DEMANDA_PERDIDA_SIN_RECOMPRAR_A_CIEGAS",
            "reason": f"Hay {len(lost)} SKU(s) con demanda agotada o no satisfecha.",
            "metric": {"candidate_skus": len(lost)},
        })
    if protect:
        priorities.append({
            "priority": "P1",
            "action": "PROTEGER_STOCK_QUE_SI_ROTA",
            "reason": f"Hay {len(protect)} SKU(s) con señales de rotación/demanda que no deben liquidarse sin revisión.",
            "metric": {"candidate_skus": len(protect)},
        })
    if restock:
        priorities.append({
            "priority": "P1",
            "action": "RECOMPRA_CONTROLADA",
            "reason": f"Hay {len(restock)} SKU(s) que cumplen las reglas financieras de recompra.",
            "metric": {"candidate_skus": len(restock)},
        })

    return {
        "health": health,
        "liquidity": {
            "cash_available": cash,
            "obligations_30d": obligations,
            "cash_coverage_ratio": coverage,
            "cash_gap": gap,
        },
        "summary": {
            "total_decisions": len(decisions),
            "sell_now": len(sell_now),
            "liquidate": len(liquidation),
            "protect_stock": len(protect),
            "lost_demand_watchlist": len(lost),
            "conditional_restock": len(restock),
            "liquidation_capital_at_cost": liquid_cost,
            "liquidation_retail_value": liquid_retail,
        },
        "priorities": priorities,
    }
