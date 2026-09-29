# Sportland Smart × Shopify — V1.1

## Objetivo

Primera intersección **read-only** entre demanda capturada por Sportland Smart y oferta real disponible en Shopify.

V1 responde:

> Para cada señal de demanda que sí identifica producto/talla, ¿existe hoy una variante Shopify correspondiente y tiene stock?

No escribe en Postgres, no modifica Google Sheets, no modifica Shopify y no envía WhatsApp.

## Fuente Smart usada

- Spreadsheet: `Sportland_smart`
- Tab: `eventos_log`
- Contrato histórico observado: v5.x / v5.8-production

V1 deduplica reintentos por `event_uuid`.

Eventos de demanda iniciales:

- `PREGUNTA_TALLA_PRECIO`
- `PREGUNTA_MODELO_ESPECIFICO`
- `PRUEBA_MULTIPLES_MODELOS`

Solo filas `LOGGED`.

## Talla histórica

Prioridad:

1. talla explícita (`talla`, `size_norm`, `size`);
2. talla dentro de `meta_json`;
3. compatibilidad histórica con SKUs como `2033-27` o `1878L-23.5`.

La inferencia es conservadora: `951-1` no se trata como talla 1.

## Shopify

Shopify es autoridad para:

- product ID;
- variant ID;
- SKU;
- `selectedOptions` de talla;
- `inventoryQuantity`;
- `available` por location;
- precio.

La consulta usa páginas de 50 variantes y máximo 10 locations por variante, con retry/backoff para 429, `THROTTLED` y 5xx.

## Estados de salida

- `MATCH_AVAILABLE`
- `MATCH_OUT_OF_STOCK`
- `NEEDS_PRODUCT_RESOLUTION`
- `NEEDS_PRODUCT_AND_SIZE_RESOLUTION`
- `NEEDS_SIZE_RESOLUTION`
- `NO_SHOPIFY_MATCH`
- `AMBIGUOUS_MATCH`
- `SIZE_CONFLICT`

## Instalación

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Prueba offline

```bash
pytest -q
```

## Primera corrida real — opción simple

Exporta `eventos_log` como CSV y configura:

```text
SMART_SOURCE=csv
SMART_CSV_PATH=/ruta/eventos_log.csv
```

Configura `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` en `.env`. V1.1 obtiene el access token automáticamente en memoria y luego corre:

```bash
python run_match.py
```

## Corrida automática desde Google Sheets

Comparte `Sportland_smart` con una Service Account de Google como Viewer y configura:

```text
SMART_SOURCE=sheets
SMART_SPREADSHEET_ID=1rEd_6hnIOsOG7KDh1DvE0OBZEJ-Hm9EYFASzHFf5IDs
SMART_SHEET_NAME=eventos_log
SMART_RANGE=A:V
GOOGLE_SERVICE_ACCOUNT_FILE=/ruta/segura/service-account.json
```

Después:

```bash
python validate_config.py
python run_match.py
```

## Salida

```text
artifacts/demand_supply_matches.csv
artifacts/demand_supply_summary.json
```

Por privacidad el teléfono no sale en el reporte por defecto.

## Autenticación Shopify V1.1

Preferida:

```text
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
```

`SHOPIFY_ADMIN_ACCESS_TOKEN` sigue soportado como override, pero ya no es necesario generarlo manualmente en cada sesión.

## Definition of Done

1. leer `eventos_log`;
2. filtrar señales de demanda;
3. cargar variantes/stock Shopify;
4. resolver al menos un evento real;
5. distinguir disponible, agotado y no resoluble;
6. generar CSV/JSON auditable;
7. cero escrituras.

## Deliberadamente fuera de V1

- VPS/Postgres;
- transición histórica 0→stock;
- persistencia de intenciones;
- consentimiento;
- WhatsApp;
- cierre por compra;
- scheduler.
