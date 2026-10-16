from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv

from smart_memory.config import MemoryConfig
from smart_memory.db import apply_migrations, connect
from smart_commerce.marketing_v62 import importar_calendario


def main() -> int:
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    cfg = MemoryConfig.from_env(str(root / ".env"))
    errors = cfg.validate()
    if errors:
        print("ERROR DE CONFIGURACIÓN:", "; ".join(errors))
        return 2

    with connect(cfg) as conn:
        applied = apply_migrations(conn)
        if applied:
            print("Migraciones aplicadas:", ", ".join(applied))
        else:
            print("Esquema ya actualizado.")

        n = importar_calendario(
            conn,
            root / "datos" / "calendario_marketing_octubre_2026.csv",
        )

    print(f"Calendario de marketing cargado: {n} acciones.")
    print("Amazon listo para importar reportes CSV.")
    print("WhatsApp 1:1 permanece en modo borrador/revisión.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
