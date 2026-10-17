"""Estacionalidad de ventas (v7.5): proyección por mes con años anteriores.

Usa las ventas totales por mes (efectivo + tarjeta + plataformas) de
finance_monthly_sales. Dos estimaciones independientes para cada mes futuro:

A. Mismo mes del año pasado × tendencia del año: cuánto vendieron los últimos meses
   completos contra los mismos meses del año anterior.
B. Índice estacional × nivel actual: cuánto pesa ese mes en años anteriores (contra
   el promedio móvil centrado de 12 meses) aplicado al nivel desestacionalizado de los
   últimos meses.

Base = promedio de las estimaciones disponibles. El rango conservador / optimista sale
del historial de aciertos del propio modelo (backtest): percentiles 20 y 80 de
venta real ÷ proyección en los meses pasados. Sin historia suficiente no se proyecta
nada (None): el sistema no inventa ventas.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from statistics import median
import re
from typing import Any

from .utils import norm, to_float

MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
MONTH_NUMBER = {name: i + 1 for i, name in enumerate(MONTHS_ES)} | {"setiembre": 9}

TREND_WINDOW = 3        # meses completos para medir la tendencia contra el año pasado
TREND_LOOKBACK = 6      # cuántos meses hacia atrás buscar pares con dato
TREND_CLAMP = (0.4, 1.6)
LEVEL_WINDOW = 3
DEFAULT_BAND = (0.85, 1.10)   # solo si no hay suficientes meses para calibrar
MIN_BACKTEST = 12
BAND_QUANTILES = (0.20, 0.80)

Key = tuple[int, int]


def month_name(month: int) -> str:
    return MONTHS_ES[month - 1]


def add_months(key: Key, k: int) -> Key:
    idx = key[0] * 12 + (key[1] - 1) + k
    return idx // 12, idx % 12 + 1


# ---------- Pestaña "Ventas" de la hoja ----------

def _cell(row: list[Any], j: int) -> Any:
    return row[j] if j < len(row) else None


def _year(value: Any) -> int | None:
    m = re.fullmatch(r"\s*(20\d\d)(?:\.0)?\s*", str(value or ""))
    return int(m.group(1)) if m else None


def parse_sales_tab(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Lee los bloques por año: [año] Efectivo | Tarjeta | Plataformas | Total del mes.

    Un mes con total 0 y sin desglose es un mes todavía sin capturar, no una venta de 0.
    """
    blocks: list[tuple[int, int, int]] = []  # (fila del encabezado, columna del año, año)
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            year = _year(value)
            if year and "efectivo" in norm(_cell(row, j + 1)) and "total" in norm(_cell(row, j + 4)):
                blocks.append((i, j, year))

    out: dict[Key, dict[str, Any]] = {}
    for header, col, year in blocks:
        for row in rows[header + 1: header + 14]:
            month = MONTH_NUMBER.get(norm(_cell(row, col)))
            if not month:
                continue
            parts = [to_float(_cell(row, col + k)) for k in (1, 2, 3)]
            total = to_float(_cell(row, col + 4))
            if total is None and any(p is not None for p in parts):
                total = sum(p or 0 for p in parts)
            if not total or total <= 0:
                continue
            out[(year, month)] = {
                "year": year, "month": month, "cash": parts[0], "card": parts[1],
                "platforms": parts[2], "total": round(float(total), 2),
            }
    return [out[k] for k in sorted(out)]


# ---------- Base de datos ----------

def load_monthly_sales(conn) -> dict[Key, float]:
    rows = conn.execute("SELECT year, month, total_mxn FROM finance_monthly_sales WHERE total_mxn > 0").fetchall()
    return {(r["year"], r["month"]): float(r["total_mxn"]) for r in rows}


def import_sales_rows(conn, rows: list[dict[str, Any]], *, apply: bool, replace: bool = False, actor: str = "importacion") -> dict[str, int]:
    """Carga el historial de la hoja. Nunca pisa meses capturados en el portal salvo con replace."""
    stats = {"nuevos": 0, "actualizados": 0, "sin_cambio": 0, "protegidos": 0}
    with conn.transaction():
        for r in rows:
            current = conn.execute(
                "SELECT sales_id, total_mxn, source FROM finance_monthly_sales WHERE year = %s AND month = %s",
                (r["year"], r["month"]),
            ).fetchone()
            if current and current["source"] == "portal" and not replace:
                stats["protegidos"] += 1
                continue
            if current and float(current["total_mxn"]) == r["total"]:
                stats["sin_cambio"] += 1
                continue
            stats["actualizados" if current else "nuevos"] += 1
            if not apply:
                continue
            row = conn.execute(
                """
                INSERT INTO finance_monthly_sales(year, month, cash_mxn, card_mxn, platforms_mxn, total_mxn, source, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, 'hoja_ventas', %s)
                ON CONFLICT (year, month) DO UPDATE SET cash_mxn = EXCLUDED.cash_mxn, card_mxn = EXCLUDED.card_mxn,
                    platforms_mxn = EXCLUDED.platforms_mxn, total_mxn = EXCLUDED.total_mxn, source = 'hoja_ventas',
                    updated_by = EXCLUDED.updated_by, updated_at = now()
                RETURNING sales_id
                """,
                (r["year"], r["month"], r["cash"], r["card"], r["platforms"], r["total"], actor),
            ).fetchone()
            conn.execute(
                "INSERT INTO finance_change_log(table_name, record_id, action, after_data, actor) VALUES ('finance_monthly_sales', %s, 'import', %s::jsonb, %s)",
                (row["sales_id"], _json(r), actor),
            )
    return stats


def _json(r: dict[str, Any]) -> str:
    import json
    return json.dumps(r, ensure_ascii=False)


# ---------- Modelo ----------

def _complete(history: dict[Key, float], as_of: date) -> dict[Key, float]:
    """Solo meses ya cerrados: el mes en curso está incompleto y no cuenta."""
    current = (as_of.year, as_of.month)
    return {k: v for k, v in history.items() if k < current and v > 0}


def yoy_trend(history: dict[Key, float], as_of: date) -> dict[str, Any] | None:
    """Últimos meses completos contra los mismos meses del año anterior."""
    hist = _complete(history, as_of)
    if not hist:
        return None
    key = max(hist)
    pairs: list[Key] = []
    for _ in range(TREND_LOOKBACK):
        if key in hist and (key[0] - 1, key[1]) in hist:
            pairs.append(key)
            if len(pairs) == TREND_WINDOW:
                break
        key = add_months(key, -1)
    if len(pairs) < 2:
        return None
    current = sum(hist[k] for k in pairs)
    previous = sum(hist[(k[0] - 1, k[1])] for k in pairs)
    raw = current / previous
    return {
        "factor": min(max(raw, TREND_CLAMP[0]), TREND_CLAMP[1]),
        "raw": raw,
        "months": [f"{month_name(m)} {y}" for y, m in sorted(pairs)],
        "current_total": round(current, 2),
        "previous_total": round(previous, 2),
    }


def seasonal_indices(history: dict[Key, float], as_of: date) -> dict[int, dict[str, Any]]:
    """Índice por mes = venta del mes / promedio móvil centrado 2×12 (mediana entre años)."""
    hist = _complete(history, as_of)
    ratios: dict[int, list[float]] = {}
    for key, value in hist.items():
        window = [add_months(key, k) for k in range(-6, 7)]
        if not all(w in hist for w in window):
            continue
        centered = (0.5 * hist[window[0]] + sum(hist[w] for w in window[1:-1]) + 0.5 * hist[window[-1]]) / 12
        ratios.setdefault(key[1], []).append(value / centered)
    out = {m: {"index": median(r), "years": len(r)} for m, r in ratios.items()}
    if len(out) == 12:
        mean = sum(x["index"] for x in out.values()) / 12
        for x in out.values():
            x["index"] /= mean
    return out


def _level(hist: dict[Key, float], indices: dict[int, dict[str, Any]]) -> float | None:
    """Venta mensual 'normal' de hoy: últimos meses quitándoles el efecto de temporada."""
    usable = [k for k in sorted(hist, reverse=True) if k[1] in indices][:LEVEL_WINDOW]
    if len(usable) < 2:
        return None
    return sum(hist[k] / indices[k[1]]["index"] for k in usable) / len(usable)


def forecast(history: dict[Key, float], as_of: date, *, months_ahead: int = 6,
             band: tuple[float, float] | None = None) -> dict[str, Any]:
    band = band or DEFAULT_BAND
    hist = _complete(history, as_of)
    trend = yoy_trend(history, as_of)
    indices = seasonal_indices(history, as_of)
    level = _level(hist, indices) if indices else None
    last = max(hist) if hist else None
    current = (as_of.year, as_of.month)
    missing = []
    if last:
        k = add_months(last, 1)
        while k < current:
            missing.append(f"{month_name(k[1])} {k[0]}")
            k = add_months(k, 1)

    months = []
    for i in range(months_ahead):
        y, m = add_months(current, i)
        last_year = hist.get((y - 1, m))
        estimates: dict[str, float] = {}
        if last_year and trend:
            estimates["mismo_mes_x_tendencia"] = last_year * trend["factor"]
        if level and m in indices:
            estimates["indice_estacional"] = level * indices[m]["index"]
        row: dict[str, Any] = {
            "year": y, "month": m, "label": f"{month_name(m)} {y}",
            "last_year": last_year, "two_years_ago": hist.get((y - 2, m)),
            "seasonal_index": round(indices[m]["index"], 3) if m in indices else None,
            "index_years": indices[m]["years"] if m in indices else 0,
            "estimates": {k: round(v, 2) for k, v in estimates.items()},
            "low": None, "base": None, "high": None,
        }
        if estimates:
            vals = list(estimates.values())
            base = sum(vals) / len(vals)
            row.update(low=round(min(min(vals), base * band[0]), 2), base=round(base, 2),
                       high=round(max(max(vals), base * band[1]), 2))
        months.append(row)

    recent = sorted(hist)[-3:]
    return {
        "as_of": as_of.isoformat(),
        "history_months": len(hist),
        "history_from": f"{month_name(min(hist)[1])} {min(hist)[0]}" if hist else None,
        "last_month_with_data": f"{month_name(last[1])} {last[0]}" if last else None,
        "missing_months": missing,
        "trend": trend,
        "level": round(level, 2) if level else None,
        "recent_avg": round(sum(hist[k] for k in recent) / len(recent), 2) if recent else None,
        "months": months,
        "method": "promedio de (mismo mes año pasado × tendencia) e (índice estacional × nivel actual)",
        "band": [round(band[0], 3), round(band[1], 3)],
    }


def sales_in_window(fc: dict[str, Any], start: date, days: int, scenario: str = "low") -> float | None:
    """Ventas esperadas entre start y start+days-1, prorrateando cada mes por días."""
    by_month = {(r["year"], r["month"]): r.get(scenario) for r in fc.get("months", [])}
    total = 0.0
    for d in range(days):
        day = start + timedelta(days=d)
        value = by_month.get((day.year, day.month))
        if value is None:
            return None
        total += value / monthrange(day.year, day.month)[1]
    return round(total, 2)


def snapshot_kpis(fc: dict[str, Any], *, as_of: date, horizon_days: int, cash: float | None, obligations: float) -> dict[str, Any]:
    low = sales_in_window(fc, as_of, horizon_days, "low")
    base = sales_in_window(fc, as_of, horizon_days, "base")
    trend = fc.get("trend") or {}
    return {
        "expected_sales_horizon_low": low,
        "expected_sales_horizon_base": base,
        "projected_cash_gap_with_sales": round(cash + low - obligations, 2) if cash is not None and low is not None else None,
        "sales_change_vs_last_year": (trend["raw"] - 1) if trend else None,
        "sales_history_last_month": fc.get("last_month_with_data"),
        "sales_history_missing_months": len(fc.get("missing_months") or []),
    }


def backtest(history: dict[Key, float], *, min_history: int = 12) -> dict[str, Any]:
    """Proyecta cada mes pasado solo con lo que se sabía antes de que empezara y lo compara.

    Simula también el hueco habitual de captura: el mes anterior todavía no está registrado.
    """
    rows = []
    for key in sorted(history):
        known = {k: v for k, v in history.items() if k < add_months(key, -1)}
        if len(known) < min_history:
            continue
        fc = forecast(known, date(key[0], key[1], 1), months_ahead=1)
        row = fc["months"][0]
        if row["base"] is None:
            continue
        actual = history[key]
        recent = sorted(known)[-3:]
        naive = sum(known[k] for k in recent) / len(recent)
        rows.append({
            "label": row["label"], "actual": actual, "low": row["low"], "base": row["base"], "high": row["high"],
            "error_pct": round((row["base"] - actual) / actual, 4),
            "within_range": row["low"] <= actual <= row["high"],
            "above_low": actual >= row["low"],
            "ratio": actual / row["base"],
            "naive": round(naive, 2),
            "naive_error_pct": round((naive - actual) / actual, 4),
        })
    n = len(rows)
    peak = [r for r in rows if r["label"].split()[0] in ("noviembre", "diciembre")]
    mape = lambda xs, key: round(sum(abs(r[key]) for r in xs) / len(xs), 4) if xs else None
    return {
        "naive_mape": mape(rows, "naive_error_pct"),
        "peak_mape": mape(peak, "error_pct"),
        "peak_naive_mape": mape(peak, "naive_error_pct"),
        "months": rows,
        "n": n,
        "mape": round(sum(abs(r["error_pct"]) for r in rows) / n, 4) if n else None,
        "within_range_pct": round(sum(r["within_range"] for r in rows) / n, 4) if n else None,
        "above_low_pct": round(sum(r["above_low"] for r in rows) / n, 4) if n else None,
    }


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def calibrated_forecast(history: dict[Key, float], as_of: date, *, months_ahead: int = 7) -> dict[str, Any]:
    """Proyección con el rango calibrado por el backtest (solo meses anteriores a as_of)."""
    past = {k: v for k, v in history.items() if k < (as_of.year, as_of.month)}
    bt = backtest(past)
    band = None
    if bt["n"] >= MIN_BACKTEST:
        ratios = [r["ratio"] for r in bt["months"]]
        band = (min(_quantile(ratios, BAND_QUANTILES[0]), 0.9), max(_quantile(ratios, BAND_QUANTILES[1]), 1.1))
    fc = forecast(history, as_of, months_ahead=months_ahead, band=band)
    fc["band_calibrated"] = band is not None
    summary = {k: bt[k] for k in ("n", "mape", "naive_mape", "peak_mape", "peak_naive_mape")}
    if band:
        # Dentro de muestra: cuántas veces la venta real quedó arriba del escenario conservador.
        summary["above_low_pct"] = round(sum(r["ratio"] >= band[0] for r in bt["months"]) / bt["n"], 4)
    fc["backtest"] = summary | {
        "months": [{k: r[k] for k in ("label", "actual", "base", "naive", "error_pct", "naive_error_pct")} for r in bt["months"]]
    }
    return fc
