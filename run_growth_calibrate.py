from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from smart_growth.calibration import (
    CALIBRATION_VERSION,
    CalibrationRules,
    calibrate_action,
)
from smart_growth.measurement_v41 import read_performance_context
from smart_growth.reporting_v41 import (
    write_csv,
    write_json,
    write_priority_dashboard,
)
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart — Growth Priority Calibration v4.1"
    )
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--rules", default="growth_rules_v41.json")
    args = parser.parse_args()

    art = Path(args.artifacts_dir)
    rules = CalibrationRules.from_json(args.rules)
    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    now = datetime.now(timezone.utc)

    with connect(cfg) as conn:
        apply_migrations(conn)
        performance = read_performance_context(conn)

        rows = conn.execute(
            """
            WITH latest_growth_run AS (
                SELECT growth_run_id
                FROM growth_runs
                ORDER BY created_at DESC, growth_run_id DESC
                LIMIT 1
            )
            SELECT
                ga.growth_action_id,
                ga.channel,
                ga.objective,
                ga.priority_band,
                ga.initial_priority_band,
                ga.status,
                ga.sku,
                ga.product_title,
                ga.source_type,
                ga.source_ref,
                ga.metadata
            FROM growth_actions ga
            JOIN latest_growth_run l
              ON l.growth_run_id = ga.growth_run_id
            WHERE ga.status IN ('DRAFT', 'APPROVED', 'MEASURED')
            ORDER BY ga.growth_action_id
            """
        ).fetchall()

        calibrated_rows = []
        with conn.transaction():
            for raw in rows:
                row = dict(raw)
                perf = performance.get(
                    (str(row["channel"]), str(row["objective"]))
                )
                result = calibrate_action(
                    row,
                    performance=perf,
                    rules=rules,
                )

                conn.execute(
                    """
                    UPDATE growth_actions
                    SET
                        initial_priority_band = COALESCE(initial_priority_band, priority_band),
                        priority_band = %s,
                        priority_score = %s,
                        calibration_version = %s,
                        calibrated_at = %s,
                        priority_reason = %s,
                        performance_context = %s,
                        updated_at = now()
                    WHERE growth_action_id = %s
                    """,
                    (
                        result.band,
                        result.score,
                        CALIBRATION_VERSION,
                        now,
                        result.reason,
                        Jsonb(result.breakdown),
                        row["growth_action_id"],
                    ),
                )

                calibrated_rows.append({
                    "growth_action_id": row["growth_action_id"],
                    "priority_band": result.band,
                    "priority_score": result.score,
                    "channel": row["channel"],
                    "objective": row["objective"],
                    "status": row["status"],
                    "sku": row["sku"],
                    "product_title": row["product_title"],
                    "source_type": row["source_type"],
                    "source_ref": row["source_ref"],
                    "performance_adjustment": result.performance_adjustment,
                    "priority_reason": result.reason,
                })

    calibrated_rows.sort(
        key=lambda r: (
            {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SIGNAL": 3}.get(
                str(r["priority_band"]), 9
            ),
            -float(r["priority_score"] or 0),
            str(r["channel"]),
            str(r["growth_action_id"]),
        )
    )

    counts = Counter(str(r["priority_band"]) for r in calibrated_rows)
    summary = {
        "version": CALIBRATION_VERSION,
        "total_actions": len(calibrated_rows),
        "by_priority": {
            "HIGH": counts.get("HIGH", 0),
            "MEDIUM": counts.get("MEDIUM", 0),
            "LOW": counts.get("LOW", 0),
            "SIGNAL": counts.get("SIGNAL", 0),
        },
        "thresholds": {
            "high": rules.high_threshold,
            "medium": rules.medium_threshold,
        },
        "performance_groups_available": len(performance),
        "guardrails": {
            "automatic_activation": False,
            "human_approval_required": True,
            "small_sample_performance": "ignored",
        },
    }

    write_csv(art / "growth_priority_plan_v41.csv", calibrated_rows)
    write_json(art / "growth_priority_plan_v41.json", calibrated_rows)
    write_json(art / "growth_priority_summary_v41.json", summary)
    write_priority_dashboard(
        art / "growth_priority_dashboard_v41.html",
        calibrated_rows,
        summary,
    )

    print("Sportland Smart — Growth Priority Calibration v4.1")
    print(f"Actions calibrated: {len(calibrated_rows)}")
    print(f"HIGH: {counts.get('HIGH', 0)}")
    print(f"MEDIUM: {counts.get('MEDIUM', 0)}")
    print(f"LOW: {counts.get('LOW', 0)}")
    print(f"SIGNAL: {counts.get('SIGNAL', 0)}")
    print(f"Performance groups available: {len(performance)}")
    print(f"Dashboard: {(art / 'growth_priority_dashboard_v41.html').resolve()}")
    print("")
    print("Guardrail: calibration only. No campaign, post, message, price, or Shopify write was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
