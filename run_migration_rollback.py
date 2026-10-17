"""Revierte una migración con su script de reversa (solo para deshacer un despliegue).

Uso:
  python run_migration_rollback.py 019_marketing_polls            # muestra qué haría
  python run_migration_rollback.py 019_marketing_polls --aplicar  # revierte

Revierte de la más nueva a la más vieja (primero 019, después 018). La reversa borra
los datos que esa migración agregó; respalda la base antes.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from smart_memory.config import MemoryConfig
from smart_memory.db import connect, rollback_migration


def main() -> int:
    parser = argparse.ArgumentParser(description="Revertir una migración de Sportland Smart")
    parser.add_argument("version", help="Ej. 019_marketing_polls")
    parser.add_argument("--aplicar", action="store_true", help="Sin esto solo se muestra el plan")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent / "database" / "migrations"
    name = args.version if args.version.endswith(".sql") else f"{args.version}.sql"
    down = root / "down" / name.replace(".sql", ".down.sql")
    if not down.exists():
        print(f"No existe script de reversa: {down}")
        return 2

    cfg = MemoryConfig.from_env()
    errors = cfg.validate()
    if errors:
        print("CONFIG ERROR:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        newer = conn.execute(
            "SELECT version FROM schema_migrations WHERE version > %s ORDER BY version",
            (name,),
        ).fetchall()
        if newer:
            print("Primero revierte las migraciones más nuevas:", ", ".join(r["version"] for r in newer))
            return 2
        if not args.aplicar:
            print(f"SIMULACIÓN: se ejecutaría {down.name} y se quitaría {name} del registro.")
            return 0
        done = rollback_migration(conn, name, root)
    print(("REVERTIDA: " if done else "No estaba aplicada: ") + name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
