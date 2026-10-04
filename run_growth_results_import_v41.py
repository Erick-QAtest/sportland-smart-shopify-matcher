from __future__ import annotations

import argparse
import csv
from pathlib import Path

from smart_growth.measurement_v41 import import_results_idempotently
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart — Growth Results Import v4.1"
    )
    parser.add_argument(
        "--input",
        default="artifacts/growth_results_input.csv",
    )
    args = parser.parse_args()

    path = Path(args.input)
    rows = read_csv(path)
    if not rows:
        print(f"No growth results to import from {path}")
        return 0

    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        apply_migrations(conn)
        stats = import_results_idempotently(conn, rows)

    print("Sportland Smart — Growth Results Import v4.1")
    print(f"Rows read: {stats['rows']}")
    print(f"Inserted: {stats['inserted']}")
    print(f"Duplicates skipped: {stats['duplicates']}")
    print(f"Missing actions: {stats['missing_action']}")
    print("")
    print("Next: python run_growth_performance.py")
    print("Then: python run_growth_calibrate.py")
    return 1 if stats["missing_action"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
