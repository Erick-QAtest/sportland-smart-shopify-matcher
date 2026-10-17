from datetime import date
import json
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from smart_finance.metrics import compute_health_score
from smart_finance.seasonality import (
    add_months,
    backtest,
    calibrated_forecast,
    forecast,
    import_sales_rows,
    load_monthly_sales,
    parse_sales_tab,
    sales_in_window,
    snapshot_kpis,
    yoy_trend,
)
from smart_portal.decision_center_v61 import build_recommendations
from smart_portal.finanzas_captura_v73 import guardar_ventas, render_finanzas_captura
from smart_portal.finanzas_proyeccion_v63 import render_finanzas_proyeccion, serie_diaria

AS_OF = date(2026, 10, 16)
# Peso de cada mes: noviembre y diciembre venden más del doble.
SEASON = {1: 0.7, 2: 0.7, 3: 0.7, 4: 0.6, 5: 0.7, 6: 0.8, 7: 0.8, 8: 1.0, 9: 1.0, 10: 0.9, 11: 2.2, 12: 2.0}


def synthetic(start=(2023, 6), end=(2026, 8), level=100000.0, yearly=0.8):
    """Ventas = nivel × peso del mes; el nivel cae 20% por año."""
    hist, key = {}, start
    while key <= end:
        years = (key[0] - start[0]) + (key[1] - start[1]) / 12
        hist[key] = round(level * yearly ** years * SEASON[key[1]], 2)
        key = add_months(key, 1)
    return hist


# ---------- Pestaña Ventas ----------

def test_parses_side_by_side_year_blocks_like_the_sheet():
    rows = [
        [],
        ["", "2025", "Efectivo", "Tarjeta ", "Plataformas", "Total del mes", "Crecimiento", "", "2026", "Efectivo", "Tarjeta ", "Plataformas", "Total del mes"],
        ["", "Noviembre", "$60,526", "123,510", "35418", "$219,454", "", "", "Agosto", "27564", "21334", "20463", "69361"],
        ["", "Diciembre", "97579", "63822", "31022", "192423", "", "", "Septiembre", "", "", "", "0"],
        ["", "Octubre ", "", "", "", "", "", "", "Octubre", "10", "20", "30", ""],
    ]
    out = {(r["year"], r["month"]): r for r in parse_sales_tab(rows)}
    assert out[(2025, 11)]["total"] == 219454 and out[(2025, 11)]["cash"] == 60526
    assert out[(2026, 8)]["total"] == 69361
    # Total 0 sin desglose = mes sin capturar (no una venta de cero); sin total se suma el desglose.
    assert (2026, 9) not in out and (2025, 10) not in out
    assert out[(2026, 10)]["total"] == 60


# ---------- Modelo ----------

def test_projects_november_with_seasonality_and_this_years_trend():
    hist = synthetic()
    fc = forecast(hist, AS_OF)
    nov = next(m for m in fc["months"] if m["month"] == 11)
    truth = 100000 * 0.8 ** ((2026 - 2023) + (11 - 6) / 12) * 2.2
    assert abs(nov["base"] - truth) / truth < 0.05
    assert nov["low"] < nov["base"] < nov["high"]
    # Mucho más que el ritmo reciente: el método plano lo subestimaba a menos de la mitad.
    assert nov["base"] > 2 * fc["recent_avg"]
    assert fc["trend"]["raw"] == pytest.approx(0.8, abs=0.01)
    assert fc["missing_months"] == ["septiembre 2026"]


def test_current_and_future_months_never_feed_the_model():
    hist = synthetic()
    with_partial = {**hist, (2026, 10): 1.0, (2026, 12): 9_999_999.0}
    assert forecast(with_partial, AS_OF)["months"] == forecast(hist, AS_OF)["months"]


def test_without_enough_history_it_does_not_invent_sales():
    hist = {(2026, 6): 50000.0, (2026, 7): 60000.0, (2026, 8): 55000.0}
    fc = forecast(hist, AS_OF)
    assert all(m["base"] is None for m in fc["months"])
    assert fc["trend"] is None and yoy_trend(hist, AS_OF) is None
    assert sales_in_window(fc, AS_OF, 30) is None


def test_window_prorates_each_month_by_days():
    fc = {"months": [{"year": 2026, "month": 10, "low": 31000.0}, {"year": 2026, "month": 11, "low": 30000.0}]}
    # 16 días de octubre (1000/día) + 14 de noviembre (1000/día)
    assert sales_in_window(fc, AS_OF, 30) == pytest.approx(30000.0)


def test_backtest_only_uses_data_known_before_each_month():
    hist = synthetic()
    bt = backtest(hist)
    changed = dict(hist)
    changed[(2026, 8)] *= 10  # cambiar el último mes no puede alterar proyecciones anteriores
    bt2 = backtest(changed)
    assert [r["base"] for r in bt["months"][:-1]] == [r["base"] for r in bt2["months"][:-1]]
    assert bt["mape"] < bt["naive_mape"]


def test_band_is_calibrated_from_past_errors():
    fc = calibrated_forecast(synthetic(), AS_OF)
    assert fc["band_calibrated"] and fc["backtest"]["n"] >= 12
    low, high = fc["band"]
    assert low <= 0.9 and high >= 1.1


def test_kpis_and_health_use_last_year_instead_of_previous_30_days():
    fc = calibrated_forecast(synthetic(), AS_OF)
    k = snapshot_kpis(fc, as_of=AS_OF, horizon_days=30, cash=10000.0, obligations=40000.0)
    assert k["expected_sales_horizon_low"] > 0
    assert k["projected_cash_gap_with_sales"] == pytest.approx(10000 + k["expected_sales_horizon_low"] - 40000, abs=0.01)
    # 30d vs 30d previos diría +100% en noviembre; contra el año pasado es -20%.
    health = compute_health_score({"kpis": {"sales_change_vs_previous_30d": 1.0, **k}})
    assert health["components"]["sales_trend"]["basis"] == "same_months_last_year"
    assert health["components"]["sales_trend"]["score"] == pytest.approx(30, abs=1)
    fallback = compute_health_score({"kpis": {"sales_change_vs_previous_30d": 0.1}})
    assert fallback["components"]["sales_trend"]["basis"] == "previous_30d"


def test_decision_center_warns_about_the_coming_peak():
    fc = calibrated_forecast(synthetic(), AS_OF)
    recs = build_recommendations({"finance": {"financial_health": {"score": 70}, "kpis": {}, "seasonal_forecast": fc}})
    season = next(r for r in recs if r.key == "finance-season-peak")
    assert "noviembre 2026" in season.title
    assert season.confidence == "MEDIUM"  # falta septiembre
    assert any("septiembre 2026" in e for e in season.evidence)
    flat = {(y, m): 50000.0 for y in (2024, 2025, 2026) for m in range(1, 13) if (y, m) < (2026, 9)}
    recs = build_recommendations({"finance": {"financial_health": {"score": 70}, "kpis": {}, "seasonal_forecast": calibrated_forecast(flat, AS_OF)}})
    assert not any(r.key == "finance-season-peak" for r in recs)


def test_projection_page_uses_the_seasonal_curve(tmp_path):
    fc = calibrated_forecast(synthetic(), date.today())
    snapshot = {"kpis": {"sales_30d": 30000, "sales_change_vs_last_year": -0.2}, "seasonal_forecast": fc}
    serie, dias = serie_diaria(snapshot, 30000, date.today())
    assert dias == len(serie) == 180
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "financial_snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    html = render_finanzas_proyeccion(tmp_path)
    assert 'id="temporada"' in html and "Precisión probada" in html and "-20%" in html
    empty = tmp_path / "vacio"
    (empty / "artifacts").mkdir(parents=True)
    (empty / "artifacts" / "financial_snapshot.json").write_text(json.dumps({"kpis": {"sales_30d": 30000}}), encoding="utf-8")
    assert "Todavía no hay historial de ventas por mes" in render_finanzas_proyeccion(empty)


# ---------- Base de datos ----------

DB_URL = os.getenv("SPORTLAND_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="Define SPORTLAND_TEST_DATABASE_URL para las pruebas con base de datos.")


@pytest.fixture
def db():
    conn = psycopg.connect(DB_URL, row_factory=dict_row)
    with conn.transaction() as tx:
        yield conn
        raise psycopg.Rollback(tx)
    conn.close()


def sheet_rows(hist):
    return [{"year": y, "month": m, "cash": None, "card": None, "platforms": None, "total": v} for (y, m), v in sorted(hist.items())]


def form(rows):
    data = {"ventas_n": [str(len(rows))]}
    for i, row in enumerate(rows):
        for name, value in row.items():
            data[f"ventas_{name}_{i}"] = [value]
    return data


def last_closed_month(today=None):
    today = today or date.today()
    return add_months((today.year, today.month), -1)


@needs_db
def test_import_is_dry_run_by_default_and_never_overwrites_portal_months(db):
    hist = {(2025, 11): 219454.0, (2025, 12): 192423.0}
    assert import_sales_rows(db, sheet_rows(hist), apply=False)["nuevos"] == 2
    assert load_monthly_sales(db) == {}
    import_sales_rows(db, sheet_rows(hist), apply=True)
    assert load_monthly_sales(db) == hist
    db.execute("UPDATE finance_monthly_sales SET total_mxn = 1, source = 'portal' WHERE month = 12")
    stats = import_sales_rows(db, sheet_rows(hist), apply=True)
    assert stats["protegidos"] == 1 and stats["sin_cambio"] == 1
    assert load_monthly_sales(db)[(2025, 12)] == 1.0


@needs_db
def test_capture_sums_the_parts_and_rejects_a_wrong_total(db):
    y, m = last_closed_month()
    ok = guardar_ventas(db, form([{"mes": f"{y}-{m:02d}", "efectivo": "27,564", "tarjeta": "21334", "plataformas": "20463", "total": ""}]), actor="socio")
    assert ok.ok and ok.inserted == 1
    assert load_monthly_sales(db)[(y, m)] == 69361.0
    bad = guardar_ventas(db, form([{"mes": f"{y}-{m:02d}", "efectivo": "1", "tarjeta": "1", "plataformas": "1", "total": "10"}]), actor="socio")
    assert not bad.ok and load_monthly_sales(db)[(y, m)] == 69361.0
    future = guardar_ventas(db, form([{"mes": f"{date.today().year}-{date.today().month:02d}", "total": "5000"}]), actor="socio")
    assert not future.ok  # el mes en curso no se captura: está incompleto


@needs_db
def test_resaving_imported_months_keeps_their_origin(db):
    y, m = last_closed_month()
    import_sales_rows(db, sheet_rows({(y, m): 82117.0}), apply=True)
    row = db.execute("SELECT sales_id FROM finance_monthly_sales").fetchone()
    same = {"id": str(row["sales_id"]), "mes": f"{y}-{m:02d}", "efectivo": "", "tarjeta": "", "plataformas": "", "total": "82117.00"}
    assert guardar_ventas(db, form([same]), actor="socio").updated == 0
    assert db.execute("SELECT source FROM finance_monthly_sales").fetchone()["source"] == "hoja_ventas"
    assert guardar_ventas(db, form([dict(same, total="90000")]), actor="socio").updated == 1
    assert db.execute("SELECT source FROM finance_monthly_sales").fetchone()["source"] == "portal"
    html = render_finanzas_captura(db, csrf_token="tok")
    assert "Ventas por mes" in html and "Faltan las ventas de" in html
