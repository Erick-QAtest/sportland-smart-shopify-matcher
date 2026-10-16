from smart_portal.finanzas_proyeccion_v63 import inferir_finanzas


def test_infiere_ventas_e_inventario_desde_snapshot():
    data = inferir_finanzas({
        "kpis": {
            "sales_30d": 50000,
            "orders_30d": 50,
            "inventory_value": 120000,
            "gross_margin_pct": 40,
        }
    })
    assert data["ventas_30d"] == 50000
    assert data["inventario"] == 120000
    assert data["margen"] == 0.40
    assert data["ticket_promedio"] == 1000


def test_no_inventa_inventario_si_no_existe():
    data = inferir_finanzas({"kpis": {"sales_30d": 50000}})
    assert data["inventario"] is None


def test_margen_decimal_se_conserva():
    data = inferir_finanzas({"gross_margin_rate": 0.32})
    assert data["margen"] == 0.32
