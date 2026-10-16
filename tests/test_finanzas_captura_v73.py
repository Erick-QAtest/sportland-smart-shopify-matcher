from datetime import date, timedelta
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from smart_finance.config import FinanceConfig
from smart_finance.db_source import import_from_sheet, load_v2_inputs
from smart_finance.v2_parsers import parse_v2_cash, parse_v2_debts, parse_v2_obligations
from smart_portal.finanzas_captura_v73 import guardar_caja, guardar_deudas, guardar_pagos, render_finanzas_captura

TODAY = date.today()
DB_URL = os.getenv("SPORTLAND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Define SPORTLAND_TEST_DATABASE_URL para las pruebas con base de datos.")

SHEET_DEBTS = [
    ["Deudas al corte"],
    ["Acreedor", "Saldo actual (MXN)", "Estado", "Notas"],
    ["Typhoon", "45,000.50", "Activa", ""],
    ["Palermo", "12000", "Liquidada", ""],
    ["Préstamo Fojal", "$30,000", "activa", "6 meses"],
    ["TOTAL", "87000.5", "", ""],
]
SHEET_PAYMENTS = [
    ["Fecha", "Concepto", "Acreedor", "Monto (MXN)", "Estado", "Cuenta / referencia", "Categoria"],
    [(TODAY + timedelta(days=3)).isoformat(), "Renta", "Arrendador", "8500", "Pendiente", "BBVA", "Fijos"],
    [(TODAY + timedelta(days=10)).strftime("%d/%m/%Y"), "Abono", "Typhoon", "5000", "Por confirmar", "", "Proveedores"],
    [(TODAY + timedelta(days=12)).isoformat(), "Ya pagado", "Raga", "999", "Pagado", "", ""],
    [(TODAY - timedelta(days=2)).isoformat(), "Vencido", "Luz", "700", "Pendiente", "", ""],
    [(TODAY + timedelta(days=45)).isoformat(), "Fuera de horizonte", "IMSS", "3200", "Pendiente", "", ""],
    [(TODAY + timedelta(days=5)).isoformat(), "Sin acreedor", "", "150", "Pendiente", "", ""],
]
SHEET_CASH = [
    ["Fecha corte", "Tipo", "Cuenta", "Saldo actual (MXN)", "Disponible"],
    [TODAY.isoformat(), "Efectivo", "Caja tienda", "3,200", "Sí"],
    [TODAY.isoformat(), "Cuenta bancaria", "BBVA", "18500.75", "si"],
    [TODAY.isoformat(), "Cuenta bancaria", "Inversión", "50000", "No"],
]


@pytest.fixture
def db():
    conn = psycopg.connect(DB_URL, row_factory=dict_row)
    with conn.transaction() as tx:
        yield conn
        raise psycopg.Rollback(tx)
    conn.close()


def from_sheet():
    return (
        parse_v2_debts(SHEET_DEBTS),
        parse_v2_cash(SHEET_CASH),
        parse_v2_obligations(SHEET_PAYMENTS, as_of=TODAY, horizon_days=30),
    )


def test_database_gives_exactly_the_same_numbers_as_the_sheet(db):
    stats = import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=True)
    assert (stats["debts"], stats["payments"], stats["cash"]) == (3, 6, 3)
    sheet_debts, sheet_cash, sheet_obl = from_sheet()
    db_debts, db_cash, db_obl = load_v2_inputs(db, as_of=TODAY, horizon_days=30)
    assert db_debts == sheet_debts == {"Typhoon": 45000.5, "Préstamo Fojal": 30000.0}
    assert db_cash == sheet_cash
    assert db_cash["total"] == 21700.75
    key = lambda o: [(p["date"], p["amount"], p["display_creditor"], p["concept"], p["status"]) for p in o["payments"]]
    assert key(db_obl) == key(sheet_obl)
    assert db_obl["total"] == sheet_obl["total"] == 13650.0


def test_import_dry_run_changes_nothing_and_refuses_to_mix(db):
    import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=False)
    assert db.execute("SELECT count(*) AS n FROM finance_debts").fetchone()["n"] == 0
    import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=True)
    with pytest.raises(RuntimeError):
        import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=True)
    import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=True, replace=True)
    assert db.execute("SELECT count(*) AS n FROM finance_debts").fetchone()["n"] == 3


def form(prefix, rows):
    data = {f"{prefix}_n": [str(len(rows))]}
    for i, row in enumerate(rows):
        for name, value in row.items():
            data[f"{prefix}_{name}_{i}"] = [value]
    return data


def test_cash_insert_then_update_is_logged_and_unchanged_rows_are_not(db):
    result = guardar_caja(db, form("caja", [{"nombre": "BBVA", "tipo": "Cuenta", "saldo": "1,000", "disponible": "si"}]), actor="socio")
    assert result.ok and result.inserted == 1
    account = db.execute("SELECT * FROM finance_cash_balances").fetchone()
    same = {"id": str(account["account_id"]), "nombre": "BBVA", "tipo": "Cuenta", "saldo": "1000.00", "disponible": "si"}
    assert guardar_caja(db, form("caja", [same]), actor="socio").updated == 0
    changed = dict(same, saldo="2500")
    assert guardar_caja(db, form("caja", [changed]), actor="socio").updated == 1
    log = db.execute("SELECT action, actor FROM finance_change_log WHERE table_name = 'finance_cash_balances' ORDER BY change_id").fetchall()
    assert [(r["action"], r["actor"]) for r in log] == [("insert", "socio"), ("update", "socio")]


def test_invalid_row_saves_nothing_in_that_section(db):
    rows = [
        {"fecha": (TODAY + timedelta(days=2)).isoformat(), "acreedor": "Renta", "monto": "8500", "estado": "pendiente"},
        {"fecha": "no-es-fecha", "acreedor": "", "monto": "-5", "estado": "pendiente"},
    ]
    result = guardar_pagos(db, form("pagos", rows), actor="socio")
    assert not result.ok and set(result.errors) == {1}
    assert db.execute("SELECT count(*) AS n FROM finance_scheduled_payments").fetchone()["n"] == 0


def test_marking_paid_and_liquidated_removes_them_from_the_engine_inputs(db):
    guardar_pagos(db, form("pagos", [{"fecha": (TODAY + timedelta(days=4)).isoformat(), "acreedor": "Typhoon", "monto": "5000", "estado": "pendiente"}]), actor="socio")
    guardar_deudas(db, form("deudas", [{"acreedor": "Typhoon", "saldo": "45000", "estado": "activa"}]), actor="socio")
    debts, _, obl = load_v2_inputs(db, as_of=TODAY, horizon_days=30)
    assert obl["total"] == 5000.0 and debts == {"Typhoon": 45000.0}

    pay = db.execute("SELECT payment_id FROM finance_scheduled_payments").fetchone()["payment_id"]
    debt = db.execute("SELECT debt_id FROM finance_debts").fetchone()["debt_id"]
    guardar_pagos(db, form("pagos", [{"id": str(pay), "fecha": (TODAY + timedelta(days=4)).isoformat(), "acreedor": "Typhoon", "monto": "5000", "estado": "pagado"}]), actor="socio")
    guardar_deudas(db, form("deudas", [{"id": str(debt), "acreedor": "Typhoon", "saldo": "0", "estado": "liquidada"}]), actor="socio")
    debts, _, obl = load_v2_inputs(db, as_of=TODAY, horizon_days=30)
    assert obl["total"] == 0 and debts == {}


def test_render_shows_kpis_and_escapes_text(db):
    guardar_deudas(db, form("deudas", [{"acreedor": "<b>Typhoon</b>", "saldo": "100", "estado": "activa"}]), actor="socio")
    html = render_finanzas_captura(db, csrf_token="tok")
    assert "<b>Typhoon</b>" not in html and "&lt;b&gt;Typhoon&lt;/b&gt;" in html
    assert "DEUDA ACTIVA" in html and 'name="csrf" value="tok"' in html


def test_finance_config_accepts_db_source(monkeypatch):
    monkeypatch.setenv("FINANCE_SOURCE", "db")
    monkeypatch.setenv("FINANCE_SCHEMA", "v2")
    assert FinanceConfig.from_env().validate() == []


def test_resaving_imported_rows_changes_nothing(db):
    import_from_sheet(db, debts=SHEET_DEBTS, payments=SHEET_PAYMENTS, cash=SHEET_CASH, apply=True)
    accounts = db.execute("SELECT * FROM finance_cash_balances ORDER BY account_id").fetchall()
    cash_rows = [{"id": str(a["account_id"]), "nombre": a["account_name"], "tipo": a["account_type"],
                  "saldo": str(a["balance_mxn"]), "disponible": "si" if a["available"] else ""} for a in accounts]
    assert guardar_caja(db, form("caja", cash_rows), actor="socio").updated == 0
    pays = db.execute("SELECT * FROM finance_scheduled_payments ORDER BY payment_id").fetchall()
    pay_rows = [{"id": str(p["payment_id"]), "fecha": p["due_date"].isoformat(), "concepto": p["concept"],
                 "acreedor": p["creditor"], "monto": str(p["amount_mxn"]), "estado": p["status"],
                 "cuenta": p["account_ref"] or "", "categoria": p["category"] or ""} for p in pays]
    result = guardar_pagos(db, form("pagos", pay_rows), actor="socio")
    assert result.ok and result.updated == 0
