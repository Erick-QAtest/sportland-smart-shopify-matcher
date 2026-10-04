from __future__ import annotations

import argparse
from pathlib import Path

from smart_ops.health import write_health_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Ops — health dashboard"
    )
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()

    json_path, html_path, payload = write_health_artifacts(
        Path(args.project_root).resolve()
    )

    print("Sportland Smart Ops — Health")
    print(f"Overall: {payload['overall']}")
    for reason in payload.get("reasons") or []:
        print(f" - {reason}")
    print(f"JSON: {json_path}")
    print(f"Dashboard: {html_path}")

    # FAIL means an operational dependency is actually unhealthy.
    return 1 if payload["overall"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
