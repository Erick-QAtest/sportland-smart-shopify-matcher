from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .utils import norm, rows_pad, to_float

_GOOGLE_SERIAL_BASE = date(1899, 12, 30)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return _GOOGLE_SERIAL_BASE + timedelta(days=int(value))
        except (OverflowError, ValueError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def _header_map(rows: list[list[Any]], required: tuple[str, ...]) -> tuple[int, dict[str, int]] | None:
    rows = rows_pad(rows)
    req = {norm(x) for x in required}
    for r_idx, row in enumerate(rows[:15]):
        mapping = {norm(v): c for c, v in enumerate(row) if norm(v)}
        if req.issubset(mapping):
            return r_idx, mapping
    return None


def parse_v2_debts(rows: list[list[Any]]) -> dict[str, float]:
    """Read authoritative active balances from Sprint 1 sheet `Deudas`."""
    rows = rows_pad(rows)
    found = _header_map(rows, ("Acreedor", "Saldo actual (MXN)", "Estado"))
    if not found:
        return {}
    header_r, cols = found
    c_name = cols[norm("Acreedor")]
    c_balance = cols[norm("Saldo actual (MXN)")]
    c_status = cols[norm("Estado")]
    out: dict[str, float] = {}
    for row in rows[header_r + 1 :]:
        name = str(row[c_name]).strip() if c_name < len(row) else ""
        if not name or norm(name).startswith("total"):
            continue
        status = norm(row[c_status] if c_status < len(row) else "")
        if status and status not in {"activa", "activo", "active"}:
            continue
        balance = to_float(row[c_balance] if c_balance < len(row) else None)
        if balance is not None and balance > 0:
            out[name] = round(balance, 2)
    return out


def parse_v2_cash(rows: list[list[Any]]) -> dict[str, Any]:
    """Read only balances explicitly marked available from `Caja externa`."""
    rows = rows_pad(rows)
    found = _header_map(rows, ("Fecha corte", "Tipo", "Saldo actual (MXN)", "Disponible"))
    if not found:
        return {"period": None, "cash": None, "accounts": None, "total": None}
    header_r, cols = found
    c_date = cols[norm("Fecha corte")]
    c_type = cols[norm("Tipo")]
    c_balance = cols[norm("Saldo actual (MXN)")]
    c_available = cols[norm("Disponible")]

    cash = 0.0
    accounts = 0.0
    seen = False
    latest: date | None = None
    for row in rows[header_r + 1 :]:
        available = norm(row[c_available] if c_available < len(row) else "")
        if available not in {"si", "sí", "yes", "true", "1"}:
            continue
        balance = to_float(row[c_balance] if c_balance < len(row) else None)
        if balance is None:
            continue
        seen = True
        typ = norm(row[c_type] if c_type < len(row) else "")
        if "efectivo" in typ or "cash" in typ:
            cash += balance
        else:
            accounts += balance
        d = _parse_date(row[c_date] if c_date < len(row) else None)
        if d and (latest is None or d > latest):
            latest = d

    if not seen:
        return {"period": None, "cash": None, "accounts": None, "total": None}
    return {
        "period": latest.isoformat() if latest else None,
        "cash": round(cash, 2),
        "accounts": round(accounts, 2),
        "total": round(cash + accounts, 2),
    }


def parse_v2_obligations(
    rows: list[list[Any]],
    *,
    as_of: date | None = None,
    horizon_days: int = 30,
) -> dict[str, Any]:
    """Read pending payments due from as_of through as_of+horizon_days.

    `Por confirmar` is intentionally included when its date has not passed.
    Paid/cancelled rows are excluded. Past rows are not counted in forward liquidity.
    """
    as_of = as_of or date.today()
    rows = rows_pad(rows)
    found = _header_map(rows, ("Fecha", "Concepto", "Acreedor", "Monto (MXN)", "Estado"))
    if not found:
        return {"period": as_of.isoformat(), "payments": [], "total": 0.0}
    header_r, cols = found
    c_date = cols[norm("Fecha")]
    c_concept = cols[norm("Concepto")]
    c_creditor = cols[norm("Acreedor")]
    c_amount = cols[norm("Monto (MXN)")]
    c_status = cols[norm("Estado")]
    c_account = cols.get(norm("Cuenta / referencia"))
    c_category = cols.get(norm("Categoria"))

    end = as_of + timedelta(days=max(0, int(horizon_days)))
    payments: list[dict[str, Any]] = []
    for row in rows[header_r + 1 :]:
        due = _parse_date(row[c_date] if c_date < len(row) else None)
        if due is None or due < as_of or due > end:
            continue
        status = norm(row[c_status] if c_status < len(row) else "")
        if status in {"pagado", "pagada", "cancelado", "cancelada", "cancelled", "paid"}:
            continue
        amount = to_float(row[c_amount] if c_amount < len(row) else None)
        if amount is None or amount <= 0:
            continue
        concept = str(row[c_concept]).strip() if c_concept < len(row) else ""
        creditor = str(row[c_creditor]).strip() if c_creditor < len(row) else ""
        account = str(row[c_account]).strip() if c_account is not None and c_account < len(row) else ""
        category = str(row[c_category]).strip() if c_category is not None and c_category < len(row) else ""
        # Existing metric classifier keys off creditor text; include concept/category for robust grouping.
        classification_name = " | ".join(x for x in (concept, creditor, category) if x)
        payments.append({
            "date": due.isoformat(),
            "day": due.day,
            "amount": amount,
            "creditor": classification_name or creditor,
            "display_creditor": creditor,
            "concept": concept,
            "category": category,
            "account": account,
            "status": status,
        })
    payments.sort(key=lambda x: (x["date"], x["creditor"]))
    return {
        "period": f"{as_of.isoformat()}..{end.isoformat()}",
        "payments": payments,
        "total": round(sum(x["amount"] for x in payments), 2),
    }
