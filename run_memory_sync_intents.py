from __future__ import annotations

import argparse

from smart_memory.config import MemoryConfig
from smart_memory.db import connect
from smart_memory.intents import read_match_rows, sync_match_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Memory — persist matcher results as demand intents"
    )
    parser.add_argument(
        "--matches",
        default="artifacts/demand_supply_matches.csv",
        help="Matcher CSV artifact",
    )
    args = parser.parse_args()

    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    rows = read_match_rows(args.matches)
    print(f"1/2 Matcher rows: {len(rows)}")

    with connect(cfg) as conn:
        stats = sync_match_rows(conn, rows)

        intents = conn.execute(
            """
            SELECT
                intent_id,
                client_uuid,
                smart_sku,
                resolved_sku,
                requested_size,
                match_status,
                state
            FROM demand_intents
            ORDER BY intent_id
            """
        ).fetchall()

    print("2/2 Demand intents synchronized")
    print(f"Inserted: {stats['inserted']}")
    print(f"Updated: {stats['updated']}")
    print(f"Missing source event: {stats['missing_source_event']}")
    print(f"AVAILABLE: {stats['available']}")
    print(f"WAITING_STOCK: {stats['waiting_stock']}")
    print(f"UNRESOLVED: {stats['unresolved']}")
    print("")
    print("Current intents:")
    for row in intents:
        print(
            f"  #{row['intent_id']} "
            f"{row['smart_sku'] or '-'} -> {row['resolved_sku'] or '-'} "
            f"size={row['requested_size'] or '-'} "
            f"{row['match_status'] or '-'} => {row['state']} "
            f"client={'yes' if row['client_uuid'] else 'no'}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
