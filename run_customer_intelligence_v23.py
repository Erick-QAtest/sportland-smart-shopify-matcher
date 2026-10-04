from __future__ import annotations

import argparse
from pathlib import Path

from smart_events.history_intelligence import (
    HistoryRules,
    build_customer_intelligence,
    build_product_lookup,
    load_event_weights,
)
from smart_events.history_store import GoogleSheetHistoryStore, HistorySheetConfig
from smart_events.output_v23 import write_csv, write_json


def main() -> int:
    p = argparse.ArgumentParser(description="Sportland Smart — Full History Intelligence Sprint 2.3")
    p.add_argument("--artifacts-dir", default="artifacts")
    p.add_argument("--rules", default="behavior_rules_v23.json")
    p.add_argument("--weights", default="event_weights_v23.json")
    args = p.parse_args()

    cfg = HistorySheetConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    art = Path(args.artifacts_dir)
    events = GoogleSheetHistoryStore(cfg).read_logged_events()
    lookup = build_product_lookup(art)
    intelligence = build_customer_intelligence(
        events,
        product_lookup=lookup,
        rules=HistoryRules.from_json(args.rules),
        event_weights=load_event_weights(args.weights),
    )

    write_json(art / "customer_intelligence_summary_v23.json", intelligence["summary"])
    write_json(art / "customer_intelligence_v23.json", intelligence)
    write_csv(art / "customer_intelligence_by_sku_v23.csv", intelligence["by_sku"])
    write_csv(art / "customer_intelligence_by_product_v23.csv", intelligence["by_product"])
    write_csv(art / "customer_event_type_summary_v23.csv", intelligence["event_types"])

    s = intelligence["summary"]
    print("Sportland Smart — Full History Intelligence Sprint 2.3")
    print(f"LOGGED events: {s['logged_events']} (confidence: {s['data_confidence']})")
    print(f"Scored customer events: {s['scored_events']}")
    print(f"Events with SKU: {s['events_with_sku']}")
    print(f"Unique SKUs: {s['unique_skus']}")
    print(f"Unique products: {s['unique_products']}")
    print(f"Unique clients: {s['unique_clients']}")
    print(f"Artifacts: {art.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
