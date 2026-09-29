# Arquitectura V1

```text
                    READ ONLY

Sportland_smart
  eventos_log
      │
      │ demanda + dedupe
      ▼
 DemandEvent
 sku + talla + client_uuid
      │
      ▼
 DemandSupplyMatcher
      ▲
      │ Shopify Admin GraphQL
      │ variants + stock + locations
      │
   Shopify
      │
      ▼
 CSV + JSON
```

Ningún módulo contiene INSERT/UPDATE/DELETE ni mutaciones GraphQL.
