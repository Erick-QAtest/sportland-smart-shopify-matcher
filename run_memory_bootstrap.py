from __future__ import annotations

from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect


def main() -> int:
    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        executed = apply_migrations(conn)

    if executed:
        print("Sportland Smart Memory — migrations applied:")
        for version in executed:
            print(f"  + {version}")
    else:
        print("Sportland Smart Memory — schema already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
