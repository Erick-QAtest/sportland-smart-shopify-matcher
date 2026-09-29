# Contrato observado

## Sportland_smart

Tabs observados:

- `Sheet1`
- `eventos_operador`
- `catalogos`
- `eventos_log`

`eventos_log` observado:

```text
ts_log
event_uuid
event_hash
fecha_evento
telefono
client_uuid
tipo_evento_id
tipo_evento_nombre
detalle_evento
silencio_flag
sku_producto
monto
canal
pct
moneda
actor
device
origen
meta_json
status
pg_evento_id
pg_sync_ts
```

Se observaron filas `v5.8-production` con `status=LOGGED` y `pg_evento_id`.

## Shopify

La consulta GraphQL de V1 fue validada contra el esquema Admin antes de empaquetarse.

Usa:

```text
ProductVariant.id
ProductVariant.legacyResourceId
ProductVariant.sku
ProductVariant.title
ProductVariant.price
ProductVariant.compareAtPrice
ProductVariant.inventoryQuantity
ProductVariant.selectedOptions
Product.id
Product.legacyResourceId
Product.handle
Product.title
Product.status
InventoryItem.id
InventoryItem.inventoryLevels
InventoryLevel.location
InventoryLevel.quantities(names:["available"])
```

Scopes requeridos por la validación:

```text
read_products
read_inventory
read_locations
read_markets_home
```
