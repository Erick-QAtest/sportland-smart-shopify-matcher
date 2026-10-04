from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_demand_matches(path: str) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_sku_decisions(
    matches: list[dict[str, str]],
    shopify: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    demand = defaultdict(lambda: {"events": 0, "available": 0, "oos": 0})
    for r in matches:
        sku = (r.get("shopify_sku") or r.get("smart_sku") or "").strip()
        if not sku:
            continue
        d = demand[sku]
        d["events"] += 1
        if r.get("match_status") == "MATCH_AVAILABLE":
            d["available"] += 1
        if r.get("match_status") == "MATCH_OUT_OF_STOCK":
            d["oos"] += 1

    perf = {
        r.get("sku"): r
        for r in (shopify.get("orders") or {}).get("sku_performance", [])
        if r.get("sku")
    }
    inv = {
        r.get("sku"): r
        for r in (shopify.get("inventory") or {}).get("variants", [])
        if r.get("sku")
    }
    skus = set(perf) | set(inv) | set(demand)
    coverage = snapshot["kpis"].get("cash_coverage_ratio")
    buying = float(snapshot["kpis"].get("buying_capacity") or 0)
    out: list[dict[str, Any]] = []

    for sku in skus:
        p = perf.get(sku, {})
        i = inv.get(sku, {})
        d = demand.get(sku, {"events": 0, "available": 0, "oos": 0})
        stock = int(i.get("inventory_quantity") or 0)
        sold = int(p.get("units_30d") or 0)
        sold_prev = int(p.get("units_prev_30d") or 0)
        cost = i.get("unit_cost")
        price = i.get("price")
        margin = i.get("margin_pct")

        decision = "OBSERVAR"
        reason = "Sin señal financiera suficiente."
        priority = 90

        if d["oos"] > 0 and stock <= 0 and (coverage is None or coverage < 1):
            decision = "NO_RECOMPRAR_AUN"
            priority = 10
            reason = "Existe demanda no satisfecha, pero la cobertura de caja es menor a 1.0x."
        elif (
            d["oos"] > 0
            and stock <= 0
            and d["events"] >= 1
            and (margin or 0) >= 0.25
            and cost is not None
            and buying >= cost
        ):
            decision = "CANDIDATO_RECOMPRA"
            priority = 20
            reason = "Demanda no satisfecha, margen >=25% y capacidad de compra suficiente para al menos una unidad."
        elif stock > 0 and d["events"] > 0:
            decision = "VENDER_PRIORITARIO"
            priority = 5
            reason = "Hay demanda Smart y stock disponible: prioridad convertir inventario en caja."
        elif stock >= 3 and sold == 0 and sold_prev == 0:
            decision = "REVISAR_ROTACION"
            priority = 30
            reason = "Hay stock actual y no se observan unidades vendidas en los últimos 60 días consultados."
        elif stock > 0 and sold >= 2:
            decision = "PROTEGER_STOCK"
            priority = 40
            reason = "El SKU tiene ventas recientes; evitar liquidarlo sin revisar demanda y margen."

        if decision == "OBSERVAR" and not (stock > 0 or sold > 0 or d["events"] > 0):
            continue

        out.append(
            {
                "priority": priority,
                "sku": sku,
                "product_title": i.get("product_title") or p.get("product_title") or "",
                "demand_events": d["events"],
                "out_of_stock_demand": d["oos"],
                "inventory_quantity": stock,
                "units_sold_30d": sold,
                "units_sold_prev_30d": sold_prev,
                "net_sales_30d": round(float(p.get("net_sales_30d") or 0), 2),
                "price": price,
                "unit_cost": cost,
                "cost_source": i.get("cost_source"),
                "margin_pct": margin,
                "decision": decision,
                "reason": reason,
            }
        )

    out.sort(key=lambda x: (x["priority"], -x["demand_events"], -x["units_sold_30d"], x["sku"]))
    return out
