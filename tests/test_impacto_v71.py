from decimal import Decimal

import pytest

from smart_portal.impacto_v71 import (
    ACTION_STATUSES,
    ATTRIBUTION_METHODS,
    calcular_valor_economico,
    make_csrf,
    normalizar_monto,
    verify_csrf,
)


def test_valor_economico_no_cuenta_ventas_dos_veces():
    value = calcular_valor_economico(
        attributed_margin=1200,
        avoided_cost=500,
        hours_saved=2,
        hourly_value=250,
    )
    assert value == Decimal("2200.00")


def test_normalizar_monto_rechaza_negativos():
    with pytest.raises(ValueError):
        normalizar_monto("-1")


def test_csrf_valido():
    token = make_csrf("s" * 64, "session-123")
    assert verify_csrf("s" * 64, "session-123", token)


def test_csrf_rechaza_sesion_distinta():
    token = make_csrf("s" * 64, "session-123")
    assert not verify_csrf("s" * 64, "session-456", token)


def test_estados_de_accion_controlados():
    assert ACTION_STATUSES == ("PENDIENTE", "EJECUTADA", "IGNORADA")


def test_metodos_de_atribucion_explicitos():
    assert "PEDIDO" in ATTRIBUTION_METHODS
    assert "ESTIMADO" in ATTRIBUTION_METHODS
    assert "NO_APLICA" in ATTRIBUTION_METHODS
