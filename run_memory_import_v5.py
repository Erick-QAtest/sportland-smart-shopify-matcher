from __future__ import annotations

from smart_events.history_store import GoogleSheetHistoryStore, HistorySheetConfig
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect
from smart_memory.import_v5 import import_logged_events


def main() -> int:
    memory_cfg = MemoryConfig.from_env()
    errors = memory_cfg.validate()

    sheet_cfg = HistorySheetConfig.from_env()
    errors.extend(sheet_cfg.validate())

    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    print("1/3 Reading canonical Sportland Smart v5 history...")
    rows = GoogleSheetHistoryStore(sheet_cfg).read_logged_events()
    print(f"    LOGGED rows: {len(rows)}")

    print("2/3 Ensuring PostgreSQL schema...")
    with connect(memory_cfg) as conn:
        migrations = apply_migrations(conn)
        if migrations:
            print(f"    Applied: {', '.join(migrations)}")

        print("3/3 Importing idempotently...")
        stats = import_logged_events(conn, rows, memory_cfg)
        health = conn.execute("SELECT * FROM smart_memory_health_v").fetchone()

    print("")
    print("Sportland Smart Memory — import complete")
    print(f"Inserted events: {stats['inserted_events']}")
    print(f"Duplicates skipped: {stats['duplicate_events']}")
    print(f"Events without client_uuid: {stats['events_without_client_uuid']}")
    print(f"Customers in DB: {health['customers']}")
    print(f"Events in DB: {health['events']}")
    print("Phone persistence:", "ON" if memory_cfg.store_phone else "OFF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
