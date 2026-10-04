from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from .config import MemoryConfig


def connect(cfg: MemoryConfig) -> Connection:
    return psycopg.connect(cfg.database_url, row_factory=dict_row)


def apply_migrations(
    conn: Connection,
    migrations_dir: str | Path = "database/migrations",
) -> list[str]:
    root = Path(migrations_dir)
    if not root.exists():
        raise FileNotFoundError(f"No existe migrations dir: {root}")

    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

    applied = {
        row["version"]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }

    executed: list[str] = []
    for path in sorted(root.glob("*.sql")):
        version = path.name
        if version in applied:
            continue

        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations(version) VALUES (%s)",
                (version,),
            )
        executed.append(version)

    return executed
