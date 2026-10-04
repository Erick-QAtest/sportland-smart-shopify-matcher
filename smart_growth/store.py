from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb

from smart_growth.planner import GrowthAction


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_open_commercial_opportunities(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            co.opportunity_id,
            co.action,
            co.priority_band,
            co.lifecycle_status,
            co.eligible_for_contact,
            di.resolved_sku AS sku
        FROM commercial_opportunities co
        JOIN demand_intents di ON di.intent_id = co.intent_id
        WHERE co.lifecycle_status = 'OPEN'
        ORDER BY co.opportunity_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def persist_growth_actions(
    conn: Connection,
    *,
    growth_run_id: str,
    source_artifact: str,
    actions: Iterable[GrowthAction],
) -> dict[str, int]:
    items = list(actions)
    stats = {
        "actions": len(items),
        "inserted": 0,
        "updated": 0,
    }

    with conn.transaction():
        conn.execute(
            """
            INSERT INTO growth_runs(
                growth_run_id,
                created_at,
                source_artifact,
                actions_generated,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (growth_run_id) DO UPDATE SET
                actions_generated = EXCLUDED.actions_generated,
                metadata = EXCLUDED.metadata
            """,
            (
                growth_run_id,
                utc_now(),
                source_artifact,
                len(items),
                Jsonb({
                    "automatic_activation": False,
                    "requires_human_approval": True,
                    "version": "growth-v4.0.0",
                }),
            ),
        )

        for item in items:
            existing = conn.execute(
                """
                SELECT growth_action_id
                FROM growth_actions
                WHERE action_key = %s
                """,
                (item.action_key,),
            ).fetchone()

            conn.execute(
                """
                INSERT INTO growth_actions(
                    action_key,
                    growth_run_id,
                    source_type,
                    source_ref,
                    sku,
                    product_key,
                    product_title,
                    channel,
                    objective,
                    priority_band,
                    activation_mode,
                    status,
                    requires_human_approval,
                    automatic_activation,
                    reason,
                    metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    'DRAFT', TRUE, FALSE, %s, %s
                )
                ON CONFLICT (action_key)
                DO UPDATE SET
                    growth_run_id = EXCLUDED.growth_run_id,
                    updated_at = now(),
                    priority_band = EXCLUDED.priority_band,
                    reason = EXCLUDED.reason,
                    metadata = growth_actions.metadata || EXCLUDED.metadata
                """,
                (
                    item.action_key,
                    growth_run_id,
                    item.source_type,
                    item.source_ref,
                    item.sku or None,
                    item.product_key or None,
                    item.product_title or None,
                    item.channel,
                    item.objective,
                    item.priority_band,
                    item.activation_mode,
                    item.reason,
                    Jsonb(item.metadata),
                ),
            )

            if existing:
                stats["updated"] += 1
            else:
                stats["inserted"] += 1

    return stats


def import_growth_results(
    conn: Connection,
    rows: Iterable[dict[str, Any]],
) -> dict[str, int]:
    stats = {
        "rows": 0,
        "inserted": 0,
        "missing_action": 0,
    }

    with conn.transaction():
        for raw in rows:
            stats["rows"] += 1
            action_id = str(raw.get("growth_action_id") or "").strip()
            if not action_id:
                stats["missing_action"] += 1
                continue

            action = conn.execute(
                """
                SELECT growth_action_id
                FROM growth_actions
                WHERE growth_action_id = %s
                """,
                (action_id,),
            ).fetchone()
            if not action:
                stats["missing_action"] += 1
                continue

            def number(key: str, integer: bool = False):
                value = str(raw.get(key) or "").strip()
                if value == "":
                    return None
                try:
                    return int(float(value)) if integer else float(value)
                except ValueError:
                    return None

            conn.execute(
                """
                INSERT INTO growth_results(
                    growth_action_id,
                    external_ref,
                    captured_at,
                    impressions,
                    clicks,
                    conversations,
                    orders,
                    revenue,
                    spend,
                    metadata
                )
                VALUES (
                    %s, %s, now(), %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    action_id,
                    str(raw.get("external_ref") or "").strip() or None,
                    number("impressions", True),
                    number("clicks", True),
                    number("conversations", True),
                    number("orders", True),
                    number("revenue"),
                    number("spend"),
                    Jsonb({"source": "manual_growth_results_csv"}),
                ),
            )
            conn.execute(
                """
                UPDATE growth_actions
                SET status = 'MEASURED', updated_at = now()
                WHERE growth_action_id = %s
                """,
                (action_id,),
            )
            stats["inserted"] += 1

    return stats

def read_latest_growth_actions_for_calibration(conn: Connection) -> list[dict[str, Any]]:
    latest = conn.execute(
        """
        SELECT growth_run_id
        FROM growth_runs
        ORDER BY created_at DESC, growth_run_id DESC
        LIMIT 1
        """
    ).fetchone()

    if not latest:
        return []

    rows = conn.execute(
        """
        SELECT
            growth_action_id,
            channel,
            objective,
            priority_band,
            initial_priority_band,
            status,
            sku,
            product_title,
            source_type,
            source_ref,
            metadata
        FROM growth_actions
        WHERE growth_run_id = %s
          AND status IN ('DRAFT', 'APPROVED', 'MEASURED')
        ORDER BY growth_action_id
        """,
        (latest["growth_run_id"],),
    ).fetchall()

    return [dict(row) for row in rows]

