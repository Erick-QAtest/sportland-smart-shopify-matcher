# V1.1 — automatic Shopify authentication

## Cerrado en esta versión

- Agregado `SHOPIFY_CLIENT_ID`.
- Agregado `SHOPIFY_CLIENT_SECRET`.
- El matcher solicita su propio Admin access token por `client_credentials`.
- El token se mantiene en memoria; no se escribe en disco.
- `SHOPIFY_ADMIN_ACCESS_TOKEN` sigue soportado como override/backward compatibility.
- `validate_config.py` informa el modo de autenticación.
- El validador rechaza valores placeholder comunes.
- El flujo sigue siendo read-only.

## Aún pendiente

- Smart en vivo desde Google Sheets como fuente por defecto.
- Resolución más rica de producto + talla.
- Postgres.
- alertas/restock/WhatsApp.
