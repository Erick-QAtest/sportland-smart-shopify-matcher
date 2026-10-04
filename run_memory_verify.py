from __future__ import annotations

from smart_memory.config import MemoryConfig
from smart_memory.db import connect


CHECKS = {
    "duplicate_event_uuid": """
        SELECT COUNT(*) FROM (
            SELECT event_uuid
            FROM customer_events
            WHERE event_uuid IS NOT NULL
            GROUP BY event_uuid
            HAVING COUNT(*) > 1
        ) x
    """,
    "duplicate_source_hash": """
        SELECT COUNT(*) FROM (
            SELECT source, source_row_hash
            FROM customer_events
            WHERE source_row_hash IS NOT NULL
            GROUP BY source, source_row_hash
            HAVING COUNT(*) > 1
        ) x
    """,
    "unknown_catalog_fk": """
        SELECT COUNT(*)
        FROM customer_events e
        LEFT JOIN event_catalog c ON c.event_type_id = e.event_type_id
        WHERE e.event_type_id IS NOT NULL AND c.event_type_id IS NULL
    """,
}


def main() -> int:
    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    failed = False
    with connect(cfg) as conn:
        health = conn.execute("SELECT * FROM smart_memory_health_v").fetchone()
        print("Sportland Smart Memory — health")
        for key, value in health.items():
            print(f"{key}: {value}")

        print("")
        print("Integrity checks")
        for name, query in CHECKS.items():
            count = conn.execute(query).fetchone()["count"]
            print(f"{name}: {count}")
            failed = failed or count != 0

    if failed:
        print("VERIFY: FAILED")
        return 1

    print("VERIFY: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
