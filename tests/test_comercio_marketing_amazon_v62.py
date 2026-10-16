from datetime import date
from pathlib import Path

from smart_commerce.amazon_v62 import preparar_filas
from smart_commerce.marketing_v62 import borrador_whatsapp
from smart_portal.centro_decisiones_v62 import _priority_calendar


def test_importador_amazon_calcula_conversion(tmp_path: Path):
    p=tmp_path/"amazon.csv"
    p.write_text(
        "fecha,clics,productos_pedidos,ventas_atribuidas,comisiones,moneda\n"
        "2026-10-01,100,5,3000,150,MXN\n",
        encoding="utf-8",
    )
    rows=preparar_filas(p,date(2026,10,1),[])
    assert len(rows)==1
    assert float(rows[0]["conversion_rate"])==0.05
    assert float(rows[0]["earnings_per_click"])==1.5


def test_importador_amazon_es_estable_por_hash(tmp_path: Path):
    p=tmp_path/"amazon.csv"
    p.write_text(
        "fecha,clics,productos_pedidos,comisiones\n"
        "2026-10-01,10,1,20\n",
        encoding="utf-8",
    )
    a=preparar_filas(p,date(2026,10,1),[])
    b=preparar_filas(p,date(2026,10,1),[])
    assert a[0]["source_row_hash"]==b[0]["source_row_hash"]


def test_borrador_whatsapp_no_inventa_stock():
    msg=borrador_whatsapp({
        "first_name":"Ana",
        "requested_size":"27",
        "resolved_sku":"ABC-27",
        "intent_state":"WAITING_STOCK",
    })
    assert "volvió a aparecer disponibilidad" not in msg
    assert "actualización" in msg


def test_borrador_restock_pide_confirmar_stock():
    msg=borrador_whatsapp({
        "first_name":"Ana",
        "requested_size":"27",
        "resolved_sku":"ABC-27",
        "intent_state":"RESTOCK_MATCH",
    })
    assert "confirmar" in msg
    assert "stock" in msg


def test_prioridad_calendario_muy_alta_se_vuelve_alta():
    assert _priority_calendar("MUY ALTA")=="HIGH"


def test_prioridad_calendario_alta_se_vuelve_media():
    assert _priority_calendar("ALTA")=="MEDIUM"
