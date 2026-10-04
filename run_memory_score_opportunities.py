from __future__ import annotations

from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect
from smart_memory.scoring import score_commercial_opportunities


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

        stats = score_commercial_opportunities(conn)

        rows = conn.execute(
            """
            SELECT
                co.opportunity_id,
                co.intent_id,
                co.action,
                co.eligible_for_contact,
                co.opportunity_score,
                co.priority_band,
                co.score_version,
                di.resolved_sku,
                di.requested_size
            FROM commercial_opportunities co
            JOIN demand_intents di ON di.intent_id = co.intent_id
            WHERE co.lifecycle_status = 'OPEN'
            ORDER BY
                CASE co.priority_band
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    WHEN 'HOLD' THEN 4
                    WHEN 'SIGNAL' THEN 5
                    ELSE 6
                END,
                co.opportunity_score DESC NULLS LAST,
                co.opportunity_id
            """
        ).fetchall()

    print("")
    print("Sportland Smart Memory — Opportunity Scoring v3.4")
    print(f"Opportunities found: {stats['opportunities']}")
    print(f"Scored: {stats['scored']}")
    print(f"HIGH: {stats['high']}")
    print(f"MEDIUM: {stats['medium']}")
    print(f"LOW: {stats['low']}")
    print(f"HOLD: {stats['hold']}")
    print(f"SIGNAL: {stats['signal']}")
    print(f"New decision history rows: {stats['decision_rows_inserted']}")

    if rows:
        print("")
        print("Prioritized opportunities:")
        for row in rows:
            print(
                f"  #{row['opportunity_id']} "
                f"intent={row['intent_id']} "
                f"sku={row['resolved_sku'] or '-'} "
                f"size={row['requested_size'] or '-'} "
                f"score={row['opportunity_score']} "
                f"priority={row['priority_band']} "
                f"commercial_action={row['action']}"
            )

    print("")
    print("Guardrail: scoring only. No customer contact or Shopify write was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
