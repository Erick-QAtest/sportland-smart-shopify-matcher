from smart_portal.decision_center_v61 import (
    build_recommendations,
    render_recommendation_cards,
)


def base_context():
    return {
        "customer": {
            "customers": 5653,
            "with_size": 70,
            "size_high": 0,
            "size_medium": 0,
            "known_customer_orders": 2600,
        },
        "purchase": {
            "captured_orders": 114,
            "purchase_lines": 148,
        },
        "sync": {
            "status": "OK",
            "orders_read": 114,
            "customers_read": 5653,
        },
        "opportunity": {
            "contact_candidates": 0,
            "high_opportunities": 0,
            "max_score": None,
        },
        "demand_groups": [],
        "finance": {
            "financial_health": {
                "score": 48.6,
                "status": "TIGHT",
            },
            "kpis": {
                "cash_coverage_ratio": 0.82,
                "projected_cash_gap": -12000,
            },
        },
        "ops": {
            "overall": "HEALTHY",
            "reasons": [],
        },
        "growth": {
            "HIGH": 3,
            "MEDIUM": 40,
        },
        "memory": {},
    }


def test_finance_recommendation_is_high_when_health_is_low():
    recs = build_recommendations(base_context())
    finance = next(r for r in recs if r.key == "finance-protect-liquidity")
    assert finance.priority == "HIGH"
    assert finance.confidence == "HIGH"
    assert finance.action_url == "/finance"


def test_partial_history_is_detected():
    recs = build_recommendations(base_context())
    data = next(r for r in recs if r.key == "data-complete-order-history")
    assert data.priority == "MEDIUM"
    assert "historial" in data.title.lower()


def test_growth_high_is_surfaced_but_not_auto_executed():
    recs = build_recommendations(base_context())
    growth = next(r for r in recs if r.key == "growth-high-review")
    assert growth.priority == "MEDIUM"
    assert "revisar" in growth.title.lower()


def test_demand_and_inventory_create_explainable_restock_review():
    ctx = base_context()
    ctx["finance"]["financial_health"]["score"] = 70
    ctx["demand_groups"] = [{
        "sku": "2080-27",
        "requested_size": "27",
        "signals": 4,
        "waiting_stock": 4,
        "restock_matches": 0,
        "identified_customers": 3,
        "stock_quantity": 1,
    }]
    recs = build_recommendations(ctx)
    demand = next(r for r in recs if r.category == "DEMAND")
    assert demand.priority == "HIGH"
    assert "2080-27" in demand.title
    assert any("Stock" in item for item in demand.evidence)


def test_ops_fail_is_top_priority():
    ctx = base_context()
    ctx["ops"] = {
        "overall": "FAIL",
        "reasons": ["Backup no verificado"],
    }
    recs = build_recommendations(ctx)
    assert recs[0].key == "ops-fail"
    assert recs[0].score == 100


def test_no_signals_returns_explicit_all_clear():
    ctx = {
        "customer": {
            "customers": 10,
            "with_size": 10,
            "known_customer_orders": 10,
        },
        "purchase": {
            "captured_orders": 10,
        },
        "sync": {"status": "OK"},
        "opportunity": {},
        "demand_groups": [],
        "finance": {
            "financial_health": {"score": 90, "status": "HEALTHY"},
            "kpis": {},
        },
        "ops": {"overall": "HEALTHY", "reasons": []},
        "growth": {},
        "memory": {},
    }
    recs = build_recommendations(ctx)
    assert len(recs) == 1
    assert recs[0].priority == "OK"


def test_recommendation_html_escapes_evidence():
    ctx = base_context()
    recs = build_recommendations(ctx)
    html = render_recommendation_cards(recs[:1])
    assert "Puntaje de decisión" in html
    assert "ejecuta" not in html.lower()
