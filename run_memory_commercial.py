from __future__ import annotations

from smart_memory.commercial import evaluate_restock_opportunities
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


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

        stats = evaluate_restock_opportunities(conn)

        rows = conn.execute(
            """
            SELECT
                co.opportunity_id,
                co.intent_id,
                co.client_uuid,
                di.resolved_sku,
                di.requested_size,
                co.action,
                co.eligible_for_contact,
                co.reason_code,
                co.hold_until
            FROM commercial_opportunities co
            JOIN demand_intents di ON di.intent_id = co.intent_id
            ORDER BY co.opportunity_id
            """
        ).fetchall()

    print("")
    print("Sportland Smart Memory — Commercial Opportunity v3.3")
    print(f"RESTOCK_MATCH evaluated: {stats['restock_matches']}")
    print(f"CONTACT_CANDIDATE: {stats['contact_candidates']}")
    print(f"HOLD: {stats['hold']}")
    print(f"DEMAND_SIGNAL_ONLY: {stats['demand_signal_only']}")
    print(f"Opportunities upserted: {stats['opportunities_upserted']}")
    print(f"New decision history rows: {stats['decision_rows_inserted']}")

    if rows:
        print("")
        print("Current commercial opportunities:")
        for row in rows:
            print(
                f"  #{row['opportunity_id']} intent={row['intent_id']} "
                f"sku={row['resolved_sku'] or '-'} "
                f"size={row['requested_size'] or '-'} "
                f"=> {row['action']} "
                f"eligible={'yes' if row['eligible_for_contact'] else 'no'} "
                f"reason={row['reason_code']}"
            )

    print("")
    print("Guardrail: no WhatsApp, email, Shopify, or customer contact was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
