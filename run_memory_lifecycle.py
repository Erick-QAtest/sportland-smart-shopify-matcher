from __future__ import annotations

from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect
from smart_memory.lifecycle import process_intent_lifecycle


def main() -> int:
    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        applied = apply_migrations(conn)
        if applied:
            print("Migrations applied:")
            for item in applied:
                print(f"  + {item}")

        stats = process_intent_lifecycle(conn)

        states = conn.execute(
            """
            SELECT state, COUNT(*) AS count
            FROM demand_intents
            GROUP BY state
            ORDER BY state
            """
        ).fetchall()

    print("")
    print("Sportland Smart Memory — Intent Lifecycle v3.5")
    print(f"Active intents evaluated: {stats['active_evaluated']}")
    print(f"PURCHASED: {stats['purchased']}")
    print(f"EXPIRED: {stats['expired']}")
    print(f"Still active: {stats['still_active']}")
    print(f"Commercial opportunities closed: {stats['opportunities_closed']}")
    print(f"New decision history rows: {stats['decision_rows_inserted']}")

    print("")
    print("Intent states:")
    for row in states:
        print(f"  {row['state']}: {row['count']}")

    print("")
    print("Guardrail: lifecycle only. No customer contact or Shopify write was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
