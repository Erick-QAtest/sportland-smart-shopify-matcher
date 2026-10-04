from __future__ import annotations

import argparse
from pathlib import Path

from smart_ops.alerts import write_alert


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Ops — local failure alert"
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--step", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--message")
    args = parser.parse_args()

    path, notified = write_alert(
        Path(args.project_root).resolve(),
        step=args.step,
        exit_code=args.exit_code,
        message=args.message,
    )
    print(f"Alert logged: {path}")
    print(f"macOS notification: {'sent' if notified else 'not available'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
