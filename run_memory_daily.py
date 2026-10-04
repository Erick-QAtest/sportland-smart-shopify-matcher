from __future__ import annotations

import argparse
from pathlib import Path
import sys

from smart_memory.orchestrator import execute_daily


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Memory — daily orchestrator v3.6"
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Sportland project root",
    )
    parser.add_argument(
        "--keep-shopify-fixture",
        action="store_true",
        help="Keep temporary Shopify fixture for debugging.",
    )
    args = parser.parse_args()

    return execute_daily(
        project_root=Path(args.project_root),
        python_executable=sys.executable,
        keep_fixture=args.keep_shopify_fixture,
    )


if __name__ == "__main__":
    raise SystemExit(main())
