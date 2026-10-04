from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any

from .utils import MONTHS_ES, month_year_from_text, norm, rows_pad, to_float

MONTH_LABELS = {v: k for k, v in MONTHS_ES.items() if k != "setiembre"}


def parse_sales(rows: list[list[Any]], target_year: int | None = None) -> dict[str, Any]:
    """Parse the legacy 'Ventas ' matrix.

    Finds the year block dynamically and returns all positive monthly totals.
    Zero-filled future months are ignored rather than treated as real sales.
    """
    target_year = target_year or date.today().year
    rows = rows_pad(rows)
    year_cell = None
    for r_idx, row in enumerate(rows[:10]):
        for c_idx, value in enumerate(row):
            if norm(value) == str(target_year):
                year_cell = (r_idx, c_idx)
                break
        if year_cell:
            break
    if not year_cell:
        return {"year": target_year, "months": [], "latest": None, "previous": None}

    r0, c0 = year_cell
    # Expected local layout: Year | Efectivo | Tarjeta | Plataformas | Total del mes
    months: list[dict[str, Any]] = []
    for row in rows[r0 + 1 : r0 + 14]:
        month_name = norm(row[c0]) if c0 < len(row) else ""
        month_num = MONTHS_ES.get(month_name)
        if not month_num:
            continue
        total = to_float(row[c0 + 4] if c0 + 4 < len(row) else None)
        efectivo = to_float(row[c0 + 1] if c0 + 1 < len(row) else None) or 0.0
        tarjeta = to_float(row[c0 + 2] if c0 + 2 < len(row) else None) or 0.0
        plataformas = to_float(row[c0 + 3] if c0 + 3 < len(row) else None) or 0.0
        rotacion = to_float(row[c0 + 6] if c0 + 6 < len(row) else None)
        if total is None or total <= 0:
            continue
        months.append({
            "year": target_year,
            "month": month_num,
            "month_name": month_name,
            "period": f"{target_year:04d}-{month_num:02d}",
            "sales_total": total,
            "cash_sales": efectivo,
            "card_sales": tarjeta,
            "platform_sales": plataformas,
            "inventory_rotation_raw": rotacion,
        })
    months.sort(key=lambda x: x["month"])
    latest = months[-1] if months else None
    previous = months[-2] if len(months) >= 2 else None
    return {"year": target_year, "months": months, "latest": latest, "previous": previous}


def _find_month_section(rows: list[list[Any]], year: int, month: int) -> tuple[int, int] | None:
    rows = rows_pad(rows)
    for r_idx, row in enumerate(rows):
        for c_idx, value in enumerate(row):
            ym = month_year_from_text(value)
            if ym == (year, month):
                return r_idx, c_idx
    return None


def parse_monthly_obligations(rows: list[list[Any]], year: int, month: int) -> dict[str, Any]:
    """Parse one month from 'Proyeccion de pagos'.

    Legacy month blocks have two amount/creditor lanes:
      DIA | MONTO | ACREEDOR | CUENTA | <gap> | MONTO | ACREEDOR | CUENTA
    Only these two MONTO lanes are counted; planning notes to the right are ignored.
    """
    rows = rows_pad(rows)
    pos = _find_month_section(rows, year, month)
    if not pos:
        return {"period": f"{year:04d}-{month:02d}", "payments": [], "total": 0.0}
    title_r, start_c = pos
    header_r = title_r + 1
    # Guard against odd blank rows by searching next 3 rows for DIA/MONTO.
    for rr in range(title_r + 1, min(title_r + 4, len(rows))):
        if norm(rows[rr][start_c]) == "dia" or norm(rows[rr][start_c + 1]) == "monto":
            header_r = rr
            break

    payments: list[dict[str, Any]] = []
    # stop when another explicit month/year title appears beneath this block
    for r_idx in range(header_r + 1, len(rows)):
        row = rows[r_idx]
        if r_idx > header_r + 1:
            below_titles = [month_year_from_text(v) for v in row]
            if any(t and t != (year, month) for t in below_titles):
                break
        # total rows typically have no day. Do not double-count them.
        day = to_float(row[start_c] if start_c < len(row) else None)
        if day is None or not (1 <= day <= 31):
            continue
        for amount_off, creditor_off, account_off in ((1, 2, 3), (5, 6, 7)):
            amount = to_float(row[start_c + amount_off] if start_c + amount_off < len(row) else None)
            if amount is None or amount <= 0:
                continue
            creditor = str(row[start_c + creditor_off]).strip() if start_c + creditor_off < len(row) else ""
            account = str(row[start_c + account_off]).strip() if start_c + account_off < len(row) else ""
            payments.append({
                "day": int(day),
                "amount": amount,
                "creditor": creditor,
                "account": account,
            })
    return {
        "period": f"{year:04d}-{month:02d}",
        "payments": payments,
        "total": round(sum(x["amount"] for x in payments), 2),
    }


def parse_cash_position(rows: list[list[Any]], year: int, month: int) -> dict[str, Any]:
    """Get latest cash/account state from the legacy Flujo de caja.

    The workbook has month-only titles, repeated year cycles, and prefilled future rows.
    First tries explicit month/year; then infers year by Jan rollovers starting in 2025.
    """
    rows = rows_pad(rows)
    pos = _find_month_section(rows, year, month)
    if not pos:
        inferred_year = 2025
        last_month = None
        for r_idx, row in enumerate(rows):
            found_month = None
            found_col = None
            for c_idx in range(min(5, len(row))):
                candidate = MONTHS_ES.get(norm(row[c_idx]))
                if candidate:
                    found_month = candidate
                    found_col = c_idx
                    break
            if found_month is None:
                continue
            if last_month is not None and found_month < last_month:
                inferred_year += 1
            last_month = found_month
            if inferred_year == year and found_month == month:
                pos = (r_idx, found_col)
                break
    if not pos:
        return {"period": f"{year:04d}-{month:02d}", "cash": None, "accounts": None, "total": None}

    title_r, start_c = pos
    header_r = state_cash_c = state_accounts_c = None
    for rr in range(title_r + 1, min(title_r + 5, len(rows))):
        for cc in range(start_c, min(start_c + 20, len(rows[rr]))):
            if norm(rows[rr][cc]) == "estado efectivo":
                header_r, state_cash_c = rr, cc
            if norm(rows[rr][cc]) == "estado cuentas":
                state_accounts_c = cc
        if header_r is not None and state_accounts_c is not None:
            break
    if header_r is None or state_cash_c is None or state_accounts_c is None:
        return {"period": f"{year:04d}-{month:02d}", "cash": None, "accounts": None, "total": None}

    today = date.today()
    max_day = today.day if (year, month) == (today.year, today.month) else 31
    day_col = max(0, start_c - 1)
    latest = None
    for r_idx in range(header_r + 1, len(rows)):
        row = rows[r_idx]
        if r_idx > header_r + 1 and any(MONTHS_ES.get(norm(row[cc])) for cc in range(min(5, len(row)))):
            break
        day = to_float(row[day_col] if day_col < len(row) else None)
        if day is None or not (1 <= day <= max_day):
            continue
        cash = to_float(row[state_cash_c] if state_cash_c < len(row) else None)
        accounts = to_float(row[state_accounts_c] if state_accounts_c < len(row) else None)
        if cash is not None or accounts is not None:
            latest = {
                "cash": cash or 0.0,
                "accounts": accounts or 0.0,
                "total": (cash or 0.0) + (accounts or 0.0),
                "source_row": r_idx + 1,
            }
    if latest is None:
        return {"period": f"{year:04d}-{month:02d}", "cash": None, "accounts": None, "total": None}
    latest["period"] = f"{year:04d}-{month:02d}"
    return latest

def parse_provider_balances(rows: list[list[Any]]) -> dict[str, float]:
    """Extract latest positive balances from creditor blocks in 'Proveedores'.

    Supports the historical Adeudo blocks plus the Prestamos running Total block.
    Negative/near-zero closed balances are normalized to zero.
    """
    rows = rows_pad(rows)
    if not rows:
        return {}
    width = len(rows[0])
    label_row = rows[1] if len(rows) > 1 else rows[0]
    # In the actual workbook labels are typically on the first data row after index;
    # search the first 5 rows for known block names and map each label to its column.
    known_labels: dict[int, str] = {}
    for rr in range(min(5, len(rows))):
        for cc, value in enumerate(rows[rr]):
            v = norm(value)
            if v and v not in {"fecha", "tipo", "monto", "adeudo", "al dia", "total"}:
                if any(k in v for k in ("typhoon", "palermo", "fojal", "prestamos", "tenis gdl", "raga")):
                    known_labels[cc] = str(value).strip()
    # Locate header columns and assign to nearest label on the left.
    balances: dict[str, float] = {}
    header_rows = range(min(8, len(rows)))
    for hr in header_rows:
        for cc in range(width):
            h = norm(rows[hr][cc])
            if h not in {"adeudo", "total"}:
                continue
            # Nearest known block label at or before the header column.
            label_candidates = [(lc, name) for lc, name in known_labels.items() if lc <= cc]
            if not label_candidates:
                continue
            lc, name = max(label_candidates, key=lambda x: x[0])
            # Avoid unrelated Total columns unless this is Prestamos.
            if h == "total" and "prestamos" not in norm(name):
                continue
            last = None
            for row in rows[hr + 1 :]:
                n = to_float(row[cc] if cc < len(row) else None)
                if n is not None:
                    last = n
            if last is not None:
                balances[name] = round(max(0.0, last), 2)
    return balances


def parse_inventory_cost_map(rows: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Find the cleanest SKU/COSTO/PRECIO block in legacy Inventario.

    The workbook contains more than one SKU area. Every candidate SKU column is scored
    by how many rows have a SKU plus numeric cost. Highest-scoring block wins.
    """
    rows = rows_pad(rows)
    candidates: list[tuple[int, int, int, int]] = []  # score, row, sku_col, cost_col
    for r_idx, row in enumerate(rows[:8]):
        for c_idx, value in enumerate(row):
            if norm(value) != "sku":
                continue
            nearby = {norm(row[j]): j for j in range(c_idx, min(c_idx + 5, len(row)))}
            cost_col = nearby.get("costo")
            price_col = nearby.get("precio")
            if cost_col is None:
                # common pattern: SKU, COSTO, PRECIO
                if c_idx + 1 < len(row) and norm(row[c_idx + 1]) == "costo":
                    cost_col = c_idx + 1
            if price_col is None and cost_col is not None and cost_col + 1 < len(row) and norm(row[cost_col + 1]) == "precio":
                price_col = cost_col + 1
            if cost_col is None:
                continue
            score = 0
            for rr in rows[r_idx + 1 : r_idx + 600]:
                sku = str(rr[c_idx]).strip() if c_idx < len(rr) else ""
                cost = to_float(rr[cost_col] if cost_col < len(rr) else None)
                if sku and cost is not None and cost >= 0:
                    score += 1
            candidates.append((score, r_idx, c_idx, cost_col if cost_col is not None else -1))
    if not candidates:
        return {}
    _, header_r, sku_col, cost_col = max(candidates, key=lambda x: x[0])
    # price is normally immediately to the right of cost in selected block.
    price_col = cost_col + 1
    out: dict[str, dict[str, float]] = {}
    for row in rows[header_r + 1 :]:
        sku = str(row[sku_col]).strip() if sku_col < len(row) else ""
        cost = to_float(row[cost_col] if cost_col < len(row) else None)
        price = to_float(row[price_col] if price_col < len(row) else None)
        if not sku or cost is None:
            continue
        out[sku] = {"cost": cost, "legacy_price": price if price is not None else 0.0}
    return out


def classify_payments(payments: list[dict[str, Any]]) -> dict[str, float]:
    groups = defaultdict(float)
    for p in payments:
        name = norm(p.get("creditor"))
        amount = float(p.get("amount", 0) or 0)
        if any(k in name for k in ("interes", "credito", "prestamo", "fojal")):
            groups["finance"] += amount
        elif any(k in name for k in ("ragga", "raga", "palermo", "deportiva", "typhoon", "tenis", "converse", "reebok", "nike")):
            groups["inventory"] += amount
        elif any(k in name for k in ("nomina", "guille", "imss", "contador", "marketing", "operacion", "santiago", "evelyn", "noe")):
            groups["operating"] += amount
        else:
            groups["other"] += amount
    groups["total"] = sum(groups.values())
    return {k: round(v, 2) for k, v in groups.items()}
