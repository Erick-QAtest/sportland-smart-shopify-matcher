import os

import psycopg
from psycopg.rows import dict_row
import pytest

from smart_customer.identity_import import import_identity_map

DB_URL = os.getenv("SPORTLAND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Define SPORTLAND_TEST_DATABASE_URL para las pruebas con base de datos.")


@pytest.fixture
def db():
    conn = psycopg.connect(DB_URL, row_factory=dict_row)
    with conn.transaction() as tx:
        yield conn
        raise psycopg.Rollback(tx)
    conn.close()


def phones(db):
    return {r["client_uuid"]: r["phone_e164"] for r in db.execute("SELECT client_uuid, phone_e164 FROM customers").fetchall()}


ROWS = [
    {"telefono_e164": "+523311112222", "client_uuid": "u-existente"},
    {"telefono_e164": "+523333334444", "client_uuid": "u-nuevo", "first_seen_at": "2026-05-01"},
    {"telefono_e164": "+523355556666", "client_uuid": "u-dup-a"},
    {"telefono_e164": "+523355556666", "client_uuid": "u-dup-b"},
    {"telefono_e164": "33", "client_uuid": "u-malo"},
]


def test_dry_run_changes_nothing(db):
    db.execute("INSERT INTO customers(client_uuid) VALUES ('u-existente')")
    stats = import_identity_map(db, ROWS, apply=False)
    assert stats["phone_added"] == 1 and stats["customers_created"] == 1
    assert phones(db) == {"u-existente": None}


def test_apply_links_phones_and_reports_conflicts(db):
    db.execute("INSERT INTO customers(client_uuid) VALUES ('u-existente')")
    stats = import_identity_map(db, ROWS, apply=True)
    assert phones(db) == {"u-existente": "+523311112222", "u-nuevo": "+523333334444"}
    assert stats["invalid"] == 1
    assert len(stats["conflicts"]) == 1 and "···6666" in stats["conflicts"][0]
    again = import_identity_map(db, ROWS, apply=True)
    assert again["already_ok"] == 2 and again["phone_added"] == 0 and again["customers_created"] == 0


def test_phone_owned_by_another_customer_is_not_moved(db):
    db.execute("INSERT INTO customers(client_uuid, phone_e164) VALUES ('otro', '+523311112222'), ('u-existente', NULL)")
    stats = import_identity_map(db, ROWS[:1], apply=True)
    assert phones(db)["u-existente"] is None
    assert "otro cliente" in stats["conflicts"][0]
