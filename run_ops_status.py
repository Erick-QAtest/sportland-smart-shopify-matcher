from __future__ import annotations

import argparse
from pathlib import Path

from smart_ops.status import fail_run, finish_run, set_step, start_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Sportland Smart Ops — daily status")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start")

    step = sub.add_parser("step")
    step.add_argument("--name", required=True)

    fail = sub.add_parser("fail")
    fail.add_argument("--step", required=True)
    fail.add_argument("--exit-code", type=int, required=True)

    sub.add_parser("ok")

    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()

    if args.command == "start":
        payload, warning = start_run(root)
    elif args.command == "step":
        payload, warning = set_step(root, args.name)
    elif args.command == "fail":
        payload, warning = fail_run(
            root,
            step_name=args.step,
            exit_code=args.exit_code,
        )
    else:
        payload, warning = finish_run(root)

    print(
        f"Ops status: {payload['status']} "
        f"run={payload['run_id']} "
        f"step={payload.get('current_step')}"
    )
    if warning:
        print(f"Ops DB log warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
