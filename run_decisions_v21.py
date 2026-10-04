from __future__ import annotations

import argparse
from pathlib import Path

from smart_finance.decision_engine_v2 import DecisionRules as BaseDecisionRules, load_csv, load_json
from smart_finance.decision_engine_v21 import DecisionRulesV21, build_action_plan_v21, build_decisions_v21
from smart_finance.decision_output_v21 import write_csv, write_dashboard, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Sportland Smart — Demand Intelligence Sprint 2.1")
    p.add_argument("--artifacts-dir", default="artifacts")
    p.add_argument("--rules", default="decision_rules_v21.json")
    p.add_argument("--base-rules", default="decision_rules.json")
    args = p.parse_args()

    art = Path(args.artifacts_dir)
    snapshot = load_json(art / "financial_snapshot.json")
    shopify = load_json(art / "shopify_finance_snapshot.json")
    matches = load_csv(art / "demand_supply_matches.csv")

    decisions, products, demand = build_decisions_v21(
        snapshot,
        shopify,
        matches,
        base_rules=BaseDecisionRules.from_json(args.base_rules),
        rules=DecisionRulesV21.from_json(args.rules),
    )
    plan = build_action_plan_v21(snapshot, decisions, products, demand)

    write_json(art / "demand_intelligence_v21.json", demand)
    write_csv(art / "demand_intelligence_by_sku.csv", demand.get("by_sku", []))
    write_csv(art / "demand_intelligence_by_product.csv", demand.get("by_product", []))
    write_csv(art / "smart_finance_decisions_v21.csv", decisions)
    write_csv(art / "product_decisions_v21.csv", products)
    write_csv(art / "liquidation_plan_v21.csv", [r for r in decisions if str(r.get("action")).startswith("LIQUIDAR_")])
    write_csv(art / "sell_now_v21.csv", [r for r in decisions if r.get("action") == "VENDER_AHORA"])
    write_csv(art / "protect_stock_v21.csv", [r for r in decisions if r.get("action") == "PROTEGER_STOCK"])
    write_json(art / "smart_finance_action_plan_v21.json", plan)
    write_dashboard(art / "smart_finance_demand_dashboard_v21.html", plan, decisions, products)

    s = plan.get("summary") or {}
    d = plan.get("demand") or {}
    h = plan.get("health") or {}
    print("Sportland Smart — Demand Intelligence Sprint 2.1")
    print(f"Health: {h.get('score')} / 100 ({h.get('status')})")
    print(f"Customer events: {d.get('total_events', 0)} (confidence: {d.get('data_confidence', 'LOW')})")
    print(f"Demand -> sell now: {s.get('sell_now', 0)}")
    print(f"Protect stock: {s.get('protect_stock', 0)}")
    print(f"Liquidate variant: {s.get('liquidate_variant', 0)}")
    print(f"Liquidate product: {s.get('liquidate_product_count', 0)} product(s)")
    print(f"Capital at cost in liquidation candidates: {float(s.get('liquidation_capital_at_cost') or 0):.2f}")
    print(f"Estimated recoverable cash: {float(s.get('liquidation_recoverable_cash_est') or 0):.2f}")
    print(f"Artifacts: {art.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
