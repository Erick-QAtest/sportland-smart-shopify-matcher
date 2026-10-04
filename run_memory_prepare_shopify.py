from __future__ import annotations

import argparse
import json
from pathlib import Path

from sportland_matcher.config import load_config, validate_config
from sportland_matcher.shopify_source import ShopifyReadOnlyClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one read-only Shopify inventory snapshot for a memory run"
    )
    parser.add_argument("--env", default=".env")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cfg = load_config(args.env)
    errors = validate_config(cfg, require_shopify=True)
    if errors:
        print("CONFIG ERROR:")
        for error in errors:
            print(f" - {error}")
        return 2

    print("Reading Shopify once for this orchestrated run...")
    client = ShopifyReadOnlyClient(cfg)
    print(f"Shopify auth: {client.auth.mode}")
    variants = client.fetch_all_variants()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            [variant.to_dict() for variant in variants],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Active variants: {len(variants)}")
    print(f"Snapshot fixture: {output}")
    print("Guardrail: Shopify was read-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
