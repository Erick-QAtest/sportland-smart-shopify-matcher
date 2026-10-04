from __future__ import annotations

import json
from smart_events.behavior import build_behavior, write_behavior_artifacts
from smart_events.sheet_store import GoogleSheetEventStore, SheetConfig


def main() -> int:
    cfg = SheetConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2
    store = GoogleSheetEventStore(cfg)
    events = store.read_logged_events()
    behavior = build_behavior(events)
    write_behavior_artifacts("artifacts", behavior)
    s = behavior["summary"]
    print("Sportland Smart — Customer Behavior Sprint 2.2")
    print(f"LOGGED events: {s['logged_events']}")
    print(f"Matcher demand events (not double-counted): {s['matcher_events']}")
    print(f"Additional behavior events with SKU: {s['behavior_events_with_sku']}")
    print("Artifacts: artifacts/customer_behavior_by_sku_v22.csv")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
