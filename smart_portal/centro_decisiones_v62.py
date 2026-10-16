from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from smart_portal.portal_v60 import base_page, collect_status, esc, money
from smart_portal.decision_center_v61 import (
    Recommendation,
    build_recommendations,
    collect_decision_context,
    render_recommendation_cards,
    DECISION_CSS,
)
from smart_commerce.amazon_v62 import resumen_amazon
from smart_commerce.marketing_v62 import item_hoy, proximos_items, candidatos_whatsapp
from smart_portal.impacto_v71 import sincronizar_recomendaciones


def _num(v: Any, default=0.0):
    try: return float(v)
    except (TypeError,ValueError): return default


def _int(v: Any, default=0):
    try: return int(v)
    except (TypeError,ValueError): return default


def _pct(v):
    try: return f"{float(v)*100:.2f}%"
    except (TypeError,ValueError): return "—"


def _priority_calendar(priority: str):
    return "HIGH" if priority=="MUY ALTA" else ("MEDIUM" if priority in {"ALTA","MEDIA"} else "LOW")


def construir_recomendaciones_v62(conn, project_root: Path):
    base_context = collect_decision_context(conn, project_root)
    recs = list(build_recommendations(base_context))

    # AMAZON
    try:
        amazon = resumen_amazon(conn)
    except Exception:
        amazon = {"total":0,"actual":{},"anterior":{},"top":[]}

    if amazon.get("total",0) == 0:
        recs.append(Recommendation(
            key="amazon-sin-datos",
            priority="MEDIUM",
            score=74,
            confidence="HIGH",
            category="MONETIZACIÓN",
            title="Importar métricas de Amazon para medir monetización real",
            summary="El portal todavía no puede relacionar contenido con clics, pedidos, conversión, ventas atribuidas y comisiones de Amazon.",
            evidence=("No existen filas de atribución Amazon en PostgreSQL.",),
            action_label="Abrir Amazon",
            action_url="/amazon",
            source=("Amazon","Contenido"),
        ))
    else:
        actual=amazon.get("actual") or {}
        top=amazon.get("top") or []
        clicks=_int(actual.get("clicks"))
        orders=_int(actual.get("ordered_items"))
        conv=_num(actual.get("conversion_rate"))
        epc=_num(actual.get("earnings_per_click"))

        if top:
            best=top[0]
            best_clicks=_int(best.get("clicks"))
            best_orders=_int(best.get("ordered_items"))
            best_conv=_num(best.get("conversion_rate"))
            best_epc=_num(best.get("earnings_per_click"))
            if best_orders >= 2 and (best_conv >= conv or best_epc >= epc) and best_clicks >= 10:
                recs.append(Recommendation(
                    key="amazon-contenido-ganador",
                    priority="HIGH",
                    score=88,
                    confidence="MEDIUM" if best_clicks < 30 else "HIGH",
                    category="MONETIZACIÓN",
                    title=f"Potenciar contenido que ya monetiza: {best.get('content_name')}",
                    summary="Este contenido combina clics con pedidos y eficiencia de monetización. Conviene reforzar su distribución y enlazado antes de crear una pieza equivalente desde cero.",
                    evidence=(
                        f"{best_clicks} clics Amazon.",
                        f"{best_orders} productos pedidos.",
                        f"Conversión: {_pct(best_conv)}.",
                        f"Ingreso por clic: {money(best_epc)}.",
                    ),
                    action_label="Ver Amazon",
                    action_url="/amazon",
                    source=("Amazon","Contenido"),
                ))

        # Volumen de clics sin pedidos: señal de fricción post-clic.
        for row in top[:10]:
            c=_int(row.get("clicks")); o=_int(row.get("ordered_items"))
            if c >= 25 and o == 0:
                recs.append(Recommendation(
                    key=f"amazon-friccion-{row.get('content_name')}",
                    priority="MEDIUM",
                    score=76,
                    confidence="MEDIUM",
                    category="MONETIZACIÓN",
                    title=f"Revisar enlace/producto de Amazon: {row.get('content_name')}",
                    summary="Hay intención de clic, pero no hay pedidos atribuidos en la ventana actual. Revisar ajuste entre contenido, producto enlazado, precio y disponibilidad.",
                    evidence=(f"{c} clics Amazon.", "0 productos pedidos atribuidos."),
                    action_label="Revisar Amazon",
                    action_url="/amazon",
                    source=("Amazon","Contenido"),
                ))
                break

    # CALENDARIO MARKETING
    try:
        hoy = item_hoy(conn)
        proximos = proximos_items(conn, dias=3)
    except Exception:
        hoy=[]; proximos=[]

    for r in hoy[:3]:
        prioridad=_priority_calendar(str(r.get("priority") or ""))
        score=86 if prioridad=="HIGH" else 70
        evidencia=[
            f"Canal: {r.get('channel')}.",
            f"Segmento: {r.get('target_segment')}.",
            f"Hora sugerida: {r.get('suggested_time')}.",
            f"KPI: {r.get('kpi')}.",
        ]
        if "WhatsApp Comunidad" in str(r.get("channel") or ""):
            evidencia.append("Enviar únicamente si existe novedad, restock u oferta real.")
        recs.append(Recommendation(
            key=f"marketing-hoy-{r.get('calendar_key')}",
            priority=prioridad,
            score=score,
            confidence="HIGH",
            category="MARKETING",
            title=f"Calendario de hoy: {r.get('topic')}",
            summary=f"{r.get('hook')} CTA: {r.get('cta')}.",
            evidence=tuple(evidencia),
            action_label="Abrir calendario",
            action_url="/marketing",
            source=("Calendario de marketing",),
        ))

    if not hoy and proximos:
        r=proximos[0]
        recs.append(Recommendation(
            key="marketing-proxima-accion",
            priority="LOW",
            score=54,
            confidence="HIGH",
            category="MARKETING",
            title=f"Próxima acción de marketing: {r.get('topic')}",
            summary=f"Programada para {r.get('scheduled_date')} por {r.get('channel')}.",
            evidence=(f"Prioridad editorial: {r.get('priority')}.",f"KPI: {r.get('kpi')}."),
            action_label="Ver calendario",
            action_url="/marketing",
            source=("Calendario de marketing",),
        ))

    # WHATSAPP 1:1 PERSONALIZADO
    try:
        wa = candidatos_whatsapp(conn, limit=100)
    except Exception:
        wa=[]
    if wa:
        high=sum(1 for r in wa if r.get("priority_band")=="HIGH")
        recs.append(Recommendation(
            key="whatsapp-borradores",
            priority="HIGH" if high else "MEDIUM",
            score=87 if high else 78,
            confidence="HIGH",
            category="WHATSAPP",
            title="Revisar borradores personalizados de WhatsApp 1:1",
            summary="Existen oportunidades que ya pasaron los gates internos de Memory y tienen identidad/contacto disponible. El mensaje sigue requiriendo verificación de consentimiento específico del canal.",
            evidence=(
                f"{len(wa)} candidatos con borrador disponible.",
                f"{high} con prioridad HIGH.",
                "PROTEGIDO y ENFRIAMIENTO están excluidos.",
                "No se envía ningún mensaje desde el portal.",
            ),
            action_label="Revisar borradores",
            action_url="/whatsapp-borradores",
            source=("Memory","Inteligencia de Clientes","WhatsApp"),
        ))

    order={"HIGH":0,"MEDIUM":1,"LOW":2,"OK":3}
    # Dedup por key.
    unique={}
    for r in recs:
        unique[r.key]=r
    return sorted(unique.values(), key=lambda r:(order.get(r.priority,9),-r.score,r.category,r.title))


def render_centro_hoy(conn, project_root: Path):
    recs=construir_recomendaciones_v62(conn,project_root)
    tracking=sincronizar_recomendaciones(conn,recs)
    high=sum(1 for r in recs if r.priority=="HIGH")
    med=sum(1 for r in recs if r.priority=="MEDIUM")
    status=collect_status(conn,project_root)
    ops=(status.get("ops") or {}).get("overall") or "LOCAL"

    if high:
        headline=f"{high} prioridad{'es' if high!=1 else ''} alta"
        sub=f"{med} de prioridad media · revisar antes de ejecutar"
    elif med:
        headline=f"{med} prioridad{'es' if med!=1 else ''} media"
        sub="No hay una recomendación de prioridad alta"
    else:
        headline="Sin acciones urgentes"
        sub="No hay evidencia suficiente para recomendar una acción inmediata"

    contenido=f"""
    {DECISION_CSS}
    <div class="today-hero">
      <div>
        <div style="font-size:11px;font-weight:850;color:#175cd3;text-transform:uppercase;letter-spacing:.08em">HOY · CENTRO DE DECISIONES</div>
        <div class="big">{esc(headline)}</div>
        <div class="small">{esc(sub)}</div>
      </div>
      <a class="decision-action" href="/recomendaciones">Ver todas las recomendaciones →</a>
    </div>
    <div class="decision-section-title"><h2>Qué necesita atención</h2><span>Finanzas · Clientes · Demanda · Amazon · Marketing · WhatsApp · Crecimiento · Operaciones</span></div>
    {render_recommendation_cards(recs,limit=6,tracking=tracking)}
    <div class="callout" style="margin-top:14px">
      <b>Regla central:</b> Sportland Smart recomienda y explica; no compra inventario, no publica contenido,
      no escribe en Shopify, no activa campañas y no envía WhatsApp automáticamente.
    </div>
    """
    return base_page("Hoy",contenido,health=str(ops))


def render_recomendaciones(conn, project_root: Path):
    recs=construir_recomendaciones_v62(conn,project_root)
    tracking=sincronizar_recomendaciones(conn,recs)
    cards = render_recommendation_cards(recs,tracking=tracking)
    calendario = proximos_items(conn,dias=7)
    cal_rows="".join(
        f"<tr><td>{esc(r.get('scheduled_date'))}</td><td>{esc(r.get('priority'))}</td><td><b>{esc(r.get('topic'))}</b></td>"
        f"<td>{esc(r.get('channel'))}</td><td>{esc(r.get('target_segment'))}</td><td>{esc(r.get('suggested_time'))}</td><td>{esc(r.get('kpi'))}</td></tr>"
        for r in calendario
    ) or "<tr><td colspan='7'>Sin acciones próximas.</td></tr>"
    wa_count=0
    try: wa_count=len(candidatos_whatsapp(conn,100))
    except Exception: pass

    contenido=f"""
    {DECISION_CSS}
    <div class="grid">
      <div class="kpi"><div class="tag">ALTA</div><div class="label">Prioridad alta</div><div class="value">{sum(1 for r in recs if r.priority=='HIGH')}</div></div>
      <div class="kpi"><div class="tag">MEDIA</div><div class="label">Prioridad media</div><div class="value">{sum(1 for r in recs if r.priority=='MEDIUM')}</div></div>
      <div class="kpi"><div class="tag">WHATSAPP</div><div class="label">Borradores 1:1</div><div class="value">{wa_count}</div><div class="note">requieren consentimiento</div></div>
      <div class="kpi"><div class="tag">CALENDARIO</div><div class="label">Próximos 7 días</div><div class="value">{len(calendario)}</div></div>
    </div>
    <div class="decision-section-title"><h2>Recomendaciones</h2><span>Ordenadas por prioridad, evidencia y confianza</span></div>
    {cards}
    <div class="panel full" style="margin-top:18px">
      <h2>Calendario de marketing — próximos 7 días</h2>
      <div class="hint">Integrado directamente en la hoja de recomendaciones.</div>
      <table><thead><tr><th>Fecha</th><th>Prioridad</th><th>Tema</th><th>Canal</th><th>Segmento</th><th>Hora</th><th>KPI</th></tr></thead><tbody>{cal_rows}</tbody></table>
    </div>
    <div class="callout" style="margin-top:14px">
      <b>WhatsApp 1:1:</b> los borradores se generan por trigger, no por calendario.
      Requieren gate interno + consentimiento específico del canal; ENFRIAMIENTO y PROTEGIDO quedan fuera.
      <a href="/whatsapp-borradores" style="font-weight:850;color:#175cd3">Abrir borradores →</a>
    </div>
    """
    return base_page("Recomendaciones",contenido)
