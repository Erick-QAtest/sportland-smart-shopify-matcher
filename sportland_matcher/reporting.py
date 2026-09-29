from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import csv
import json

from .matcher import MatchResult

REPORT_FIELDS = [
    "event_uuid", "event_hash", "fecha_evento", "client_uuid", "event_type",
    "smart_sku", "requested_size", "size_source", "match_status",
    "match_confidence", "reason", "product_id", "product_legacy_id",
    "product_handle", "product_title", "variant_id", "variant_legacy_id",
    "shopify_sku", "shopify_size", "inventory_total", "available_locations",
    "price", "compare_at_price",
]


def write_reports(output_dir: Path, results: list[MatchResult], *, smart_event_count: int,
                  shopify_variant_count: int) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "demand_supply_matches.csv"
    json_path = output_dir / "demand_supply_summary.json"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for item in results:
            writer.writerow(item.to_dict())
    counts = Counter(x.match_status for x in results)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "smart_demand_events": smart_event_count,
        "shopify_variants_loaded": shopify_variant_count,
        "results": len(results),
        "status_counts": dict(sorted(counts.items())),
        "available_matches": counts.get("MATCH_AVAILABLE", 0),
        "waiting_matches": counts.get("MATCH_OUT_OF_STOCK", 0),
        "manual_resolution_required": sum(
            count for status, count in counts.items()
            if status in {
                "NEEDS_PRODUCT_RESOLUTION", "NEEDS_PRODUCT_AND_SIZE_RESOLUTION",
                "NEEDS_SIZE_RESOLUTION", "NO_SHOPIFY_MATCH", "AMBIGUOUS_MATCH", "SIZE_CONFLICT"
            }
        ),
        "guardrail": "V1 is read-only. It does not write to Smart, Postgres, Shopify, or WhatsApp.",
    }
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return csv_path, json_path
