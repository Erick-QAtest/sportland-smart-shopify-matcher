from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import uuid

from smart_growth.output import (
    build_summary,
    write_actions_csv,
    write_dashboard,
    write_json,
    write_results_template,
)
from smart_growth.planner import (
    actions_from_behavior_decisions,
    actions_from_commercial_opportunities,
    dedupe_actions,
)
from smart_growth.store import (
    persist_growth_actions,
    read_open_commercial_opportunities,
)
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart — Growth Integration v4.0"
    )
    parser.add_argument("--artifacts-dir", default="artifacts")
    args = parser.parse_args()

    art = Path(args.artifacts_dir)
    decisions_path = art / "smart_finance_decisions_v23.csv"
    if not decisions_path.exists():
        print(f"ERROR: missing {decisions_path}. Run Behavior Intelligence first.")
        return 2

    decisions = read_csv(decisions_path)

    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    now = datetime.now(timezone.utc)
    run_id = f"growth-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    with connect(cfg) as conn:
        apply_migrations(conn)
        commercial = read_open_commercial_opportunities(conn)

        actions = dedupe_actions(
            actions_from_behavior_decisions(decisions)
            + actions_from_commercial_opportunities(commercial)
        )

        stats = persist_growth_actions(
            conn,
            growth_run_id=run_id,
            source_artifact=str(decisions_path),
            actions=actions,
        )

        rows = conn.execute(
            """
            SELECT
                growth_action_id,
                channel,
                objective,
                priority_band,
                activation_mode,
                status,
                sku,
                product_title,
                source_type,
                source_ref,
                reason
            FROM growth_actions
            WHERE growth_run_id = %s
            ORDER BY
                CASE priority_band
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    WHEN 'SIGNAL' THEN 4
                    ELSE 5
                END,
                channel,
                growth_action_id
            """,
            (run_id,),
        ).fetchall()
        output_rows = [dict(row) for row in rows]

    summary = build_summary(output_rows)
    summary["growth_run_id"] = run_id
    summary["source_decisions"] = len(decisions)
    summary["open_commercial_opportunities"] = len(commercial)
    summary["inserted"] = stats["inserted"]
    summary["updated"] = stats["updated"]

    write_actions_csv(art / "growth_activation_plan.csv", output_rows)
    write_json(art / "growth_activation_plan.json", output_rows)
    write_json(art / "growth_channel_summary.json", summary)
    write_dashboard(
        art / "growth_activation_dashboard.html",
        output_rows,
        summary,
    )
    write_results_template(art / "growth_results_input.csv")

    print("Sportland Smart — Growth Integration v4.0")
    print(f"Behavior decisions read: {len(decisions)}")
    print(f"Open commercial opportunities: {len(commercial)}")
    print(f"Growth actions: {summary['total_actions']}")
    print(f"META: {summary['by_channel'].get('META', 0)}")
    print(f"WHATSAPP: {summary['by_channel'].get('WHATSAPP', 0)}")
    print(f"YOUTUBE: {summary['by_channel'].get('YOUTUBE', 0)}")
    print(f"GOOGLE_SEO: {summary['by_channel'].get('GOOGLE_SEO', 0)}")
    print(f"Inserted: {stats['inserted']}")
    print(f"Updated/idempotent: {stats['updated']}")
    print(f"Dashboard: {(art / 'growth_activation_dashboard.html').resolve()}")
    print("")
    print("Guardrail: DRAFT planning only. No ad, post, WhatsApp, email, or customer contact was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
