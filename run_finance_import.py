"""Copia Deudas / Próximos pagos / Caja externa de la hoja de finanzas a la base y compara.

    python run_finance_import.py                 # simulación + comparación, no cambia nada
    python run_finance_import.py --aplicar       # guarda (falla si ya hay datos)
    python run_finance_import.py --aplicar --reemplazar
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import psycopg

from smart_finance.config import FinanceConfig
from smart_finance.db_source import import_from_sheet, load_v2_inputs
from smart_finance.sheets import GoogleSheetsReader
from smart_finance.v2_parsers import parse_v2_cash, parse_v2_debts, parse_v2_obligations
from smart_memory.config import MemoryConfig
from smart_memory.db import connect


def compare(sheet: tuple, db: tuple) -> list[str]:
    (s_debts, s_cash, s_obl), (d_debts, d_cash, d_obl) = sheet, db
    diffs = []
    if s_debts != d_debts:
        diffs.append(f"Deudas: hoja {s_debts} ≠ base {d_debts}")
    for key in ("cash", "accounts", "total", "period"):
        if s_cash.get(key) != d_cash.get(key):
            diffs.append(f"Caja {key}: hoja {s_cash.get(key)} ≠ base {d_cash.get(key)}")
    # La base guarda centavos (NUMERIC 14,2): se compara redondeado a centavos.
    s_pay = [(p["date"], round(p["amount"], 2), p["display_creditor"], p["concept"]) for p in s_obl["payments"]]
    d_pay = [(p["date"], round(p["amount"], 2), p["display_creditor"], p["concept"]) for p in d_obl["payments"]]
    if s_pay != d_pay or round(s_obl["total"], 2) != round(d_obl["total"], 2):
        diffs.append(f"Pagos próximos: hoja {len(s_pay)} (${s_obl['total']:,.2f}) ≠ base {len(d_pay)} (${d_obl['total']:,.2f})")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--reemplazar", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent / ".env")
    cfg = FinanceConfig.from_env()
    if not cfg.spreadsheet_id or not cfg.service_account_file:
        print("Falta FINANCE_SPREADSHEET_ID o la llave de Google en .env")
        return 2

    reader = GoogleSheetsReader(cfg.spreadsheet_id, cfg.service_account_file)
    debts = reader.read(f"'{cfg.debts_sheet}'!A:J")
    payments = reader.read(f"'{cfg.payments_sheet}'!A:K")
    cash = reader.read(f"'{cfg.cashflow_sheet}'!A:H")
    today = date.today()
    from_sheet = (
        parse_v2_debts(debts),
        parse_v2_cash(cash),
        parse_v2_obligations(payments, as_of=today, horizon_days=cfg.horizon_days),
    )

    with connect(MemoryConfig.from_env()) as conn:
        with conn.transaction() as tx:
            stats = import_from_sheet(conn, debts=debts, payments=payments, cash=cash, apply=True, replace=args.reemplazar)
            diffs = compare(from_sheet, load_v2_inputs(conn, as_of=today, horizon_days=cfg.horizon_days))
            if not args.aplicar or diffs:
                raise psycopg.Rollback(tx)

    applied = args.aplicar and not diffs
    print("APLICADO" if applied else "SIMULACIÓN (nada cambió)")
    print(f"  deudas: {stats['debts']}  pagos programados: {stats['payments']}  cuentas de caja: {stats['cash']}")
    for line in stats["skipped"]:
        print("  aviso:", line)
    s_debts, s_cash, s_obl = from_sheet
    print(f"  deuda activa: ${sum(s_debts.values()):,.2f}  caja disponible: ${(s_cash.get('total') or 0):,.2f}"
          f"  pagos próximos {cfg.horizon_days} días: ${s_obl['total']:,.2f}")
    if diffs:
        print("  DIFERENCIAS entre hoja y base (no se guardó nada):")
        for line in diffs:
            print("   -", line)
        return 1
    print("  Hoja y base dan exactamente los mismos números.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
