from __future__ import annotations

import argparse
from pathlib import Path

from smart_growth.output import read_csv
from smart_growth.store import import_growth_results
from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import manually captured growth results into Sportland Smart"
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
        stats = import_growth_results(conn, rows)

    print("Sportland Smart — Growth Results Import")
    print(f"Rows read: {stats['rows']}")
    print(f"Results inserted: {stats['inserted']}")
    print(f"Missing actions: {stats['missing_action']}")
    return 1 if stats["missing_action"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
