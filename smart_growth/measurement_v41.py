from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable

from psycopg import Connection
from psycopg.types.json import Jsonb


METRIC_FIELDS = (
    "impressions",
    "clicks",
    "conversations",
    "orders",
    "revenue",
    "spend",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any, *, integer: bool = False):
    text = _text(value)
    if text == "":
        return None
    try:
        return int(float(text)) if integer else float(text)
    except (TypeError, ValueError):
        return None


def result_key(row: dict[str, Any]) -> str:
    parts = [
        _text(row.get("growth_action_id")),
        _text(row.get("external_ref")),
    ]
    parts.extend(_text(row.get(key)) for key in METRIC_FIELDS)
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def import_results_idempotently(
    conn: Connection,
    rows: Iterable[dict[str, Any]],
) -> dict[str, int]:
    stats = {
        "rows": 0,
        "inserted": 0,
        "duplicates": 0,
        "missing_action": 0,
    }

    with conn.transaction():
        for raw in rows:
            stats["rows"] += 1
            action_id = _text(raw.get("growth_action_id"))
            if not action_id:
                stats["missing_action"] += 1
                continue

            exists = conn.execute(
                """
                SELECT growth_action_id
                FROM growth_actions
                WHERE growth_action_id = %s
                """,
                (action_id,),
            ).fetchone()
            if not exists:
                stats["missing_action"] += 1
                continue

            key = result_key(raw)
            inserted = conn.execute(
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
                    metadata,
                    result_key
                )
                VALUES (
                    %s, %s, now(),
                    %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (result_key) DO NOTHING
                RETURNING growth_result_id
                """,
                (
                    action_id,
                    _text(raw.get("external_ref")) or None,
                    _number(raw.get("impressions"), integer=True),
                    _number(raw.get("clicks"), integer=True),
                    _number(raw.get("conversations"), integer=True),
                    _number(raw.get("orders"), integer=True),
                    _number(raw.get("revenue")),
                    _number(raw.get("spend")),
                    Jsonb({
                        "source": "manual_growth_results_csv_v41",
                        "idempotent": True,
                    }),
                    key,
                ),
            ).fetchone()

            if inserted:
                stats["inserted"] += 1
                conn.execute(
                    """
                    UPDATE growth_actions
                    SET status = 'MEASURED', updated_at = now()
                    WHERE growth_action_id = %s
                    """,
                    (action_id,),
                )
            else:
                stats["duplicates"] += 1

    return stats


def read_performance_context(conn: Connection) -> dict[tuple[str, str], dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            channel,
            objective,
            actions_with_results,
            result_rows,
            impressions,
            clicks,
            conversations,
            orders,
            revenue,
            spend,
            ctr,
            click_to_order_rate,
            roas
        FROM growth_performance_by_channel_objective
        """
    ).fetchall()

    return {
        (str(row["channel"]), str(row["objective"])): dict(row)
        for row in rows
    }


def read_performance_summary(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            channel,
            objective,
            actions_with_results,
            result_rows,
            impressions,
            clicks,
            conversations,
            orders,
            revenue,
            spend,
            ctr,
            click_to_order_rate,
            roas
        FROM growth_performance_by_channel_objective
        ORDER BY revenue DESC NULLS LAST, orders DESC, impressions DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]
