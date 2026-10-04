from __future__ import annotations

import argparse
from pathlib import Path

from smart_finance.decision_engine_v2 import DecisionRules, build_action_plan, build_decisions, load_csv, load_json
from smart_finance.decision_output_v2 import write_csv, write_decision_dashboard, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Sportland Smart — Decision Sprint 2")
    p.add_argument("--artifacts-dir", default="artifacts")
    p.add_argument("--rules", default="decision_rules.json")
    args = p.parse_args()

    art = Path(args.artifacts_dir)
    snapshot_path = art / "financial_snapshot.json"
    shopify_path = art / "shopify_finance_snapshot.json"
    matches_path = art / "demand_supply_matches.csv"

    snapshot = load_json(snapshot_path)
    shopify = load_json(shopify_path)
    matches = load_csv(matches_path)
    rules = DecisionRules.from_json(args.rules)

    decisions = build_decisions(snapshot, shopify, matches, rules)
    plan = build_action_plan(snapshot, decisions)

    write_csv(art / "smart_finance_decisions_v2.csv", decisions)
    write_json(art / "smart_finance_action_plan.json", plan)
    write_csv(art / "liquidation_candidates.csv", [r for r in decisions if r.get("action") == "LIQUIDAR"])
    write_csv(art / "sell_now_candidates.csv", [r for r in decisions if r.get("action") == "VENDER_AHORA"])
    write_csv(art / "protect_stock.csv", [r for r in decisions if r.get("action") == "PROTEGER_STOCK"])
    write_csv(art / "lost_demand_watchlist.csv", [r for r in decisions if r.get("action") in {"NO_RECOMPRAR_AUN", "DEMANDA_PERDIDA"}])
    write_csv(art / "conditional_restock.csv", [r for r in decisions if r.get("action") == "RECOMPRA_CONDICIONAL"])
    write_decision_dashboard(art / "smart_finance_decisions_dashboard.html", snapshot, plan, decisions)

    s = plan.get("summary") or {}
    h = plan.get("health") or {}
    l = plan.get("liquidity") or {}
    print("Sportland Smart — Decision Sprint 2")
    print(f"Health: {h.get('score')} / 100 ({h.get('status')})")
    print(f"Cash coverage: {float(l.get('cash_coverage_ratio') or 0):.2f}x")
    print(f"Sell now: {s.get('sell_now', 0)}")
    print(f"Liquidate: {s.get('liquidate', 0)}")
    print(f"Protect stock: {s.get('protect_stock', 0)}")
    print(f"Lost demand watchlist: {s.get('lost_demand_watchlist', 0)}")
    print(f"Conditional restock: {s.get('conditional_restock', 0)}")
    print(f"Artifacts: {art.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
