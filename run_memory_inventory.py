from __future__ import annotations

import argparse
import json
from pathlib import Path

from sportland_matcher.config import load_config, validate_config
from sportland_matcher.shopify_source import (
    LocationInventory,
    ShopifyReadOnlyClient,
    ShopifyVariant,
)
from smart_memory.config import MemoryConfig
from smart_memory.db import connect
from smart_memory.inventory import capture_inventory


def _load_fixture(path: Path) -> list[ShopifyVariant]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants: list[ShopifyVariant] = []
    for raw in payload:
        item = dict(raw)
        locations = [LocationInventory(**x) for x in item.pop("locations", [])]
        variants.append(ShopifyVariant(locations=locations, **item))
    return variants


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Memory — inventory snapshots + restock detection"
    )
    parser.add_argument("--env", default=".env")
    parser.add_argument(
        "--shopify-fixture",
        help="Optional local Shopify JSON fixture instead of live Shopify.",
    )
    args = parser.parse_args()

    memory_cfg = MemoryConfig.from_env(args.env)
    memory_errors = memory_cfg.validate()
    if memory_errors:
        print("MEMORY CONFIG ERROR:")
        for error in memory_errors:
            print(f" - {error}")
        return 2

    shopify_cfg = load_config(args.env)
    shopify_errors = validate_config(
        shopify_cfg,
        require_shopify=not bool(args.shopify_fixture),
    )
    if shopify_errors:
        print("SHOPIFY CONFIG ERROR:")
        for error in shopify_errors:
            print(f" - {error}")
        return 2

    print("1/3 Reading Shopify inventory...")
    if args.shopify_fixture:
        variants = _load_fixture(Path(args.shopify_fixture))
        print("    Shopify auth: fixture/offline")
    else:
        client = ShopifyReadOnlyClient(shopify_cfg)
        print(f"    Shopify auth: {client.auth.mode}")
        variants = client.fetch_all_variants()
    print(f"    Active variants: {len(variants)}")

    print("2/3 Capturing persistent inventory snapshot...")
    with connect(memory_cfg) as conn:
        stats, transitions = capture_inventory(conn, variants)

        state_counts = conn.execute(
            """
            SELECT state, COUNT(*) AS count
            FROM demand_intents
            GROUP BY state
            ORDER BY state
            """
        ).fetchall()

    print("3/3 Restock detection complete")
    print(f"Snapshots inserted: {stats['snapshots_inserted']}")
    print(f"Restock transitions: {stats['restock_transitions']}")
    print(f"WAITING_STOCK intents promoted: {stats['intents_promoted']}")

    if transitions:
        print("")
        print("Detected restocks:")
        for item in transitions:
            print(
                f"  {item.sku or item.shopify_variant_id}: "
                f"{item.previous_quantity} -> {item.current_quantity}"
            )

    print("")
    print("Intent states:")
    for row in state_counts:
        print(f"  {row['state']}: {row['count']}")

    print("")
    print("Guardrail: Shopify was read-only. Only local PostgreSQL memory was updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
