"""Marketing Intelligence v8.0 contra PostgreSQL (se salta sin SPORTLAND_TEST_DATABASE_URL).

La base de prueba debe tener aplicadas todas las migraciones (001 en adelante).
"""
from datetime import date
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest

from smart_marketing import store
from smart_memory.db import apply_migrations, rollback_migration
from smart_portal import marketing_v80

DB_URL = os.getenv("SPORTLAND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Define SPORTLAND_TEST_DATABASE_URL para las pruebas con base de datos.")
MIGRATIONS = Path(__file__).resolve().parents[1] / "database" / "migrations"


@pytest.fixture
def db():
    conn = psycopg.connect(DB_URL, row_factory=dict_row)
    with conn.transaction() as tx:
        yield conn
        raise psycopg.Rollback(tx)
    conn.close()


def new_item(db, **over):
    form = {"scheduled_date": ["2026-11-02"], "channel": ["WhatsApp comunidad"], "community_code": ["WA_LOCAL"],
            "content_type": ["PRODUCTO"], "topic": ["Puma Softride Pro, comodidad diaria"],
            "copy_text": ["Comodidad para todos los días."], "suggested_time": ["12:30"]}
    form.update({k: [v] for k, v in over.items()})
    data, errors = store.parse_item_form(form)
    assert errors == []
    return store.create_item(db, data, actor="test")


def test_seed_campaigns_and_historic_polls_are_present(db):
    codes = [c["code"] for c in store.list_campaigns(db)]
    for code in ("2026-11-COMODIDAD", "2026-11-BUEN-FIN", "2026-11-BF-CM", "2026-12-CIERRE"):
        assert code in codes
    buen_fin = next(c for c in store.list_campaigns(db) if c["code"] == "2026-11-BUEN-FIN")
    assert (buen_fin["starts_on"], buen_fin["ends_on"]) == (date(2026, 11, 13), date(2026, 11, 17))
    polls = {p["question"]: p for p in store.list_polls(db)}
    price = polls["¿Cuánto consideras buen precio por unos tenis originales?"]
    assert sum(o["selections"] for o in price["options"]) == 33 and price["unique_voters"] is None


def test_full_workflow_is_logged_and_approval_is_recorded(db):
    key = new_item(db)
    assert store.transition_item(db, key, "EN_REVISION", actor="erick") == []
    assert store.transition_item(db, key, "APROBADO", actor="erick") == []
    assert store.transition_item(db, key, "PROGRAMADO", actor="erick") == []
    assert store.transition_item(db, key, "PUBLICADO", actor="erick", published_ref="https://wa.me/x") == []
    assert store.transition_item(db, key, "MEDIDO", actor="erick", note="2 ventas declaradas") == []
    it = store.get_item(db, key)
    assert it["approved_by"] == "erick" and it["approved_at"] and it["published_at"] and it["measured_at"]
    assert it["published_ref"] == "https://wa.me/x" and it["result_notes"] == "2 ventas declaradas"
    actions = [(l["action"], l["to_status"]) for l in reversed(store.item_log(db, key))]
    assert actions == [("crear", "BORRADOR"), ("estado", "EN_REVISION"), ("estado", "APROBADO"),
                       ("estado", "PROGRAMADO"), ("estado", "PUBLICADO"), ("estado", "MEDIDO")]


def test_cannot_publish_without_approval_in_app_and_in_database(db):
    key = new_item(db)
    errors = store.transition_item(db, key, "PUBLICADO", actor="erick")
    assert errors and store.get_item(db, key)["workflow_status"] == "BORRADOR"
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():
            db.execute("UPDATE marketing_calendar_items SET workflow_status='PUBLICADO' WHERE calendar_key=%s", (key,))


def test_reject_and_reopen_clear_the_approval(db):
    key = new_item(db)
    store.transition_item(db, key, "EN_REVISION", actor="erick")
    assert store.transition_item(db, key, "BORRADOR", actor="erick")  # sin motivo: rechazado
    assert store.transition_item(db, key, "BORRADOR", actor="erick", note="Falta tallas") == []
    store.transition_item(db, key, "EN_REVISION", actor="erick")
    store.transition_item(db, key, "APROBADO", actor="erick")
    assert store.transition_item(db, key, "BORRADOR", actor="erick") == []
    it = store.get_item(db, key)
    assert it["approved_at"] is None and it["approved_by"] is None


def test_editing_is_blocked_after_approval_but_rescheduling_keeps_it(db):
    key = new_item(db)
    store.transition_item(db, key, "EN_REVISION", actor="erick")
    store.transition_item(db, key, "APROBADO", actor="erick")
    data, _ = store.parse_item_form({"scheduled_date": ["2026-11-02"], "channel": ["Instagram"], "topic": ["Otro"]})
    assert store.update_item(db, key, data, actor="erick")
    assert store.reschedule_item(db, key, date(2026, 11, 4), "13:00", actor="erick") == []
    it = store.get_item(db, key)
    assert (it["scheduled_date"], it["suggested_time"], it["weekday_name"]) == (date(2026, 11, 4), "13:00", "miércoles")
    assert it["approved_at"] is not None and it["channel"] == "WhatsApp comunidad"


def test_reimporting_the_csv_never_resets_an_approval(db, monkeypatch):
    # El importador hace commit() propio; aquí todo queda dentro de la transacción de prueba.
    monkeypatch.setattr(db, "commit", lambda: None)
    from smart_commerce.marketing_v62 import importar_calendario
    import csv, tempfile
    header = ["Fecha", "Día", "Pilar", "Segmento objetivo", "Canal", "Formato", "Tema / pieza", "Hook / ángulo",
              "CTA", "Destino", "Evento / señal", "Distribución Ads", "Hora sugerida", "KPI", "Prioridad", "Estado"]
    row = ["02/11/2026", "lunes", "Producto", "S6", "WhatsApp Comunidad", "Post", "Restock real", "", "Ver",
           "", "", "", "12:30", "Pedidos", "ALTA", "PLANIFICADO"]
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as f:
        csv.writer(f).writerows([header, row])
    importar_calendario(db, Path(f.name))
    key = db.execute("SELECT calendar_key FROM marketing_calendar_items WHERE topic='Restock real'").fetchone()["calendar_key"]
    store.transition_item(db, key, "EN_REVISION", actor="erick")
    store.transition_item(db, key, "APROBADO", actor="erick")
    importar_calendario(db, Path(f.name))
    assert store.get_item(db, key)["workflow_status"] == "APROBADO"
    os.unlink(f.name)


def test_week_template_generation_is_idempotent(db):
    camp = next(c for c in store.list_campaigns(db) if c["code"] == "2026-11-COMODIDAD")
    inserted, existing, errors = store.generate_campaign_drafts(db, camp["campaign_id"], ["WA_LOCAL", "WA_ONLINE"], actor="erick")
    assert errors == [] and (inserted, existing) == (8, 0)
    assert store.generate_campaign_drafts(db, camp["campaign_id"], ["WA_LOCAL", "WA_ONLINE"], actor="erick")[:2] == (0, 8)
    week = store.list_items(db, date(2026, 11, 2), date(2026, 11, 8), {"campana": str(camp["campaign_id"])})
    assert len(week) == 8 and all(i["workflow_status"] == "BORRADOR" for i in week)


def test_calendar_filters(db):
    new_item(db)
    new_item(db, channel="Instagram", community_code="", content_type="EDUCATIVO", topic="Qué es SoftFoam")
    day = date(2026, 11, 2)
    assert {i["topic"] for i in store.list_items(db, day, day, {"plataforma": "instagram"})} == {"Qué es SoftFoam"}
    assert {i["topic"] for i in store.list_items(db, day, day, {"comunidad": "WA_LOCAL"})} == {"Puma Softride Pro, comodidad diaria"}
    assert {i["topic"] for i in store.list_items(db, day, day, {"tipo": "EDUCATIVO"})} == {"Qué es SoftFoam"}
    assert len(store.list_items(db, day, day, {"estado": "BORRADOR"})) >= 2


def test_poll_is_saved_with_options_and_log(db):
    form = {"question": ["¿Qué talla usas en PUMA?"], "category": ["TALLA"], "multi_select": ["1"],
            "opcion_label_0": ["25"], "opcion_sel_0": ["7"], "opcion_label_1": ["26.5"], "opcion_sel_1": ["4"]}
    data, errors = store.parse_poll_form(form)
    assert errors == []
    poll_id = store.save_poll(db, data, actor="erick")
    saved = next(p for p in store.list_polls(db) if p["poll_id"] == poll_id)
    assert [o["selections"] for o in saved["options"]] == [7, 4] and saved["unique_voters"] is None
    assert db.execute("SELECT count(*) n FROM marketing_change_log WHERE entity_type='ENCUESTA' AND entity_key=%s",
                      (str(poll_id),)).fetchone()["n"] == 1


def test_pages_render_escape_user_text_and_carry_csrf(db):
    key = new_item(db, topic="<script>alert(1)</script>")
    pages = [
        marketing_v80.render_hoy(db, csrf="tok", today=date(2026, 11, 2)),
        marketing_v80.render_calendar(db, query={"vista": ["mes"], "fecha": ["2026-11-02"]}, csrf="tok"),
        marketing_v80.render_calendar(db, query={"vista": ["semana"], "fecha": ["2026-11-02"]}, csrf="tok"),
        marketing_v80.render_calendar(db, query={"vista": ["dia"], "fecha": ["2026-11-02"]}, csrf="tok"),
        marketing_v80.render_item(db, key, csrf="tok")[1],
        marketing_v80.render_campaigns(db, csrf="tok"),
        marketing_v80.render_polls(db, csrf="tok"),
        marketing_v80.render_assets(db, csrf="tok"),
    ]
    for html in pages:
        assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in pages[1]
    assert 'name="csrf" value="tok"' in pages[4] or "name='csrf' value='tok'" in pages[4]
    assert "El Buen Fin 2026" in pages[5]
    assert "no 33 personas" in pages[6]


def test_post_handler_creates_moves_and_rejects_invalid(db):
    kind, status, url = marketing_v80.handle_post(db, "/marketing/item/guardar", {
        "scheduled_date": ["2026-11-03"], "channel": ["Instagram"], "topic": ["Reel SoftFoam"]}, actor="erick", csrf="tok")
    assert (kind, status) == ("redirect", 303) and "msg=creado" in url
    key = url.split("key=")[1].split("&")[0]
    kind, status, _ = marketing_v80.handle_post(db, "/marketing/item/estado", {"key": [key], "to": ["PUBLICADO"]},
                                                actor="erick", csrf="tok")
    assert (kind, status) == ("html", 400)
    kind, status, html = marketing_v80.handle_post(db, "/marketing/item/guardar", {
        "scheduled_date": ["no-es-fecha"], "channel": [""], "topic": [""]}, actor="erick", csrf="tok")
    assert status == 400 and "Fecha inválida" in html
    kind, status, url = marketing_v80.handle_post(db, "/marketing/item/estado", {
        "key": [key], "to": ["EN_REVISION"], "volver": ["https://evil.example/"]}, actor="erick", csrf="tok")
    assert url.startswith("/marketing/item?")


def test_migrations_roll_back_and_reapply_without_touching_existing_rows(db):
    db.execute("INSERT INTO marketing_calendar_items(calendar_key, scheduled_date, topic) VALUES ('legacy-1', '2026-10-20', 'Legacy')")
    before = db.execute("SELECT count(*) n FROM marketing_calendar_items").fetchone()["n"]
    assert rollback_migration(db, "019_marketing_polls", MIGRATIONS)
    assert rollback_migration(db, "018_marketing_campaigns", MIGRATIONS)
    assert db.execute("SELECT to_regclass('marketing_campaigns') r").fetchone()["r"] is None
    assert db.execute("SELECT count(*) n FROM marketing_calendar_items").fetchone()["n"] == before
    assert apply_migrations(db, MIGRATIONS) == ["018_marketing_campaigns.sql", "019_marketing_polls.sql"]
    assert apply_migrations(db, MIGRATIONS) == []
    assert db.execute("SELECT count(*) n FROM marketing_calendar_items").fetchone()["n"] == before
    assert store.get_item(db, "legacy-1")["workflow_status"] == "BORRADOR"
