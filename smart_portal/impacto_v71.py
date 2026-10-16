from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
from typing import Any

from smart_portal.portal_v60 import base_page, esc, money


ACTION_STATUSES = ("PENDIENTE", "EJECUTADA", "IGNORADA")
OUTCOMES = ("POSITIVO", "NEUTRO", "NEGATIVO", "INCIERTO")
ATTRIBUTION_METHODS = ("MANUAL", "PEDIDO", "ESTIMADO", "NO_APLICA")
ATTRIBUTION_CONFIDENCE = ("ALTA", "MEDIA", "BAJA")


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def normalizar_monto(value: Any) -> Decimal:
    number = _decimal(value)
    if number < 0:
        raise ValueError("Los montos no pueden ser negativos.")
    return number.quantize(Decimal("0.01"))


def calcular_valor_economico(
    attributed_margin: Any,
    avoided_cost: Any,
    hours_saved: Any,
    hourly_value: Any,
) -> Decimal:
    margen = normalizar_monto(attributed_margin)
    evitado = normalizar_monto(avoided_cost)
    horas = normalizar_monto(hours_saved)
    valor_hora = normalizar_monto(hourly_value)
    return (margen + evitado + horas * valor_hora).quantize(Decimal("0.01"))


def make_csrf(secret: str, session_token: str) -> str:
    key = (secret or "sportland-local-only").encode("utf-8")
    msg = (session_token or "local-session").encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify_csrf(secret: str, session_token: str, token: str) -> bool:
    expected = make_csrf(secret, session_token)
    return bool(token) and hmac.compare_digest(expected, token)


def _rec_dict(rec: Any) -> dict[str, Any]:
    try:
        return asdict(rec)
    except Exception:
        return {
            "key": getattr(rec, "key", ""),
            "priority": getattr(rec, "priority", ""),
            "score": getattr(rec, "score", 0),
            "confidence": getattr(rec, "confidence", ""),
            "category": getattr(rec, "category", ""),
            "title": getattr(rec, "title", ""),
            "summary": getattr(rec, "summary", ""),
            "action_label": getattr(rec, "action_label", ""),
            "action_url": getattr(rec, "action_url", ""),
            "source": tuple(getattr(rec, "source", ()) or ()),
        }


def sincronizar_recomendaciones(conn, recommendations: list[Any]) -> dict[str, dict[str, Any]]:
    latest_rows = conn.execute(
        """
        SELECT DISTINCT ON (recommendation_key)
          recommendation_episode_id,
          recommendation_key,
          episode_no,
          active_now,
          ended_at,
          action_status,
          measurement_status,
          outcome
        FROM recommendation_episodes
        ORDER BY recommendation_key, episode_no DESC
        """
    ).fetchall()

    latest = {str(r["recommendation_key"]): dict(r) for r in latest_rows}
    current_keys: set[str] = set()
    tracking: dict[str, dict[str, Any]] = {}

    for rec in recommendations:
        data = _rec_dict(rec)
        key = str(data.get("key") or "").strip()
        if not key:
            continue
        current_keys.add(key)
        previous = latest.get(key)
        source_json = json.dumps(list(data.get("source") or ()), ensure_ascii=False)

        if previous and previous.get("ended_at") is None:
            row = conn.execute(
                """
                UPDATE recommendation_episodes
                SET
                  active_now=TRUE,
                  last_seen_at=NOW(),
                  priority=%s,
                  score=%s,
                  confidence=%s,
                  category=%s,
                  title=%s,
                  summary=%s,
                  action_label=%s,
                  action_url=%s,
                  source_json=%s::jsonb,
                  updated_at=NOW()
                WHERE recommendation_episode_id=%s
                RETURNING
                  recommendation_episode_id,
                  action_status,
                  measurement_status,
                  outcome
                """,
                (
                    data.get("priority"),
                    int(data.get("score") or 0),
                    data.get("confidence"),
                    data.get("category"),
                    data.get("title"),
                    data.get("summary"),
                    data.get("action_label"),
                    data.get("action_url"),
                    source_json,
                    previous["recommendation_episode_id"],
                ),
            ).fetchone()
        else:
            episode_no = int(previous["episode_no"]) + 1 if previous else 1
            row = conn.execute(
                """
                INSERT INTO recommendation_episodes (
                  recommendation_key,
                  episode_no,
                  active_now,
                  priority,
                  score,
                  confidence,
                  category,
                  title,
                  summary,
                  action_label,
                  action_url,
                  source_json
                )
                VALUES (%s,%s,TRUE,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING
                  recommendation_episode_id,
                  action_status,
                  measurement_status,
                  outcome
                """,
                (
                    key,
                    episode_no,
                    data.get("priority"),
                    int(data.get("score") or 0),
                    data.get("confidence"),
                    data.get("category"),
                    data.get("title"),
                    data.get("summary"),
                    data.get("action_label"),
                    data.get("action_url"),
                    source_json,
                ),
            ).fetchone()

        tracking[key] = dict(row)

    for key, previous in latest.items():
        if key in current_keys or previous.get("ended_at") is not None:
            continue
        conn.execute(
            """
            UPDATE recommendation_episodes
            SET active_now=FALSE, ended_at=NOW(), updated_at=NOW()
            WHERE recommendation_episode_id=%s
              AND ended_at IS NULL
            """,
            (previous["recommendation_episode_id"],),
        )

    conn.commit()
    return tracking


def _snapshot(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    keep = (
        "action_status",
        "action_at",
        "action_notes",
        "measurement_status",
        "outcome",
        "attribution_method",
        "attribution_confidence",
        "attributed_revenue",
        "attributed_margin",
        "avoided_cost",
        "hours_saved",
        "hourly_value",
        "evidence_reference",
        "measurement_notes",
        "measured_at",
    )
    result = {}
    for key in keep:
        value = row.get(key)
        if isinstance(value, Decimal):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[key] = value
    return result


def _fetch_episode(conn, recommendation_episode_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM recommendation_impact_v
        WHERE recommendation_episode_id=%s
        """,
        (recommendation_episode_id,),
    ).fetchone()
    return dict(row) if row else None


def registrar_estado(
    conn,
    recommendation_episode_id: int,
    *,
    status: str,
    notes: str = "",
) -> None:
    status = str(status or "").upper()
    if status not in ACTION_STATUSES:
        raise ValueError("Estado de recomendación no válido.")

    previous = _fetch_episode(conn, recommendation_episode_id)
    if not previous:
        raise ValueError("Recomendación no encontrada.")

    action_at_sql = "NULL" if status == "PENDIENTE" else "NOW()"
    row = conn.execute(
        f"""
        UPDATE recommendation_episodes
        SET
          action_status=%s,
          action_at={action_at_sql},
          action_notes=%s,
          updated_at=NOW()
        WHERE recommendation_episode_id=%s
        RETURNING *
        """,
        (status, (notes or "").strip()[:4000], recommendation_episode_id),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO recommendation_impact_audit (
          recommendation_episode_id,
          event_type,
          previous_json,
          new_json
        )
        VALUES (%s,'ESTADO',%s::jsonb,%s::jsonb)
        """,
        (
            recommendation_episode_id,
            json.dumps(_snapshot(previous), ensure_ascii=False),
            json.dumps(_snapshot(dict(row)), ensure_ascii=False),
        ),
    )
    conn.commit()


def registrar_resultado(
    conn,
    recommendation_episode_id: int,
    *,
    outcome: str,
    attribution_method: str,
    attribution_confidence: str,
    attributed_revenue: Any = 0,
    attributed_margin: Any = 0,
    avoided_cost: Any = 0,
    hours_saved: Any = 0,
    hourly_value: Any = 0,
    evidence_reference: str = "",
    notes: str = "",
) -> None:
    outcome = str(outcome or "").upper()
    attribution_method = str(attribution_method or "").upper()
    attribution_confidence = str(attribution_confidence or "").upper()

    if outcome not in OUTCOMES:
        raise ValueError("Resultado no válido.")
    if attribution_method not in ATTRIBUTION_METHODS:
        raise ValueError("Método de atribución no válido.")
    if attribution_confidence not in ATTRIBUTION_CONFIDENCE:
        raise ValueError("Confianza de atribución no válida.")

    revenue = normalizar_monto(attributed_revenue)
    margin = normalizar_monto(attributed_margin)
    avoided = normalizar_monto(avoided_cost)
    hours = normalizar_monto(hours_saved)
    hourly = normalizar_monto(hourly_value)

    previous = _fetch_episode(conn, recommendation_episode_id)
    if not previous:
        raise ValueError("Recomendación no encontrada.")

    row = conn.execute(
        """
        UPDATE recommendation_episodes
        SET
          measurement_status='MEDIDO',
          outcome=%s,
          attribution_method=%s,
          attribution_confidence=%s,
          attributed_revenue=%s,
          attributed_margin=%s,
          avoided_cost=%s,
          hours_saved=%s,
          hourly_value=%s,
          evidence_reference=%s,
          measurement_notes=%s,
          measured_at=NOW(),
          updated_at=NOW()
        WHERE recommendation_episode_id=%s
        RETURNING *
        """,
        (
            outcome,
            attribution_method,
            attribution_confidence,
            revenue,
            margin,
            avoided,
            hours,
            hourly,
            (evidence_reference or "").strip()[:2000],
            (notes or "").strip()[:5000],
            recommendation_episode_id,
        ),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO recommendation_impact_audit (
          recommendation_episode_id,
          event_type,
          previous_json,
          new_json
        )
        VALUES (%s,'RESULTADO',%s::jsonb,%s::jsonb)
        """,
        (
            recommendation_episode_id,
            json.dumps(_snapshot(previous), ensure_ascii=False),
            json.dumps(_snapshot(dict(row)), ensure_ascii=False),
        ),
    )
    conn.commit()


def resumen_impacto(conn) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS recomendaciones,
          COUNT(*) FILTER (WHERE active_now) AS activas,
          COUNT(*) FILTER (WHERE action_status='PENDIENTE') AS pendientes,
          COUNT(*) FILTER (WHERE action_status='EJECUTADA') AS ejecutadas,
          COUNT(*) FILTER (WHERE action_status='IGNORADA') AS ignoradas,
          COUNT(*) FILTER (WHERE measurement_status='MEDIDO') AS medidas,
          COUNT(*) FILTER (
            WHERE measurement_status='MEDIDO' AND outcome='POSITIVO'
          ) AS positivas,
          COALESCE(SUM(attributed_revenue) FILTER (
            WHERE measurement_status='MEDIDO'
          ),0) AS attributed_revenue,
          COALESCE(SUM(attributed_margin) FILTER (
            WHERE measurement_status='MEDIDO'
          ),0) AS attributed_margin,
          COALESCE(SUM(avoided_cost) FILTER (
            WHERE measurement_status='MEDIDO'
          ),0) AS avoided_cost,
          COALESCE(SUM(time_value) FILTER (
            WHERE measurement_status='MEDIDO'
          ),0) AS time_value,
          COALESCE(SUM(economic_impact) FILTER (
            WHERE measurement_status='MEDIDO'
          ),0) AS economic_impact
        FROM recommendation_impact_v
        """
    ).fetchone()
    return dict(row) if row else {}


def _status_badge(value: str) -> str:
    value = str(value or "")
    cls = {
        "EJECUTADA": "ok",
        "IGNORADA": "neutral",
        "PENDIENTE": "warn",
        "POSITIVO": "ok",
        "NEGATIVO": "fail",
        "NEUTRO": "neutral",
        "INCIERTO": "warn",
    }.get(value, "neutral")
    return f"<span class='impact-badge {cls}'>{esc(value)}</span>"


IMPACT_CSS = r"""
<style>
.impact-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.impact-kpi{background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:16px}
.impact-kpi .k{font-size:10px;color:#175cd3;font-weight:850;letter-spacing:.05em}
.impact-kpi .v{font-size:26px;font-weight:900;margin-top:6px}
.impact-kpi .n{font-size:11px;color:#667085;margin-top:4px;line-height:1.4}
.impact-badge{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:850;background:#f2f4f7;color:#475467}
.impact-badge.ok{background:#ecfdf3;color:#067647}.impact-badge.warn{background:#fff7ed;color:#b54708}.impact-badge.fail{background:#fff1f0;color:#b42318}
.impact-table-wrap{overflow:auto;background:#fff;border:1px solid #e4e7ec;border-radius:17px;padding:4px 14px 14px;margin-top:14px}
.impact-table a{font-weight:850;color:#175cd3}
.impact-form{background:#fff;border:1px solid #e4e7ec;border-radius:17px;padding:18px;margin-top:14px}
.impact-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.impact-form label{font-size:11px;font-weight:800;color:#475467;display:block;margin-bottom:5px}
.impact-form input,.impact-form select,.impact-form textarea{width:100%;padding:10px;border:1px solid #d0d5dd;border-radius:10px;font:inherit}
.impact-form textarea{min-height:80px;resize:vertical}
.impact-form button{border:0;background:#071b33;color:#fff;padding:10px 14px;border-radius:10px;font-weight:850;cursor:pointer}
.impact-form .full{grid-column:1/-1}
.impact-note{font-size:11px;color:#667085;line-height:1.55}
@media(max-width:900px){.impact-kpis{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.impact-kpis,.impact-form-grid{grid-template-columns:1fr}}
</style>
"""


def render_impacto(conn) -> str:
    summary = resumen_impacto(conn)
    medidas = int(summary.get("medidas") or 0)
    positivas = int(summary.get("positivas") or 0)
    tasa = (positivas / medidas * 100) if medidas else 0

    rows = conn.execute(
        """
        SELECT *
        FROM recommendation_impact_v
        ORDER BY active_now DESC, last_seen_at DESC, recommendation_episode_id DESC
        LIMIT 100
        """
    ).fetchall()

    body_rows = "".join(
        f"""
        <tr>
          <td>#{r['recommendation_episode_id']}</td>
          <td>{'Sí' if r['active_now'] else 'No'}</td>
          <td>{esc(r['priority'])}</td>
          <td><b>{esc(r['title'])}</b><br><span style="color:#667085">{esc(r['category'])}</span></td>
          <td>{_status_badge(r['action_status'])}</td>
          <td>{_status_badge(r['outcome'] or 'SIN MEDIR')}</td>
          <td>{money(r['economic_impact'])}</td>
          <td><a href="/impacto/recomendacion?id={r['recommendation_episode_id']}">Abrir →</a></td>
        </tr>
        """
        for r in rows
    ) or "<tr><td colspan='8'>Todavía no hay recomendaciones registradas. Abre Hoy o Recomendaciones para sincronizarlas.</td></tr>"

    content = f"""
    {IMPACT_CSS}
    <div class="section-title">
      <h2>Impacto de Sportland Smart</h2>
      <span>Recomendación → ejecución → resultado → valor económico</span>
    </div>

    <div class="impact-kpis">
      <div class="impact-kpi"><div class="k">RECOMENDACIONES</div><div class="v">{int(summary.get('recomendaciones') or 0)}</div><div class="n">{int(summary.get('activas') or 0)} activas · {int(summary.get('pendientes') or 0)} pendientes</div></div>
      <div class="impact-kpi"><div class="k">EJECUTADAS</div><div class="v">{int(summary.get('ejecutadas') or 0)}</div><div class="n">{int(summary.get('ignoradas') or 0)} ignoradas</div></div>
      <div class="impact-kpi"><div class="k">RESULTADOS MEDIDOS</div><div class="v">{medidas}</div><div class="n">{tasa:.0f}% con resultado positivo</div></div>
      <div class="impact-kpi"><div class="k">VALOR ECONÓMICO REGISTRADO</div><div class="v">{money(summary.get('economic_impact'))}</div><div class="n">Margen + costo evitado + valor del tiempo</div></div>

      <div class="impact-kpi"><div class="k">VENTAS ATRIBUIDAS</div><div class="v">{money(summary.get('attributed_revenue'))}</div><div class="n">Se muestra aparte para no confundir ventas con utilidad.</div></div>
      <div class="impact-kpi"><div class="k">MARGEN ATRIBUIDO</div><div class="v">{money(summary.get('attributed_margin'))}</div><div class="n">Componente monetario del impacto.</div></div>
      <div class="impact-kpi"><div class="k">COSTOS EVITADOS</div><div class="v">{money(summary.get('avoided_cost'))}</div><div class="n">Errores, compras o gastos evitados documentados.</div></div>
      <div class="impact-kpi"><div class="k">VALOR DEL TIEMPO</div><div class="v">{money(summary.get('time_value'))}</div><div class="n">Horas ahorradas × valor/hora registrado.</div></div>
    </div>

    <div class="callout" style="margin-top:14px">
      <b>Regla de atribución:</b> Sportland Smart no se adjudica una venta por existir una recomendación.
      El valor solo entra a los KPI cuando el administrador registra un resultado y su método/confianza de atribución.
      Las ventas se muestran por separado; el valor económico usa margen, costos evitados y tiempo ahorrado para evitar doble conteo.
    </div>

    <div class="impact-table-wrap">
      <table class="impact-table">
        <thead><tr><th>ID</th><th>Activa</th><th>Prioridad</th><th>Recomendación</th><th>Acción</th><th>Resultado</th><th>Valor</th><th></th></tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """
    return base_page("Impacto", content)


def render_recomendacion_impacto(
    conn,
    recommendation_episode_id: int,
    *,
    csrf_token: str,
) -> str:
    row = _fetch_episode(conn, recommendation_episode_id)
    if not row:
        return base_page(
            "Impacto",
            f"{IMPACT_CSS}<div class='callout'>Recomendación no encontrada. <a href='/impacto'>Volver a Impacto</a></div>",
        )

    economic = row.get("economic_impact") or 0
    time_value = row.get("time_value") or 0

    content = f"""
    {IMPACT_CSS}
    <div class="section-title">
      <h2>Seguimiento de recomendación #{row['recommendation_episode_id']}</h2>
      <span><a href="/impacto" style="color:#175cd3;font-weight:850">← Volver a Impacto</a></span>
    </div>

    <div class="panel full">
      <span class="impact-badge">{esc(row.get('priority'))}</span>
      {_status_badge(row.get('action_status'))}
      {_status_badge(row.get('outcome') or 'SIN MEDIR')}
      <h2 style="margin-top:12px">{esc(row.get('title'))}</h2>
      <div class="hint">{esc(row.get('summary'))}</div>
      <div class="callout">
        <b>Valor económico registrado:</b> {money(economic)} ·
        Ventas atribuidas: {money(row.get('attributed_revenue'))} ·
        Margen: {money(row.get('attributed_margin'))} ·
        Costo evitado: {money(row.get('avoided_cost'))} ·
        Tiempo: {money(time_value)}
      </div>
    </div>

    <form class="impact-form" method="post" action="/impacto/estado">
      <h2>1. ¿Qué se hizo con la recomendación?</h2>
      <input type="hidden" name="csrf" value="{esc(csrf_token)}">
      <input type="hidden" name="id" value="{row['recommendation_episode_id']}">
      <div class="impact-form-grid">
        <div>
          <label>Estado</label>
          <select name="status">
            {''.join(f"<option value='{s}' {'selected' if row.get('action_status')==s else ''}>{s}</option>" for s in ACTION_STATUSES)}
          </select>
        </div>
        <div class="full">
          <label>Nota de ejecución</label>
          <textarea name="notes" placeholder="Ej.: se repusieron 4 pares de talla 27; campaña publicada; se decidió no ejecutar.">{esc(row.get('action_notes') or '')}</textarea>
        </div>
        <div class="full"><button type="submit">Guardar estado</button></div>
      </div>
    </form>

    <form class="impact-form" method="post" action="/impacto/resultado">
      <h2>2. Registrar resultado</h2>
      <div class="impact-note">Registra únicamente valor que puedas defender con evidencia. Si no existe medición suficiente, usa INCIERTO o deja la recomendación sin medir.</div>
      <input type="hidden" name="csrf" value="{esc(csrf_token)}">
      <input type="hidden" name="id" value="{row['recommendation_episode_id']}">
      <div class="impact-form-grid">
        <div>
          <label>Resultado</label>
          <select name="outcome" required>
            {"<option value='' disabled selected>Seleccionar</option>" if not row.get('outcome') else ""}
            {''.join(f"<option value='{s}' {'selected' if row.get('outcome')==s else ''}>{s}</option>" for s in OUTCOMES)}
          </select>
        </div>
        <div>
          <label>Método de atribución</label>
          <select name="attribution_method">
            {''.join(f"<option value='{s}' {'selected' if row.get('attribution_method')==s else ''}>{s}</option>" for s in ATTRIBUTION_METHODS)}
          </select>
        </div>
        <div>
          <label>Confianza de atribución</label>
          <select name="attribution_confidence" required>
            {"<option value='' disabled selected>Seleccionar</option>" if not row.get('attribution_confidence') else ""}
            {''.join(f"<option value='{s}' {'selected' if row.get('attribution_confidence')==s else ''}>{s}</option>" for s in ATTRIBUTION_CONFIDENCE)}
          </select>
        </div>
        <div>
          <label>Ventas atribuidas (MXN)</label>
          <input name="attributed_revenue" type="number" min="0" step="0.01" value="{esc(row.get('attributed_revenue') or 0)}">
        </div>
        <div>
          <label>Margen atribuido (MXN)</label>
          <input name="attributed_margin" type="number" min="0" step="0.01" value="{esc(row.get('attributed_margin') or 0)}">
        </div>
        <div>
          <label>Costos evitados (MXN)</label>
          <input name="avoided_cost" type="number" min="0" step="0.01" value="{esc(row.get('avoided_cost') or 0)}">
        </div>
        <div>
          <label>Horas ahorradas</label>
          <input name="hours_saved" type="number" min="0" step="0.25" value="{esc(row.get('hours_saved') or 0)}">
        </div>
        <div>
          <label>Valor por hora (MXN)</label>
          <input name="hourly_value" type="number" min="0" step="0.01" value="{esc(row.get('hourly_value') or 0)}">
        </div>
        <div class="full">
          <label>Evidencia / referencia</label>
          <input name="evidence_reference" value="{esc(row.get('evidence_reference') or '')}" placeholder="Ej.: pedido #1234, reporte Shopify, factura, captura, URL interna">
        </div>
        <div class="full">
          <label>Notas de medición</label>
          <textarea name="notes" placeholder="Qué cambió después de ejecutar y por qué atribuyes este resultado.">{esc(row.get('measurement_notes') or '')}</textarea>
        </div>
        <div class="full"><button type="submit">Guardar resultado medido</button></div>
      </div>
    </form>
    """
    return base_page("Seguimiento de recomendación", content)
