from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from smart_events.decision_v23 import enhance_product_decisions, enhance_variant_decisions, read_csv
from smart_events.history_intelligence import HistoryRules, build_customer_intelligence, build_product_lookup, load_event_weights
from smart_events.history_store import GoogleSheetHistoryStore, HistorySheetConfig
from smart_events.output_v23 import write_csv, write_dashboard, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Sportland Smart — Behavior-aware Decisions Sprint 2.3")
    p.add_argument("--artifacts-dir", default="artifacts")
    p.add_argument("--rules", default="behavior_rules_v23.json")
    p.add_argument("--weights", default="event_weights_v23.json")
    args = p.parse_args()
    art = Path(args.artifacts_dir)

    base_decisions = art / "smart_finance_decisions_v21.csv"
    base_products = art / "product_decisions_v21.csv"
    if not base_decisions.exists() or not base_products.exists():
        if not Path("run_decisions_v21.py").exists():
            print("Falta Sprint 2.1: run_decisions_v21.py o sus artifacts")
            return 2
        rc = subprocess.call([sys.executable, "run_decisions_v21.py", "--artifacts-dir", str(art)])
        if rc:
            return rc

    cfg = HistorySheetConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    events = GoogleSheetHistoryStore(cfg).read_logged_events()
    intelligence = build_customer_intelligence(
        events,
        product_lookup=build_product_lookup(art),
        rules=HistoryRules.from_json(args.rules),
        event_weights=load_event_weights(args.weights),
    )

    decisions = enhance_variant_decisions(
        read_csv(base_decisions), intelligence["by_sku"], intelligence["by_product"]
    )
    products = enhance_product_decisions(read_csv(base_products), intelligence["by_product"])

    write_json(art / "customer_intelligence_v23.json", intelligence)
    write_csv(art / "customer_intelligence_by_sku_v23.csv", intelligence["by_sku"])
    write_csv(art / "customer_intelligence_by_product_v23.csv", intelligence["by_product"])
    write_csv(art / "customer_event_type_summary_v23.csv", intelligence["event_types"])
    write_csv(art / "smart_finance_decisions_v23.csv", decisions)
    write_csv(art / "product_decisions_v23.csv", products)
    write_csv(art / "sell_now_v23.csv", [r for r in decisions if r.get("action") == "VENDER_AHORA"])
    write_csv(art / "protect_stock_v23.csv", [r for r in decisions if r.get("action") == "PROTEGER_STOCK"])
    write_csv(art / "review_variant_v23.csv", [r for r in decisions if r.get("action") == "REVISAR_VARIANTE"])
    write_csv(art / "liquidation_plan_v23.csv", [r for r in decisions if str(r.get("action") or "").startswith("LIQUIDAR")])
    write_dashboard(art / "smart_finance_behavior_dashboard_v23.html", intelligence, decisions, products)

    def count(a: str) -> int:
        return sum(1 for r in decisions if r.get("action") == a)

    s = intelligence["summary"]
    print("Sportland Smart — Behavior Intelligence Sprint 2.3")
    print(f"LOGGED customer history: {s['logged_events']} (confidence: {s['data_confidence']})")
    print(f"Events with SKU: {s['events_with_sku']}")
    print(f"Sell now: {count('VENDER_AHORA')}")
    print(f"Protect stock: {count('PROTEGER_STOCK')}")
    print(f"Review variant: {count('REVISAR_VARIANTE')}")
    print(f"Liquidate variant: {count('LIQUIDAR_VARIANTE')}")
    print(f"Dashboard: {(art / 'smart_finance_behavior_dashboard_v23.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
