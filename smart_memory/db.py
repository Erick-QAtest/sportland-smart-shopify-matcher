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


def rollback_migration(
    conn: Connection,
    version: str,
    migrations_dir: str | Path = "database/migrations",
) -> bool:
    """Revierte una migración aplicada con su script `down/<nombre>.down.sql`.

    Corre en una sola transacción: o se revierte completa y sale del registro, o no
    cambia nada. Devuelve False si la migración no está aplicada.
    """
    root = Path(migrations_dir)
    name = version if version.endswith(".sql") else f"{version}.sql"
    down = root / "down" / name.replace(".sql", ".down.sql")
    if not down.exists():
        raise FileNotFoundError(f"No existe script de reversa: {down}")

    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = %s", (name,)
    ).fetchone()
    if not row:
        return False

    with conn.transaction():
        conn.execute(down.read_text(encoding="utf-8"))
        conn.execute("DELETE FROM schema_migrations WHERE version = %s", (name,))
    return True
