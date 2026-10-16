from smart_customer.dashboard_v51 import (
    render_brands,
    render_customer_360,
    render_customers,
    render_overview,
    render_segments,
    render_sizes,
)


def test_overview_escapes_content():
    html = render_overview({
        "customer": {
            "customers": 10,
            "with_size": 4,
            "repeat_buyers": 2,
            "lifetime_value": 5000,
            "size_high": 1,
        },
        "purchases": {"purchase_lines": 5, "units": 6},
        "sync": {"status": "OK", "orders_read": 5},
        "opportunity": {"contact_candidates": 1},
        "sizes": [{"size": "27", "customers": 4}],
        "brands": [{"brand": "<Nike>", "profiles": 3}],
    })
    assert "&lt;Nike&gt;" in html
    assert "<Nike>" not in html
    assert "Customer Intelligence" in html


def test_customers_never_inject_search_text():
    html = render_customers([], q="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_sizes_page_contains_customer_link():
    html = render_sizes([{
        "size": "27",
        "customers": 4,
        "observations": 6,
        "high": 1,
        "medium": 1,
        "low": 2,
        "avg_confidence": 0.75,
    }])
    assert "/customers?size=27" in html
    assert "75%" in html


def test_brands_render():
    html = render_brands([
        {"brand": "NIKE", "size": "27", "customers": 3, "observations": 4, "avg_confidence": 0.8},
        {"brand": "NIKE", "size": "27.5", "customers": 1, "observations": 1, "avg_confidence": 0.5},
    ])
    assert "NIKE" in html
    assert "27.5" in html


def test_segments_are_navigation_only():
    html = render_segments([
        {"name": "Talla conocida", "count": 70, "description": "Perfil", "url": "/customers?segment=size_known"}
    ])
    assert "/customers?segment=size_known" in html
    assert "no disparan mensajes" in html.lower()


def test_customer_360_displays_size_profile():
    html = render_customer_360({
        "customer": {
            "customer_id": 1,
            "first_name": "Ana",
            "last_name": "Test",
            "email": "ana@example.com",
            "phone_e164": "+521234",
            "shopify_customer_id": "gid://shopify/Customer/1",
            "shopify_orders_count": 4,
            "shopify_total_spent": 4500,
            "shopify_currency": "MXN",
            "preferred_size": "27",
            "last_purchase_size": "27.5",
            "size_confidence": 0.8,
            "size_confidence_band": "HIGH",
            "size_observation_count": 5,
            "size_counts": {"27": 4, "27.5": 1},
        },
        "brands": [],
        "purchases": [],
        "events": [],
        "intents": [],
        "opportunities": [],
    })
    assert "Ana Test" in html
    assert "27" in html
    assert "80%" in html
    assert "Customer 360" in html
