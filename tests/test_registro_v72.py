from datetime import date
import os

import psycopg
from psycopg.rows import dict_row
import pytest

from smart_portal.registro_v72 import (
    CAPTURE_SOURCE,
    RowInput,
    guardar_registro,
    normalize_phone,
    normalize_size,
    parse_rows,
    render_registro,
    validate_row,
)

TODAY = date(2026, 10, 16)
CATALOG = {"COMPRA": 7, "SALE_SIN_COMPRA": 23, "PREGUNTA_MODELO_ESPECIFICO": 21, "APARTADO": 6}


def row(index=0, **values):
    return RowInput(index=index, values={"fecha": TODAY.isoformat(), **values})


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("33 1234 5678", "+523312345678"),
        ("(33) 1234-5678", "+523312345678"),
        ("523312345678", "+523312345678"),
        ("+52 33 1234 5678", "+523312345678"),
        ("0052 33 1234 5678", "+523312345678"),
        ("+1 415 555 0100", "+14155550100"),
        ("", ""),
    ],
)
def test_normalize_phone(raw, expected):
    value, error = normalize_phone(raw)
    assert error is None
    assert value == expected


def test_normalize_phone_rejects_garbage():
    assert normalize_phone("12345")[1]
    assert normalize_phone("abc")[1]


@pytest.mark.parametrize("raw,expected", [("27", "27"), ("26,50", "26.5"), ("27.0 mx", "27"), (" m ", "M")])
def test_normalize_size_matches_sheet_contract(raw, expected):
    assert normalize_size(raw) == expected


def test_purchase_needs_phone_size_and_amount():
    result = validate_row(row(tipo="COMPRA"), CATALOG, TODAY)
    assert any("teléfono" in e for e in result.errors)
    assert any("talla" in e for e in result.errors)
    assert any("monto" in e for e in result.errors)


def test_anonymous_event_is_allowed_without_phone():
    result = validate_row(row(tipo="SALE_SIN_COMPRA"), CATALOG, TODAY)
    assert result.errors == []
    assert result.payload["phone_e164"] is None


def test_future_date_and_unknown_event_are_rejected():
    result = validate_row(row(tipo="NO_EXISTE", fecha="2026-10-17", telefono="3312345678"), CATALOG, TODAY)
    assert any("tipo de evento" in e for e in result.errors)
    assert any("futura" in e for e in result.errors)


def test_parse_rows_reads_indexed_fields_and_skips_blank_rows():
    form = {"fecha_0": [TODAY.isoformat()], "tipo_0": ["COMPRA"], "fecha_1": [TODAY.isoformat()]}
    rows = parse_rows(form, count=3)
    assert len(rows) == 3
    assert not rows[0].is_blank()
    assert rows[1].is_blank()


# ---------- Integración con PostgreSQL (opcional) ----------

DB_URL = os.getenv("SPORTLAND_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DB_URL, reason="Define SPORTLAND_TEST_DATABASE_URL para las pruebas con base de datos.")


@pytest.fixture
def db():
    conn = psycopg.connect(DB_URL, row_factory=dict_row)
    with conn.transaction() as tx:
        yield conn
        raise psycopg.Rollback(tx)
    conn.close()


def purchase(index, phone="33 1234 5678", **extra):
    return row(index=index, telefono=phone, tipo="COMPRA", sku="2033-27", talla="27", monto="1,899", canal="whatsapp", **extra)


@needs_db
def test_saving_a_batch_creates_customer_and_events(db):
    summary = guardar_registro(db, [purchase(0), row(index=1, tipo="SALE_SIN_COMPRA")], actor="socio", today=TODAY)
    assert summary["saved"] == 2
    assert summary["new_customers"] == 1
    events = db.execute(
        "SELECT e.*, c.phone_e164 FROM customer_events e LEFT JOIN customers c USING (customer_id) WHERE e.source = %s ORDER BY e.event_id",
        (CAPTURE_SOURCE,),
    ).fetchall()
    assert [e["event_type_name"] for e in events] == ["COMPRA", "SALE_SIN_COMPRA"]
    assert events[0]["phone_e164"] == "+523312345678"
    assert events[0]["amount"] == 1899
    assert events[0]["actor"] == "socio"
    assert events[1]["customer_id"] is None


@needs_db
def test_existing_customer_is_reused_by_phone(db):
    db.execute("INSERT INTO customers(client_uuid, phone_e164) VALUES ('legacy-uuid', '+523312345678')")
    summary = guardar_registro(db, [purchase(0)], actor="socio", today=TODAY)
    assert summary["new_customers"] == 0
    event = db.execute("SELECT client_uuid FROM customer_events WHERE source = %s", (CAPTURE_SOURCE,)).fetchone()
    assert event["client_uuid"] == "legacy-uuid"


@needs_db
def test_resubmitting_the_same_batch_skips_duplicates(db):
    guardar_registro(db, [purchase(0)], actor="socio", today=TODAY)
    summary = guardar_registro(db, [purchase(0)], actor="socio", today=TODAY)
    assert summary["saved"] == 0
    assert summary["duplicates"] == 1


@needs_db
def test_one_invalid_row_saves_nothing(db):
    summary = guardar_registro(db, [purchase(0), row(index=1, tipo="COMPRA")], actor="socio", today=TODAY)
    assert summary["saved"] == 0
    assert db.execute("SELECT count(*) AS n FROM customer_events WHERE source = %s", (CAPTURE_SOURCE,)).fetchone()["n"] == 0


@needs_db
def test_phone_shared_by_two_customers_is_flagged(db):
    db.execute("INSERT INTO customers(client_uuid, phone_e164) VALUES ('a', '+523312345678'), ('b', '+523312345678')")
    summary = guardar_registro(db, [purchase(0)], actor="socio", today=TODAY)
    assert summary["saved"] == 0
    assert any("clientes distintos" in e for e in summary["results"][0].errors)


@needs_db
def test_render_escapes_user_text(db):
    summary = guardar_registro(db, [purchase(0, detalle="<script>alert(1)</script>")], actor="socio", today=TODAY)
    assert summary["saved"] == 1
    html = render_registro(db, csrf_token="tok", today=TODAY)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert html.count('name="telefono_') == 15
    assert 'name="csrf" value="tok"' in html
