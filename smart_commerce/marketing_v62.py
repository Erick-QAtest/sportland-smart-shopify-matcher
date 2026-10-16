from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import hashlib
from typing import Any

from smart_portal.portal_v60 import base_page, esc


PRIORIDAD_ORDEN = {"MUY ALTA":0,"ALTA":1,"MEDIA":2,"BAJA":3}


def _leer_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def importar_calendario(conn, csv_path: Path) -> int:
    rows = _leer_csv(csv_path)
    count = 0
    for r in rows:
        fecha = datetime.strptime(r["Fecha"], "%d/%m/%Y").date()
        raw_key = "|".join([r["Fecha"],r["Canal"],r["Tema / pieza"]])
        key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT INTO marketing_calendar_items(
                 calendar_key,scheduled_date,weekday_name,pillar,target_segment,channel,format,
                 topic,hook,cta,destination,event_signal,ads_distribution,suggested_time,kpi,priority,status
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(calendar_key) DO UPDATE SET
                 scheduled_date=EXCLUDED.scheduled_date,weekday_name=EXCLUDED.weekday_name,
                 pillar=EXCLUDED.pillar,target_segment=EXCLUDED.target_segment,channel=EXCLUDED.channel,
                 format=EXCLUDED.format,topic=EXCLUDED.topic,hook=EXCLUDED.hook,cta=EXCLUDED.cta,
                 destination=EXCLUDED.destination,event_signal=EXCLUDED.event_signal,
                 ads_distribution=EXCLUDED.ads_distribution,suggested_time=EXCLUDED.suggested_time,
                 kpi=EXCLUDED.kpi,priority=EXCLUDED.priority,status=EXCLUDED.status,updated_at=now()""",
            (key,fecha,r["Día"],r["Pilar"],r["Segmento objetivo"],r["Canal"],r["Formato"],
             r["Tema / pieza"],r["Hook / ángulo"],r["CTA"],r["Destino"],r["Evento / señal"],
             r["Distribución Ads"],r["Hora sugerida"],r["KPI"],r["Prioridad"],r["Estado"]),
        )
        count += 1
    conn.execute(
        """INSERT INTO marketing_calendar_imports(source_name,rows_imported,metadata)
           VALUES('Sportland_Calendario_Redes_Comunidad_30_dias',%s,'{"version":"v2","mes":"octubre 2026"}'::jsonb)
           ON CONFLICT(source_name) DO UPDATE SET imported_at=now(),rows_imported=EXCLUDED.rows_imported,
             metadata=EXCLUDED.metadata""",
        (count,),
    )
    conn.commit()
    return count


def proximos_items(conn, desde: date | None = None, dias: int = 7):
    desde = desde or date.today()
    hasta = desde + timedelta(days=dias-1)
    return [dict(r) for r in conn.execute(
        """SELECT * FROM marketing_calendar_items
           WHERE scheduled_date BETWEEN %s AND %s
           ORDER BY scheduled_date,
             CASE priority WHEN 'MUY ALTA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END,
             suggested_time""",
        (desde,hasta),
    ).fetchall()]


def item_hoy(conn, hoy: date | None = None):
    hoy = hoy or date.today()
    return [dict(r) for r in conn.execute(
        """SELECT * FROM marketing_calendar_items
           WHERE scheduled_date=%s
           ORDER BY CASE priority WHEN 'MUY ALTA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END""",
        (hoy,),
    ).fetchall()]


def candidatos_whatsapp(conn, limit: int = 50):
    return [dict(r) for r in conn.execute(
        """SELECT
             co.opportunity_id,co.customer_id,co.action,co.eligible_for_contact,
             co.reason,co.opportunity_score,co.priority_band,co.source_state,
             c.first_name,c.last_name,c.phone_e164,c.current_stage,c.preferred_size,
             c.size_confidence_band,c.shopify_orders_count,c.shopify_total_spent,
             di.requested_size,di.resolved_sku,di.smart_sku,di.state AS intent_state
           FROM commercial_opportunities co
           JOIN customers c ON c.customer_id=co.customer_id
           LEFT JOIN demand_intents di ON di.intent_id=co.intent_id
           WHERE co.lifecycle_status='OPEN'
             AND co.action='CONTACT_CANDIDATE'
             AND co.eligible_for_contact=TRUE
             AND c.phone_e164 IS NOT NULL
             AND UPPER(COALESCE(c.current_stage,'')) NOT IN ('PROTEGIDO','ENFRIAMIENTO')
           ORDER BY
             CASE co.priority_band WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
             co.opportunity_score DESC NULLS LAST,
             co.evaluated_at DESC
           LIMIT %s""",
        (max(1,min(limit,200)),),
    ).fetchall()]


def borrador_whatsapp(row: dict[str, Any]) -> str:
    nombre = (row.get("first_name") or "").strip() or "Hola"
    talla = row.get("requested_size") or row.get("preferred_size")
    sku = row.get("resolved_sku") or row.get("smart_sku")
    state = str(row.get("intent_state") or "")

    detalle = ""
    if sku and talla:
        detalle = f"{sku} en talla {talla}"
    elif sku:
        detalle = str(sku)
    elif talla:
        detalle = f"la talla {talla}"
    else:
        detalle = "lo que estabas buscando"

    if state == "RESTOCK_MATCH":
        return (
            f"Hola {nombre}, volvió a aparecer disponibilidad relacionada con {detalle}. "
            "Antes de comprar conviene confirmar que el stock siga vigente. "
            "Si quieres, te comparto el enlace y la disponibilidad actual."
        )
    return (
        f"Hola {nombre}, tengo una actualización relacionada con {detalle}. "
        "Si todavía te interesa, puedo compartirte la disponibilidad actual."
    )


def render_calendario(conn):
    rows = proximos_items(conn, dias=14)
    body = "".join(
        f"<tr><td><b>{esc(r['scheduled_date'])}</b><br>{esc(r.get('weekday_name'))}</td>"
        f"<td>{esc(r.get('priority'))}</td><td><b>{esc(r.get('topic'))}</b><br><span style='color:#667085'>{esc(r.get('hook'))}</span></td>"
        f"<td>{esc(r.get('channel'))}</td><td>{esc(r.get('target_segment'))}</td><td>{esc(r.get('suggested_time'))}</td>"
        f"<td>{esc(r.get('cta'))}</td><td>{esc(r.get('kpi'))}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='8'>No hay publicaciones planificadas en esta ventana.</td></tr>"
    return base_page("Calendario de marketing",f"""
      <div class="panel full">
        <h2>Próximas acciones de marketing</h2>
        <div class="hint">Calendario estratégico v2 de Sportland. Las horas son punto de partida para prueba, no una hora óptima definitiva.</div>
        <table><thead><tr><th>Fecha</th><th>Prioridad</th><th>Tema</th><th>Canal</th><th>Segmento</th><th>Hora</th><th>CTA</th><th>KPI</th></tr></thead><tbody>{body}</tbody></table>
      </div>
      <div class="callout" style="margin-top:14px">
        <b>Regla editorial:</b> 35% producto/conversión · 30% educación/SEO · 20% confianza/prueba social · 15% engagement/captura de señales.
      </div>
    """)


def render_whatsapp(conn):
    rows = candidatos_whatsapp(conn)
    body = "".join(
        f"<tr><td><b>{esc((r.get('first_name') or '')+' '+(r.get('last_name') or ''))}</b><br><span style='color:#98a2b3'>ID {r.get('customer_id')}</span></td>"
        f"<td>{esc(r.get('priority_band') or '—')}<br>{esc(r.get('opportunity_score') or '—')}</td>"
        f"<td>{esc(r.get('requested_size') or r.get('preferred_size') or '—')}</td>"
        f"<td>{esc(r.get('resolved_sku') or r.get('smart_sku') or '—')}</td>"
        f"<td style='max-width:520px'>{esc(borrador_whatsapp(r))}</td>"
        f"<td><b>REVISAR</b><br><span style='color:#b54708'>Consentimiento del canal por verificar</span></td>"
        f"<td><a href='/customer?customer_id={r.get('customer_id')}' style='color:#175cd3;font-weight:800'>Cliente 360°</a></td></tr>"
        for r in rows
    ) or "<tr><td colspan='7'>No hay candidatos 1:1 que hayan pasado los gates internos actuales.</td></tr>"
    return base_page("Borradores de WhatsApp",f"""
      <div class="callout">
        <b>Solo borradores.</b> S-Mart 1:1 es activado por intención/restock; no tiene calendario fijo.
        Antes de usar un borrador se debe verificar consentimiento específico del canal.
        PROTEGIDO y ENFRIAMIENTO quedan excluidos. El portal no envía mensajes.
      </div>
      <div class="panel full" style="margin-top:14px">
        <h2>WhatsApp 1:1 para revisión humana</h2>
        <div class="hint">Personalización basada en talla/modelo/intención ya conocidos, sin inventar stock, precio, restock ni urgencia.</div>
        <table><thead><tr><th>Cliente</th><th>Prioridad</th><th>Talla</th><th>SKU</th><th>Borrador</th><th>Gate</th><th></th></tr></thead><tbody>{body}</tbody></table>
      </div>
      <div class="callout" style="margin-top:14px">
        <b>Comunidad WhatsApp:</b> 1–2 envíos por semana. Priorizar nuevos productos reales, restock amplio u oferta verdadera.
        Sin novedad real, se omite el envío.
      </div>
    """)
