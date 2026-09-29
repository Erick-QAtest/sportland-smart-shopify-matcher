# Sportland Smart × Shopify — V1.1 Live Matcher

## First live end-to-end milestone

Sportland Smart demand events are now matched against live Shopify catalog,
variant, inventory and pricing data.

## Verified flow

Sportland Smart v5.1.1
→ Google Sheets
→ Python Matcher
→ Shopify Admin API
→ Product resolution
→ Size resolution
→ Inventory / pricing

## Live validation

- Google Sheets ingestion: OK
- Shopify client credentials: OK
- Active Shopify variants loaded: 3,159
- SKU product resolution: OK
- Explicit size resolution: OK
- Sibling variant resolution: OK
- Live inventory lookup: OK
- Live price lookup: OK
- Read-only execution: OK

## Verified scenario

Input:

- Smart SKU: 2072-26
- Requested size: 27

Resolved:

- Product: Tenis Puma Court Classic vulc FS
- Shopify SKU: 2072-27
- Shopify size: 27
- Inventory: 0
- Match confidence: HIGH

Result:

MATCH_OUT_OF_STOCK

The matcher used the supplied SKU to identify the product and the explicit
requested size to resolve the corresponding sibling variant.

## Safety

V1.1 does not modify Shopify, send notifications or write to PostgreSQL.
