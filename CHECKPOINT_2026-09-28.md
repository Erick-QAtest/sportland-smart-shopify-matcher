# Checkpoint — Sportland Smart × Shopify V1

Date verified: 2026-09-28

## What was proven end-to-end

The read-only matcher ran successfully from a Windows laptop against the real Shopify store.

Verified flow:

```text
Sportland Smart CSV export (eventos_log.csv)
        ↓
Python matcher V1
        ↑
Shopify Admin API — live inventory
        ↓
Demand vs supply classification
        ↓
CSV + JSON reports
```

## Verified runtime state

- Smart source: `csv`
- Smart sheet label in config: `eventos_log`
- Shopify host: `sportland-sales.myshopify.com`
- Shopify authentication: successful during the verified session
- Shopify inventory read: successful
- Matching step: successful
- Report generation: successful
- Guardrail: read-only; no systems were modified

## Result of the verified live run

The run read 3 demand events and completed all four stages.
The final status count shown in the terminal was:

```json
{
  "NEEDS_PRODUCT_AND_SIZE_RESOLUTION": 3
}
```

Interpretation: infrastructure/integration worked, but those three live Smart events did not contain enough resolvable product + size identity for a concrete Shopify match.

## Important current limitation

The Shopify connection is functional, but authentication is not yet self-contained inside the module.
The verified session used a temporary Admin access token loaded into the PowerShell process.

Next refactor:

```text
SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET
        ↓
module obtains access token automatically
        ↓
Shopify API
```

Until that refactor is implemented, a valid `SHOPIFY_ADMIN_ACCESS_TOKEN` must be supplied in `.env` or in the process environment.

## Not connected live yet

- Google Sheets as the active source in the verified run (CSV bridge is used)
- PostgreSQL as the matcher source/store
- WhatsApp notifications
- automatic restock actions
- price/inventory mutation

## Next functional objective

1. automate Shopify token acquisition;
2. then connect Smart directly from Google Sheets;
3. improve product + size resolution so live events can become concrete Shopify matches.
