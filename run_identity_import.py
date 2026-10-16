"""Copia `client_identity_map` (hoja de eventos) a `customers.phone_e164`.

Uso en el servidor:
    python run_identity_import.py            # simulación: no cambia nada
    python run_identity_import.py --aplicar  # guarda los cambios
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from smart_customer.identity_import import import_identity_map
from smart_events.sheet_store import SheetConfig
from smart_memory.config import MemoryConfig
from smart_memory.db import connect

IDENTITY_SHEET = "client_identity_map"


def read_identity_rows(cfg: SheetConfig) -> list[dict[str, object]]:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        str(Path(cfg.service_account_file).expanduser()),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    values = (
        service.spreadsheets().values()
        .get(spreadsheetId=cfg.spreadsheet_id, range=f"{IDENTITY_SHEET}!A:E")
        .execute()
        .get("values") or []
    )
    if not values:
        return []
    headers = [str(h).strip() for h in values[0]]
    return [dict(zip(headers, row)) for row in values[1:]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Guardar los cambios (sin esto solo simula).")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent / ".env")
    sheet_cfg = SheetConfig.from_env()
    problems = sheet_cfg.validate()
    if problems:
        print("ERROR DE CONFIGURACIÓN:", "; ".join(problems))
        return 2

    rows = read_identity_rows(sheet_cfg)
    with connect(MemoryConfig.from_env()) as conn:
        stats = import_identity_map(conn, rows, apply=args.aplicar)

    print("APLICADO" if stats["applied"] else "SIMULACIÓN (nada cambió; usa --aplicar para guardar)")
    for key in ("rows", "invalid", "already_ok", "phone_added", "customers_created"):
        print(f"  {key}: {stats[key]}")
    if stats["conflicts"]:
        print(f"  conflictos ({len(stats['conflicts'])}), se omitieron:")
        for line in stats["conflicts"]:
            print("   -", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
