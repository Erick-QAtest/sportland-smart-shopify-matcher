from __future__ import annotations

from typing import Any

from .parsers import classify_payments
from .utils import clamp


def ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0):
        return None
    return num / den


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous


def compute_snapshot(
    *,
    shopify: dict[str, Any],
    cash: dict[str, Any],
    obligations: dict[str, Any],
    provider_balances: dict[str, float],
    reserve_cash: float = 0.0,
    manual_debts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cur = (shopify.get("orders") or {}).get("current_30d") or {}
    prev = (shopify.get("orders") or {}).get("previous_30d") or {}
    inv = shopify.get("inventory") or {}

    sales = float(cur.get("total_sales") or 0)
    prev_sales = float(prev.get("total_sales") or 0)
    sales_change = pct_change(sales, prev_sales)

    cash_total = cash.get("total")
    payment_groups = classify_payments(obligations.get("payments", []))
    obligation_total = float(obligations.get("total") or 0)
    coverage = ratio(cash_total, obligation_total)
    gap = (cash_total - obligation_total) if cash_total is not None else None
    buying_capacity = max(0.0, (cash_total or 0) - obligation_total - reserve_cash)

    debts = dict(provider_balances)
    for item in manual_debts or []:
        if not item.get("enabled", True):
            continue
        bal = float(item.get("balance", 0) or 0)
        if bal > 0:
            debts[str(item.get("name") or "Manual debt")] = bal
    debt_total = round(sum(v for v in debts.values() if v > 0), 2)

    monthly_interest = 0.0
    for p in obligations.get("payments", []):
        if "interes" in str(p.get("creditor", "")).lower():
            monthly_interest += float(p.get("amount", 0) or 0)
    for item in manual_debts or []:
        if item.get("enabled", True):
            monthly_interest += float(item.get("monthly_interest", 0) or 0)

    debt_service = payment_groups.get("finance", 0.0)
    units_30 = int(cur.get("units_sold") or 0)
    ending_units = int(inv.get("units") or 0)
    sell_through_proxy = (units_30 / (units_30 + ending_units)) if (units_30 + ending_units) > 0 else None
    coverage_days = (ending_units / (units_30 / 30.0)) if units_30 > 0 else None
    gm = float(cur.get("gross_margin") or 0)
    inv_cost = float(inv.get("cost_value_known") or 0)
    gmroi_30d_proxy = (gm / inv_cost) if inv_cost > 0 else None

    return {
        "as_of": cash.get("period") or obligations.get("period"),
        "data_sources": {
            "sales": "shopify_admin_api",
            "orders": "shopify_admin_api",
            "inventory": "shopify_admin_api",
            "prices": "shopify_admin_api",
            "costs": "shopify_admin_api_with_optional_sheet_fallback",
            "cash": "finance_sheet",
            "debt": "finance_sheet",
            "obligations": "finance_sheet",
        },
        "data_freshness": {
            "shopify_as_of": (shopify.get("orders") or {}).get("as_of"),
            "cash_as_of": cash.get("period"),
            "payments_as_of": obligations.get("period"),
        },
        "kpis": {
            "cash_available": round(cash_total, 2) if cash_total is not None else None,
            "cash_physical": round(cash.get("cash", 0), 2) if cash.get("cash") is not None else None,
            "cash_accounts": round(cash.get("accounts", 0), 2) if cash.get("accounts") is not None else None,
            "projected_obligations_30d": round(obligation_total, 2),
            "cash_coverage_ratio": coverage,
            "projected_cash_gap": round(gap, 2) if gap is not None else None,
            "buying_capacity": round(buying_capacity, 2),
            "sales_30d": round(sales, 2),
            "sales_prev_30d": round(prev_sales, 2),
            "sales_change_vs_previous_30d": sales_change,
            "orders_30d": int(cur.get("orders") or 0),
            "orders_prev_30d": int(prev.get("orders") or 0),
            "average_order_value_30d": cur.get("average_order_value"),
            "net_product_sales_30d": cur.get("net_product_sales"),
            "discounts_30d": cur.get("discounts"),
            "order_reductions_30d": cur.get("order_reductions"),
            "units_sold_30d": units_30,
            "estimated_cogs_30d": cur.get("estimated_cogs"),
            "gross_margin_30d": cur.get("gross_margin"),
            "gross_margin_pct_30d": cur.get("gross_margin_pct"),
            "cogs_missing_units_30d": cur.get("cogs_missing_units"),
            "inventory_units": ending_units,
            "inventory_retail_value": inv.get("retail_value"),
            "inventory_cost_value_known": inv.get("cost_value_known"),
            "inventory_missing_cost_units": inv.get("missing_cost_units"),
            "inventory_potential_margin_known": inv.get("potential_margin_known"),
            "sell_through_30d_proxy": sell_through_proxy,
            "inventory_coverage_days_proxy": coverage_days,
            "gmroi_30d_proxy": gmroi_30d_proxy,
            "known_debt_total": debt_total,
            "debt_to_30d_sales": ratio(debt_total, sales),
            "monthly_interest_burden": round(monthly_interest, 2),
            "interest_burden_ratio": ratio(monthly_interest, sales),
            "scheduled_debt_service": round(debt_service, 2),
            "debt_service_ratio": ratio(debt_service, sales),
            "scheduled_inventory_payments": payment_groups.get("inventory", 0.0),
            "scheduled_operating_payments": payment_groups.get("operating", 0.0),
        },
        "debts": debts,
        "payment_mix": payment_groups,
    }


def _linear_score(value: float | None, good: float, bad: float, inverse: bool = True) -> float | None:
    if value is None or good == bad:
        return None
    if inverse:
        if value <= good:
            return 100.0
        if value >= bad:
            return 0.0
        return clamp(100 * (bad - value) / (bad - good))
    if value >= good:
        return 100.0
    if value <= bad:
        return 0.0
    return clamp(100 * (value - bad) / (good - bad))


def compute_health_score(snapshot: dict[str, Any]) -> dict[str, Any]:
    k = snapshot["kpis"]
    cov = k.get("cash_coverage_ratio")
    liquidity = clamp((cov or 0) * 100) if cov is not None else None
    change = k.get("sales_change_vs_previous_30d")
    sales_trend = clamp(50 + 100 * change) if change is not None else None
    margin = _linear_score(k.get("gross_margin_pct_30d"), good=0.35, bad=0.10, inverse=False)
    debt_service = _linear_score(k.get("debt_service_ratio"), good=0.10, bad=0.50, inverse=True)
    interest = _linear_score(k.get("interest_burden_ratio"), good=0.05, bad=0.20, inverse=True)
    st = _linear_score(k.get("sell_through_30d_proxy"), good=0.25, bad=0.05, inverse=False)

    components = {
        "liquidity": {"score": liquidity, "weight": 0.30},
        "gross_margin": {"score": margin, "weight": 0.20},
        "sales_trend": {"score": sales_trend, "weight": 0.15},
        "debt_service": {"score": debt_service, "weight": 0.15},
        "interest_burden": {"score": interest, "weight": 0.10},
        "inventory_velocity": {"score": st, "weight": 0.10},
    }
    available = [x for x in components.values() if x["score"] is not None]
    ws = sum(x["weight"] for x in available)
    score = round(sum(x["score"] * x["weight"] for x in available) / ws, 1) if ws else None
    if score is None:
        status = "UNKNOWN"
    elif score < 35:
        status = "CRITICAL"
    elif score < 55:
        status = "TIGHT"
    elif score < 75:
        status = "STABLE"
    else:
        status = "HEALTHY"
    return {"score": score, "status": status, "components": components}
