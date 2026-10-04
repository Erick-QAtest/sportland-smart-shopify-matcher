from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from smart_events.capture import capture_event
from smart_events.importers import parse_whatsapp_export
from smart_events.resolver import CatalogResolver
from smart_events.sheet_store import GoogleSheetEventStore, SheetConfig


def main() -> int:
    p = argparse.ArgumentParser(description="Sportland Smart Event Capture Sprint 2.2")
    p.add_argument("--text", default="")
    p.add_argument("--occurred-at", default="")
    p.add_argument("--channel", default="whatsapp")
    p.add_argument("--phone", default="")
    p.add_argument("--sku", default="")
    p.add_argument("--product-title", default="")
    p.add_argument("--size", default="")
    p.add_argument("--action", default="")
    p.add_argument("--source-event-id", default="")
    p.add_argument("--device", default="unknown")
    p.add_argument("--whatsapp-export", default="")
    p.add_argument("--owner-names", default="Noe,Noah,Sportland")
    p.add_argument("--catalog-csv", default=os.getenv("EVENT_CAPTURE_CATALOG_CSV", "artifacts/shopify_inventory_finance.csv"))
    args = p.parse_args()

    cfg = SheetConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR")
        for e in errors:
            print("-", e)
        return 2
    store = GoogleSheetEventStore(cfg)
    resolver = CatalogResolver.from_csv(args.catalog_csv)

    if args.whatsapp_export:
        owners = {x.strip().lower() for x in args.owner_names.split(",") if x.strip()}
        msgs = parse_whatsapp_export(args.whatsapp_export)
        logged = review = skipped = 0
        for m in msgs:
            if m.sender.strip().lower() in owners:
                continue
            result = capture_event(
                store=store, resolver=resolver, text=m.text, occurred_at=m.occurred_at,
                channel="whatsapp", source_event_id=m.source_event_id,
                device="mobile", origin="whatsapp_export_v22",
                metadata={"sender_label": "customer"},
            )
            if result["status"] == "LOGGED": logged += 1
            elif result["status"] == "NEEDS_REVIEW": review += 1
            else: skipped += 1
        print(f"WhatsApp import: LOGGED={logged} NEEDS_REVIEW={review} OTHER/SKIPPED={skipped}")
        return 0

    if not args.text and not args.action:
        p.error("usa --text/--action o --whatsapp-export")
    result = capture_event(
        store=store, resolver=resolver, text=args.text, occurred_at=args.occurred_at,
        channel=args.channel, phone_e164=args.phone, sku=args.sku,
        product_title=args.product_title, size=args.size, action=args.action,
        source_event_id=args.source_event_id, device=args.device,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"LOGGED", "SKIPPED_DUPLICATE", "NEEDS_REVIEW"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
