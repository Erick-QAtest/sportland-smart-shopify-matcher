"""Finanzas v2 desde PostgreSQL (FINANCE_SOURCE=db).

Las tablas de 016_finance_capture.sql se convierten al mismo formato de filas que las
pestañas Deudas / Próximos pagos / Caja externa y se procesan con los parsers v2 de
siempre: los cálculos del motor no cambian al pasar de la hoja a la base.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from typing import Any

import psycopg

from .utils import norm, to_float
from .v2_parsers import _header_map, _parse_date, parse_v2_cash, parse_v2_debts, parse_v2_obligations

DEBT_HEADERS = ["Acreedor", "Saldo actual (MXN)", "Estado"]
PAYMENT_HEADERS = ["Fecha", "Concepto", "Acreedor", "Monto (MXN)", "Estado", "Cuenta / referencia", "Categoria"]
CASH_HEADERS = ["Fecha corte", "Tipo", "Saldo actual (MXN)", "Disponible"]

PAYMENT_STATUSES = {"pendiente", "por confirmar", "pagado", "cancelado"}


def _num(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def debt_rows(conn) -> list[list[Any]]:
    rows = conn.execute(
        "SELECT creditor, balance_mxn, status FROM finance_debts ORDER BY lower(creditor), debt_id"
    ).fetchall()
    return [DEBT_HEADERS] + [[r["creditor"], _num(r["balance_mxn"]), r["status"].capitalize()] for r in rows]


def payment_rows(conn) -> list[list[Any]]:
    rows = conn.execute(
        """
        SELECT due_date, concept, creditor, amount_mxn, status, account_ref, category
        FROM finance_scheduled_payments ORDER BY due_date, payment_id
        """
    ).fetchall()
    return [PAYMENT_HEADERS] + [
        [r["due_date"], r["concept"], r["creditor"], _num(r["amount_mxn"]), r["status"].capitalize(),
         r["account_ref"] or "", r["category"] or ""]
        for r in rows
    ]


def cash_rows(conn) -> list[list[Any]]:
    rows = conn.execute(
        "SELECT cut_date, account_type, balance_mxn, available FROM finance_cash_balances ORDER BY account_id"
    ).fetchall()
    return [CASH_HEADERS] + [
        [r["cut_date"], r["account_type"], _num(r["balance_mxn"]), "Sí" if r["available"] else "No"] for r in rows
    ]


def load_v2_inputs(conn, *, as_of: date, horizon_days: int) -> tuple[dict[str, float], dict[str, Any], dict[str, Any]]:
    """Devuelve (provider_balances, cash, obligations) igual que si se leyera la hoja."""
    return (
        parse_v2_debts(debt_rows(conn)),
        parse_v2_cash(cash_rows(conn)),
        parse_v2_obligations(payment_rows(conn), as_of=as_of, horizon_days=horizon_days),
    )


# ---------- Importación única desde la hoja ----------

def _cell(row: list[Any], cols: dict[str, int], *names: str) -> Any:
    for name in names:
        index = cols.get(norm(name))
        if index is not None and index < len(row) and str(row[index]).strip() != "":
            return row[index]
    return None


def _source_row(headers: list[Any], row: list[Any]) -> str:
    return json.dumps(
        {str(h).strip(): (str(row[i]) if i < len(row) else "") for i, h in enumerate(headers) if str(h).strip()},
        ensure_ascii=False,
    )


def _payment_status(raw: Any) -> str:
    value = norm(raw)
    if value in {"pagado", "pagada", "paid"}:
        return "pagado"
    if value in {"cancelado", "cancelada", "cancelled"}:
        return "cancelado"
    if value == "por confirmar":
        return "por confirmar"
    return "pendiente"


def _log(conn, table: str, record_id: int, actor: str) -> None:
    conn.execute(
        "INSERT INTO finance_change_log(table_name, record_id, action, actor) VALUES (%s, %s, 'import', %s)",
        (table, record_id, actor),
    )


def import_from_sheet(
    conn,
    *,
    debts: list[list[Any]],
    payments: list[list[Any]],
    cash: list[list[Any]],
    apply: bool,
    replace: bool = False,
    actor: str = "importacion_hoja",
) -> dict[str, Any]:
    """Copia las tres pestañas a la base. Sin `apply` es una simulación exacta (se revierte)."""
    stats: dict[str, Any] = {"debts": 0, "payments": 0, "cash": 0, "skipped": [], "applied": apply}
    tables = ("finance_debts", "finance_scheduled_payments", "finance_cash_balances")
    with conn.transaction() as tx:
        existing = sum(conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in tables)
        if existing and not replace:
            raise RuntimeError(f"Las tablas de finanzas ya tienen {existing} registros; usa --reemplazar para sustituirlos.")
        if existing:
            for table in tables:
                conn.execute(f"DELETE FROM {table}")

        found = _header_map(debts, tuple(DEBT_HEADERS))
        if found:
            header_r, cols = found
            for row in debts[header_r + 1:]:
                name = str(_cell(row, cols, "Acreedor") or "").strip()
                if not name or norm(name).startswith("total"):
                    continue
                balance = to_float(_cell(row, cols, "Saldo actual (MXN)")) or 0.0
                status = "activa" if norm(_cell(row, cols, "Estado")) in {"", "activa", "activo", "active"} else "liquidada"
                rid = conn.execute(
                    """INSERT INTO finance_debts(creditor, balance_mxn, status, source_row, updated_by)
                       VALUES (%s, %s, %s, %s::jsonb, %s) RETURNING debt_id""",
                    (name, max(balance, 0.0), status, _source_row(debts[header_r], row), actor),
                ).fetchone()["debt_id"]
                _log(conn, "finance_debts", rid, actor)
                stats["debts"] += 1
        else:
            stats["skipped"].append("Deudas: no se encontraron los encabezados esperados")

        found = _header_map(payments, ("Fecha", "Concepto", "Acreedor", "Monto (MXN)", "Estado"))
        if found:
            header_r, cols = found
            for row in payments[header_r + 1:]:
                due = _parse_date(_cell(row, cols, "Fecha"))
                amount = to_float(_cell(row, cols, "Monto (MXN)"))
                creditor = str(_cell(row, cols, "Acreedor") or "").strip()
                # Mismo criterio que parse_v2_obligations: el acreedor puede venir vacío.
                if due is None or amount is None or amount <= 0:
                    continue
                rid = conn.execute(
                    """INSERT INTO finance_scheduled_payments(
                           due_date, concept, creditor, amount_mxn, status, account_ref, category, source_row, updated_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING payment_id""",
                    (due, str(_cell(row, cols, "Concepto") or "").strip(), creditor, amount,
                     _payment_status(_cell(row, cols, "Estado")),
                     str(_cell(row, cols, "Cuenta / referencia") or "").strip() or None,
                     str(_cell(row, cols, "Categoria") or "").strip() or None,
                     _source_row(payments[header_r], row), actor),
                ).fetchone()["payment_id"]
                _log(conn, "finance_scheduled_payments", rid, actor)
                stats["payments"] += 1
        else:
            stats["skipped"].append("Próximos pagos: no se encontraron los encabezados esperados")

        found = _header_map(cash, tuple(CASH_HEADERS))
        if found:
            header_r, cols = found
            for row in cash[header_r + 1:]:
                balance = to_float(_cell(row, cols, "Saldo actual (MXN)"))
                if balance is None:
                    continue
                kind = str(_cell(row, cols, "Tipo") or "Cuenta").strip()
                name = str(_cell(row, cols, "Cuenta", "Nombre", "Concepto", "Banco", "Tipo") or kind).strip()
                available = norm(_cell(row, cols, "Disponible")) in {"si", "yes", "true", "1"}
                cut = _parse_date(_cell(row, cols, "Fecha corte")) or date.today()
                rid = conn.execute(
                    """INSERT INTO finance_cash_balances(
                           account_name, account_type, balance_mxn, available, cut_date, source_row, updated_by)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING account_id""",
                    (name, kind, balance, available, cut, _source_row(cash[header_r], row), actor),
                ).fetchone()["account_id"]
                _log(conn, "finance_cash_balances", rid, actor)
                stats["cash"] += 1
        else:
            stats["skipped"].append("Caja externa: no se encontraron los encabezados esperados")

        if not apply:
            raise psycopg.Rollback(tx)
    return stats
