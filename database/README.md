# Sportland Smart Memory v2 — Sprint 3.0

This layer rebuilds the persistent commercial memory that was lost with the old VPS.

It does **not** replace Shopify or Sportland Smart v5:

- Shopify remains the authority for products, variants, current inventory, price and orders.
- `eventos_log_v5` remains the canonical historical event source during migration.
- PostgreSQL becomes the durable memory for customer/event history and future intents, inventory snapshots and decision history.

## Safety

The memory layer is isolated from the current daily pipeline until validation passes.

By default, customer phone numbers are **not** persisted:

```text
MEMORY_STORE_PHONE=false
```

`client_uuid` is used when available. Events without `client_uuid` are preserved with `customer_id=NULL`; Sprint 3.1 will resolve identity conservatively rather than inventing it.

## Local PostgreSQL (optional)

If Docker is available:

```bash
cp database/.env.example database/.env
# Edit database/.env and choose a local password.
docker compose --env-file database/.env -f database/docker-compose.yml up -d
```

Then add only to your local root `.env`:

```text
DATABASE_URL=postgresql://sportland_app:<LOCAL_PASSWORD>@localhost:5433/sportland_smart
MEMORY_SOURCE_NAME=sportland_smart_v5
MEMORY_STORE_PHONE=false
```

Never commit the real `DATABASE_URL` or database password.

## Install

```bash
source .venv/bin/activate
pip install -r requirements-memory.txt
```

## Bootstrap schema

```bash
python run_memory_bootstrap.py
```

## Recover canonical Smart v5 history

The importer reuses the existing read-only `HistorySheetConfig`, so the current values for:

```text
SMART_SPREADSHEET_ID
SMART_SHEET_NAME=eventos_log_v5
GOOGLE_SERVICE_ACCOUNT_FILE
```

continue to be used.

Run:

```bash
python run_memory_import_v5.py
```

The import is idempotent using:

```text
event_uuid
(source, source_row_hash)
```

For Smart v5, `source_row_hash` is populated from the Sheet `event_hash`, matching the historical contract documented before the VPS was lost.

## Verify

```bash
python run_memory_verify.py
```

Expected integrity result:

```text
duplicate_event_uuid: 0
duplicate_source_hash: 0
unknown_catalog_fk: 0
VERIFY: OK
```

## Tables created

Sprint 3.0 creates:

- `event_catalog`
- `customers`
- `customer_events`
- `demand_intents`
- `inventory_snapshots`
- `decision_history`
- `schema_migrations`

and read views:

- `customer_profile_v`
- `smart_memory_health_v`

Only the historical event/customer layer is populated in Sprint 3.0. The other tables are deliberately prepared but are not yet wired into the daily pipeline.

## Next acceptance gate

Do not add the memory importer to `run_daily_sportland.sh` until all of these are true:

1. `run_memory_import_v5.py` completes successfully.
2. event counts reconcile with the canonical `LOGGED` rows.
3. `run_memory_verify.py` returns `VERIFY: OK`.
4. rerunning the importer inserts `0` new rows when the Sheet has not changed.
5. database backups are configured before production use.
