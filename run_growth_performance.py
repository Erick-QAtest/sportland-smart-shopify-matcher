from __future__ import annotations

import argparse
from pathlib import Path

from smart_growth.measurement_v41 import read_performance_summary
from smart_growth.reporting_v41 import (
    write_json,
    write_performance_dashboard,
)
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart — Growth Performance v4.1"
    )
    parser.add_argument("--artifacts-dir", default="artifacts")
    args = parser.parse_args()

    art = Path(args.artifacts_dir)
    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        apply_migrations(conn)
        rows = read_performance_summary(conn)

    totals = {
        "groups": len(rows),
        "impressions": sum(int(r.get("impressions") or 0) for r in rows),
        "clicks": sum(int(r.get("clicks") or 0) for r in rows),
        "orders": sum(int(r.get("orders") or 0) for r in rows),
        "revenue": round(sum(float(r.get("revenue") or 0) for r in rows), 2),
        "spend": round(sum(float(r.get("spend") or 0) for r in rows), 2),
    }

    write_json(art / "growth_performance_v41.json", {
        "summary": totals,
        "by_channel_objective": rows,
    })
    write_performance_dashboard(
        art / "growth_performance_dashboard_v41.html",
        rows,
    )

    print("Sportland Smart — Growth Performance v4.1")
    print(f"Measured groups: {totals['groups']}")
    print(f"Impressions: {totals['impressions']}")
    print(f"Clicks: {totals['clicks']}")
    print(f"Orders: {totals['orders']}")
    print(f"Revenue: {totals['revenue']:.2f}")
    print(f"Spend: {totals['spend']:.2f}")
    print(f"Dashboard: {(art / 'growth_performance_dashboard_v41.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
