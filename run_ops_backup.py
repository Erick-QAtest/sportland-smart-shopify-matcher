from __future__ import annotations

import argparse
from pathlib import Path

from smart_ops.backup import create_backup


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sportland Smart Ops — verified PostgreSQL backup"
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--mirror-dir")
    args = parser.parse_args()

    result = create_backup(
        Path(args.project_root).resolve(),
        retention_days=args.retention_days,
        mirror_dir=Path(args.mirror_dir).expanduser() if args.mirror_dir else None,
    )

    print("Sportland Smart Ops — PostgreSQL backup")
    print(f"Database: {result.database_name}")
    print(f"Backup: {result.path}")
    print(f"Size bytes: {result.size_bytes}")
    print(f"SHA256: {result.sha256}")
    print(f"Verified: {'YES' if result.verified else 'NO'}")
    print(f"Old backups deleted: {result.deleted_old_backups}")

    if result.mirror_path:
        print(f"Mirror: {result.mirror_path}")
        print(f"Mirror size bytes: {result.mirror_size_bytes}")
        print(f"Mirror SHA256: {result.mirror_sha256}")
        print(
            "Mirror verified: "
            f"{'YES' if result.mirror_verified is True else 'NO'}"
        )
        print(
            "Old mirror backups deleted: "
            f"{result.deleted_old_mirror_backups}"
        )
    else:
        print("Mirror: not configured")

    if result.mirror_required:
        print("Mirror policy: REQUIRED")
    else:
        print("Mirror policy: OPTIONAL")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
