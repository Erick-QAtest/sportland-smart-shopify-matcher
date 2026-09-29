from __future__ import annotations

import argparse
import json
from pathlib import Path

from sportland_matcher.config import load_config, validate_config
from sportland_matcher.smart_source import demand_events_from_rows, load_rows
from sportland_matcher.shopify_source import LocationInventory, ShopifyReadOnlyClient, ShopifyVariant
from sportland_matcher.matcher import DemandSupplyMatcher
from sportland_matcher.reporting import write_reports


def _load_shopify_fixture(path: Path) -> list[ShopifyVariant]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = []
    for raw in payload:
        item = dict(raw)
        locations = [LocationInventory(**x) for x in item.pop("locations", [])]
        variants.append(ShopifyVariant(locations=locations, **item))
    return variants


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart x Shopify V1.1 — read-only demand/supply matcher"
    )
    parser.add_argument("--env", default=".env")
    parser.add_argument("--shopify-fixture", help="Use local Shopify JSON instead of live API.")
    args = parser.parse_args()

    cfg = load_config(args.env)
    errors = validate_config(cfg, require_shopify=not bool(args.shopify_fixture))
    if errors:
        print("CONFIG ERROR:")
        for error in errors:
            print(f" - {error}")
        return 2

    print("1/4 Reading Sportland Smart...")
    rows = load_rows(cfg)
    events = demand_events_from_rows(rows, cfg)
    print(f"    Demand events: {len(events)}")

    print("2/4 Reading Shopify inventory...")
    if args.shopify_fixture:
        variants = _load_shopify_fixture(Path(args.shopify_fixture))
        print("    Shopify auth: fixture/offline")
    else:
        client = ShopifyReadOnlyClient(cfg)
        print(f"    Shopify auth: {client.auth.mode}")
        if client.auth.scope:
            print(f"    Granted scopes: {client.auth.scope}")
        variants = client.fetch_all_variants()
    print(f"    Active variants: {len(variants)}")

    print("3/4 Matching demand against supply...")
    results = DemandSupplyMatcher(variants).match_all(events)

    print("4/4 Writing reports...")
    csv_path, json_path = write_reports(
        cfg.output_dir,
        results,
        smart_event_count=len(events),
        shopify_variant_count=len(variants),
    )
    print("")
    print("DONE — no systems were modified.")
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    print(json.dumps(summary["status_counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
