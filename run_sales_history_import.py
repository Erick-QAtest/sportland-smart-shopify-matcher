"""Copia el historial mensual de la pestaña "Ventas" de la hoja de finanzas a la base.

    python run_sales_history_import.py                 # simulación, no cambia nada
    python run_sales_history_import.py --aplicar       # guarda (no pisa meses capturados en el portal)
    python run_sales_history_import.py --aplicar --reemplazar
    python run_sales_history_import.py --hoja <ID de otra hoja> [--pestana "Ventas "]

Si no se indica la pestaña, busca la que empiece con "Ventas" y tenga más meses.

Al final muestra la proyección por temporada y qué tan bien habría acertado en meses pasados.
"""
from __future__ import annotations

import argparse
from datetime import date
import os
from pathlib import Path

from dotenv import load_dotenv
import requests

from smart_finance.config import FinanceConfig
from smart_finance.seasonality import calibrated_forecast, import_sales_rows, load_monthly_sales, parse_sales_tab
from smart_finance.sheets import GoogleSheetsReader
from smart_finance.utils import norm
from smart_memory.config import MemoryConfig
from smart_memory.db import connect


def _service_email(path: str) -> str:
    import json
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("client_email", "?")
    except (OSError, ValueError):
        return "?"


def money(v: float | None) -> str:
    return "—" if v is None else f"${v:,.0f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--reemplazar", action="store_true", help="también pisa meses capturados en el portal")
    parser.add_argument("--hoja", help="ID de la hoja de Google (por defecto FINANCE_SPREADSHEET_ID)")
    parser.add_argument("--pestana", help="nombre exacto de la pestaña (por defecto FINANCE_SALES_SHEET o la que empiece con Ventas)")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent / ".env")
    cfg = FinanceConfig.from_env()
    sheet_id = args.hoja or cfg.spreadsheet_id
    if not sheet_id or not cfg.service_account_file:
        print("Falta FINANCE_SPREADSHEET_ID (o --hoja) o la llave de Google en .env")
        return 2
    reader = GoogleSheetsReader(sheet_id, cfg.service_account_file)
    try:
        titles = reader.sheet_titles()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        print(f"No pude abrir la hoja {sheet_id} (HTTP {code}).")
        if code in (403, 404):
            print("Compártela (solo lectura) con el correo de la cuenta de servicio:", _service_email(cfg.service_account_file))
        return 2
    wanted = args.pestana or os.getenv("FINANCE_SALES_SHEET")
    if wanted and wanted in titles:
        candidates = [wanted]
    else:
        candidates = [t for t in titles if norm(t).startswith("ventas")]
        if wanted and not args.pestana:
            print(f"  aviso: FINANCE_SALES_SHEET='{wanted}' no existe en esta hoja; busco pestañas de ventas.")
        elif args.pestana:
            candidates = []
    best: tuple[str, list] | None = None
    for title in candidates:
        parsed = parse_sales_tab(reader.read(f"'{title}'!A:AZ"))
        print(f"  pestaña '{title}': {len(parsed)} meses con ventas")
        if parsed and (best is None or len(parsed) > len(best[1])):
            best = (title, parsed)
    if best is None:
        print("No encontré una pestaña con el formato de Ventas (año | Efectivo | Tarjeta | Plataformas | Total del mes).")
        print("Pestañas de esta hoja: " + ", ".join(repr(t) for t in titles))
        return 1
    tab, parsed = best
    print(f"  usando la pestaña '{tab}' de la hoja {sheet_id}")

    with connect(MemoryConfig.from_env()) as conn:
        stats = import_sales_rows(conn, parsed, apply=args.aplicar, replace=args.reemplazar)
        history = load_monthly_sales(conn)
    if not args.aplicar:
        history.update({(r["year"], r["month"]): r["total"] for r in parsed})

    print("APLICADO" if args.aplicar else "SIMULACIÓN (nada cambió)")
    print(f"  meses en la hoja: {len(parsed)} ({parsed[0]['month']}/{parsed[0]['year']} a {parsed[-1]['month']}/{parsed[-1]['year']})")
    print(f"  nuevos: {stats['nuevos']}  actualizados: {stats['actualizados']}  sin cambio: {stats['sin_cambio']}"
          f"  protegidos (capturados en portal): {stats['protegidos']}")

    fc = calibrated_forecast(history, date.today())
    bt = fc["backtest"]
    if fc["missing_months"]:
        print(f"  FALTAN meses por capturar: {', '.join(fc['missing_months'])}")
    if fc["trend"]:
        t = fc["trend"]
        print(f"  tendencia vs año pasado ({', '.join(t['months'])}): {t['raw'] - 1:+.0%}")
    print("  proyección (conservador / base / optimista · mismo mes año pasado):")
    for m in fc["months"]:
        print(f"    {m['label']:<16} {money(m['low']):>10} {money(m['base']):>10} {money(m['high']):>10} · {money(m['last_year'])}")
    if bt["n"]:
        print(f"  backtest {bt['n']} meses: error medio {bt['mape']:.0%} (método anterior {bt['naive_mape']:.0%});"
              f" nov-dic {bt['peak_mape']:.0%} (anterior {bt['peak_naive_mape']:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
