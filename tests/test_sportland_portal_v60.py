from pathlib import Path

from smart_portal.portal_v60 import (
    add_portal_ribbon,
    base_page,
    render_home,
    render_missing_artifact,
)


def test_base_page_contains_core_navigation():
    doc = base_page("Test", "<p>ok</p>", health="HEALTHY")
    assert 'href="/customer-intelligence"' in doc
    assert 'href="/finance"' in doc
    assert 'href="/memory"' in doc
    assert 'href="/growth"' in doc
    assert 'href="/ops"' in doc


def test_portal_ribbon_is_injected_into_static_dashboard():
    doc = "<!doctype html><html><body><main>Finance</main></body></html>"
    out = add_portal_ribbon(doc)
    assert "SPORTLAND SMART" in out
    assert out.index("SPORTLAND SMART") < out.index("Finance")


def test_customer_page_overview_link_is_rewritten():
    doc = '<html><body><a href="/">Overview</a></body></html>'
    out = add_portal_ribbon(doc, customer_page=True)
    assert 'href="/customer-intelligence"' in out


def test_missing_artifact_has_friendly_message():
    out = render_missing_artifact("Finance", Path("/tmp/missing.html"))
    assert "Finanzas" in out
    assert "todavía no existe" in out


def test_home_renders_modules_and_escapes_values():
    out = render_home({
        "customer": {
            "customers": 5653,
            "with_size": 70,
            "repeat_buyers": 10,
            "lifetime_value": 10000,
        },
        "memory": {
            "events": 100,
            "demand_intents": 2,
            "waiting_stock": 1,
            "restock_matches": 0,
            "open_commercial_opportunities": 1,
            "contact_candidates": 1,
        },
        "growth": {"HIGH": 3, "MEDIUM": 40},
        "finance": {
            "kpis": {"sales_30d": 50955, "orders_30d": 47},
            "financial_health": {"score": 48.6, "status": "TIGHT"},
        },
        "ops": {"overall": "HEALTHY"},
        "customer_sync": {
            "status": "OK",
            "orders_read": 114,
            "customers_read": 5653,
        },
    })
    assert "5,653" not in out  # integers are intentionally rendered without locale formatting
    assert "5653" in out
    assert "Inteligencia de Clientes" in out
    assert "Finanzas" in out
    assert "Crecimiento" in out
    assert "HEALTHY" in out


def test_home_does_not_contain_contact_action_controls():
    out = render_home({
        "customer": {},
        "memory": {},
        "growth": {},
        "finance": {},
        "ops": {},
        "customer_sync": {},
    })
    lowered = out.lower()
    assert "send whatsapp" not in lowered
    assert "send email" not in lowered
    assert "acciones automáticas desactivadas" in lowered
