from __future__ import annotations

from datetime import datetime
import html
import json
import os
from pathlib import Path
from typing import Any

from smart_customer.dashboard_v51 import (
    fetch_brand_distribution,
    fetch_customer_360,
    fetch_opportunities,
    fetch_overview,
    fetch_segments,
    fetch_size_distribution,
    render_brands,
    render_customer_360,
    render_customers,
    render_opportunities,
    render_overview,
    render_segments,
    render_sizes,
    search_customers,
)


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def money(value: Any, currency: str = "MXN") -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.0f} {currency}"
    except (TypeError, ValueError):
        return esc(value)


def pct100(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return esc(value)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


PORTAL_CSS = r"""
:root{
  --navy:#071b33;--navy2:#123a68;--blue:#175cd3;--red:#d92d20;
  --ink:#101828;--muted:#667085;--line:#e4e7ec;--bg:#f3f6fa;
  --panel:#fff;--green:#067647;--amber:#b54708;--shadow:0 8px 30px rgba(16,24,40,.07)
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{text-decoration:none;color:inherit}
.wrap{max-width:1440px;margin:0 auto;padding:22px}
.hero{background:linear-gradient(135deg,var(--navy),var(--navy2));color:#fff;border-radius:22px;padding:25px;box-shadow:0 16px 38px rgba(7,27,51,.18)}
.hero-top{display:flex;align-items:center;justify-content:space-between;gap:20px}
.brand{display:flex;gap:15px;align-items:center}.mark{height:48px;width:48px;border-radius:15px;background:#fff;color:var(--navy);display:grid;place-items:center;font-weight:950;font-size:23px}
h1{font-size:24px;margin:0}.hero p{margin:5px 0 0;color:rgba(255,255,255,.72);font-size:13px}
.health{padding:8px 11px;background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.2);border-radius:999px;font-size:12px;font-weight:800}
.topnav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
.topnav a{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 13px;font-size:12px;font-weight:800;color:#344054}
.topnav a:hover{background:var(--navy);color:#fff;border-color:var(--navy)}
.section-title{display:flex;justify-content:space-between;align-items:end;margin:22px 2px 12px}.section-title h2{font-size:17px;margin:0}.section-title span{font-size:11px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
.kpi{grid-column:span 3;background:#fff;border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 2px 10px rgba(16,24,40,.03)}
.kpi .tag{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--blue);font-weight:850}.kpi .label{font-size:12px;color:var(--muted);margin-top:4px}.kpi .value{font-size:27px;font-weight:850;margin-top:8px}.kpi .note{font-size:11px;color:#98a2b3;margin-top:4px}
.module{grid-column:span 4;background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:var(--shadow);display:flex;flex-direction:column;min-height:210px}
.module .icon{height:40px;width:40px;border-radius:12px;background:#eff8ff;color:var(--blue);display:grid;place-items:center;font-weight:900}
.module h3{margin:14px 0 4px;font-size:17px}.module p{font-size:12px;line-height:1.45;color:var(--muted);margin:0 0 14px}.module .meta{font-size:11px;color:#475467;margin-top:auto;padding-top:12px;border-top:1px solid #f0f2f5}.module .go{margin-top:13px;display:inline-flex;align-items:center;gap:5px;color:var(--blue);font-weight:850;font-size:12px}
.panel{grid-column:span 6;background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;overflow:auto}.panel.full{grid-column:1/-1}.panel h2{font-size:16px;margin:0 0 4px}.hint{font-size:12px;color:var(--muted);margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:10px 9px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}th{font-size:10px;text-transform:uppercase;color:#475467;letter-spacing:.03em}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:850;background:#f2f4f7;color:#475467}.badge.high,.badge.ok,.badge.healthy{background:#ecfdf3;color:#067647}.badge.medium,.badge.warn{background:#fff7ed;color:#b54708}.badge.failed,.badge.fail{background:#fff1f0;color:#b42318}
.callout{background:#eff8ff;border:1px solid #b2ddff;border-radius:15px;padding:14px;font-size:12px;line-height:1.5}
.footer{text-align:center;color:#98a2b3;font-size:11px;margin:25px 0 5px}
@media(max-width:980px){.kpi{grid-column:span 6}.module{grid-column:span 6}.panel{grid-column:1/-1}}
@media(max-width:620px){.wrap{padding:10px}.hero{border-radius:15px}.hero-top{align-items:flex-start;flex-direction:column}.kpi,.module{grid-column:1/-1}}
"""


def base_page(title: str, content: str, *, health: str = "") -> str:
    health_class = str(health or "").lower()
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Sportland Smart</title>
<style>{PORTAL_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="hero-top">
      <div class="brand">
        <div class="mark">S</div>
        <div>
          <h1>Sportland Smart</h1>
          <p>Decisiones · Clientes · Finanzas · Crecimiento · Operaciones</p>
        </div>
      </div>
      <div class="health badge {esc(health_class)}">{esc(health or "PORTAL LOCAL")}</div>
    </div>
  </div>
  <div class="topnav">
    <a href="/">Hoy</a>
    <a href="/registro">Registro del día</a>
    <a href="/recomendaciones">Recomendaciones</a>
    <a href="/impacto">Impacto</a>
    <a href="/customer-intelligence">Clientes</a>
    <a href="/amazon">Amazon</a>
    <a href="/marketing">Marketing</a>
    <a href="/whatsapp-borradores">WhatsApp</a>
    <a href="/finance">Finanzas</a>
    <a href="/demand">Demanda</a>
    <a href="/memory">Memoria</a>
    <a href="/growth">Crecimiento</a>
    <a href="/ops">Operaciones</a>
    {('<a href="/salir">Salir</a>' if str(os.getenv("SPORTLAND_AUTH_ENABLED","false")).lower() in {"1","true","yes","si","sí","on"} else '')}
  </div>
  {content}
  <div class="footer">Sportland Smart Portal v7.1 · impacto medible · acciones automáticas desactivadas</div>
</div>
</body>
</html>"""


def collect_status(conn, project_root: Path) -> dict[str, Any]:
    memory = {}
    customer = {}
    growth = {}
    sync = {}

    try:
        row = conn.execute("SELECT * FROM smart_memory_health_v").fetchone()
        memory = dict(row) if row else {}
    except Exception:
        memory = {}

    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS customers,
              COUNT(*) FILTER (WHERE shopify_customer_id IS NOT NULL) AS shopify_customers,
              COUNT(*) FILTER (WHERE preferred_size IS NOT NULL) AS with_size,
              COUNT(*) FILTER (WHERE size_confidence_band='HIGH') AS size_high,
              COUNT(*) FILTER (WHERE COALESCE(shopify_orders_count,0)>=2) AS repeat_buyers,
              COALESCE(SUM(shopify_total_spent),0) AS lifetime_value
            FROM customers
            """
        ).fetchone()
        customer = dict(row) if row else {}
    except Exception:
        customer = {}

    try:
        row = conn.execute(
            """
            SELECT *
            FROM customer_sync_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        sync = dict(row) if row else {}
    except Exception:
        sync = {}

    try:
        latest = conn.execute(
            """
            SELECT growth_run_id
            FROM growth_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if latest:
            rows = conn.execute(
                """
                SELECT priority_band, COUNT(*) AS n
                FROM growth_actions
                WHERE growth_run_id=%s
                GROUP BY priority_band
                """,
                (latest["growth_run_id"],),
            ).fetchall()
            growth = {str(r["priority_band"]): int(r["n"]) for r in rows}
    except Exception:
        growth = {}

    finance = read_json(project_root / "artifacts" / "financial_snapshot.json")
    ops = read_json(project_root / "artifacts" / "ops_health.json")

    return {
        "memory": memory,
        "customer": customer,
        "customer_sync": sync,
        "growth": growth,
        "finance": finance,
        "ops": ops,
    }


def render_home(status: dict[str, Any]) -> str:
    c = status["customer"]
    m = status["memory"]
    g = status["growth"]
    f = status["finance"]
    o = status["ops"]
    s = status["customer_sync"]

    fk = f.get("kpis") or {}
    fh = f.get("financial_health") or {}
    overall = o.get("overall") or "UNKNOWN"

    kpis = [
        ("Clientes", c.get("customers", 0), f"{c.get('with_size',0)} con talla conocida", "CRM"),
        ("Ventas 30d", money(fk.get("sales_30d")), f"{fk.get('orders_30d',0)} pedidos", "FINANCE"),
        ("Financial health", pct100(fh.get("score")), fh.get("status", "—"), "FINANCE"),
        ("Crecimiento HIGH", g.get("HIGH", 0), f"{g.get('MEDIUM',0)} MEDIUM", "GROWTH"),
        ("Oportunidades abiertas", m.get("open_commercial_opportunities", 0), f"{m.get('contact_candidates',0)} contact candidates", "MEMORY"),
        ("Esperando stock", m.get("waiting_stock", 0), f"{m.get('restock_matches',0)} restock matches", "DEMAND"),
        ("Sincronización de clientes", s.get("status", "—"), f"{s.get('orders_read',0)} orders · {s.get('customers_read',0)} customers", "SYNC"),
        ("Ops", overall, "Backup + daily + memory", "HEALTH"),
    ]

    kpi_html = "".join(
        f"""<div class="kpi">
          <div class="tag">{esc(tag)}</div>
          <div class="label">{esc(label)}</div>
          <div class="value">{esc(value)}</div>
          <div class="note">{esc(note)}</div>
        </div>"""
        for label, value, note, tag in kpis
    )

    modules = [
        ("CI", "Inteligencia de Clientes", "Clientes, historial de compra, talla habitual, talla por marca, segmentos y Customer 360.", "/customer-intelligence",
         f"{c.get('customers',0)} clientes · {c.get('with_size',0)} con talla"),
        ("FI", "Finanzas", "Ventas, caja, obligaciones, deuda, inventario, margen y decisiones financieras.", "/finance",
         f"{fh.get('score','—')} / 100 · {fh.get('status','—')}"),
        ("DE", "Demanda", "Intenciones, tallas solicitadas, waiting stock, restock matches y señales pendientes.", "/demand",
         f"{m.get('demand_intents',0)} intents"),
        ("ME", "Memoria", "Estado de memoria comercial, eventos, oportunidades y última corrida del orchestrator.", "/memory",
         f"{m.get('events',0)} eventos"),
        ("GR", "Crecimiento", "Prioridades de Crecimiento, canales, objetivos y performance observada.", "/growth",
         f"HIGH {g.get('HIGH',0)} · MEDIUM {g.get('MEDIUM',0)}"),
        ("OP", "Salud Operativa", "Daily pipeline, PostgreSQL, backups verificados e iCloud mirror.", "/ops",
         str(overall)),
    ]

    module_html = "".join(
        f"""<a class="module" href="{url}">
          <div class="icon">{esc(icon)}</div>
          <h3>{esc(title)}</h3>
          <p>{esc(desc)}</p>
          <div class="meta">{esc(meta)}</div>
          <div class="go">Abrir →</div>
        </a>"""
        for icon, title, desc, url, meta in modules
    )

    content = f"""
    <div class="section-title"><h2>Estado del negocio</h2><span>Lectura local en vivo + artifacts diarios</span></div>
    <div class="grid">{kpi_html}</div>
    <div class="section-title"><h2>Módulos</h2><span>Un solo punto de entrada</span></div>
    <div class="grid">{module_html}</div>
    <div class="callout" style="margin-top:14px">
      <b>Inicio local:</b> los datos personales del CRM no se publican ni se copian a artifacts.
      Inteligencia de Clientes consulta PostgreSQL directamente. Los dashboards de Finanzas, Crecimiento y Ops se sirven desde sus artifacts locales.
    </div>
    """
    return base_page("Inicio", content, health=str(overall))


def render_memory(conn) -> str:
    health = {}
    latest = None
    states = []
    actions = []
    event_types = []

    try:
        row = conn.execute("SELECT * FROM smart_memory_health_v").fetchone()
        health = dict(row) if row else {}
    except Exception:
        pass

    try:
        row = conn.execute(
            """
            SELECT run_id, started_at, finished_at, status, failed_step
            FROM memory_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        latest = dict(row) if row else None
    except Exception:
        latest = None

    try:
        states = [dict(r) for r in conn.execute(
            """
            SELECT state, COUNT(*) AS n
            FROM demand_intents
            GROUP BY state
            ORDER BY n DESC, state
            """
        ).fetchall()]
    except Exception:
        states = []

    try:
        actions = [dict(r) for r in conn.execute(
            """
            SELECT action, COUNT(*) AS n
            FROM commercial_opportunities
            WHERE lifecycle_status='OPEN'
            GROUP BY action
            ORDER BY n DESC, action
            """
        ).fetchall()]
    except Exception:
        actions = []

    try:
        event_types = [dict(r) for r in conn.execute(
            """
            SELECT event_type_name, COUNT(*) AS n
            FROM customer_events
            GROUP BY event_type_name
            ORDER BY n DESC, event_type_name
            LIMIT 15
            """
        ).fetchall()]
    except Exception:
        event_types = []

    cards = [
        ("Clientes", health.get("customers", 0), "Memoria identities", "MEMORY"),
        ("Events", health.get("events", 0), "Customer + system events", "EVENTS"),
        ("Demanda intents", health.get("demand_intents", 0), f"{health.get('waiting_stock',0)} waiting stock", "INTENTS"),
        ("Oportunidades abiertas", health.get("open_commercial_opportunities", 0), f"{health.get('contact_candidates',0)} candidates", "COMMERCIAL"),
    ]
    card_html = "".join(
        f"<div class='kpi'><div class='tag'>{esc(t)}</div><div class='label'>{esc(a)}</div><div class='value'>{esc(b)}</div><div class='note'>{esc(c)}</div></div>"
        for a,b,c,t in cards
    )

    states_html = "".join(f"<tr><td>{esc(r['state'])}</td><td>{r['n']}</td></tr>" for r in states) or "<tr><td colspan='2'>Sin datos</td></tr>"
    actions_html = "".join(f"<tr><td>{esc(r['action'])}</td><td>{r['n']}</td></tr>" for r in actions) or "<tr><td colspan='2'>Sin datos</td></tr>"
    event_html = "".join(f"<tr><td>{esc(r['event_type_name'])}</td><td>{r['n']}</td></tr>" for r in event_types) or "<tr><td colspan='2'>Sin datos</td></tr>"

    latest_html = "Sin corrida registrada."
    if latest:
        latest_html = (
            f"<b>{esc(latest.get('status'))}</b> · {esc(latest.get('run_id'))}"
            f"<br><span style='color:#667085'>Inicio: {esc(latest.get('started_at'))} · Fin: {esc(latest.get('finished_at'))}</span>"
        )

    content = f"""
    <div class="grid">{card_html}</div>
    <div class="grid" style="margin-top:14px">
      <div class="panel"><h2>Demanda states</h2><div class="hint">Estado actual de intenciones.</div><table>{states_html}</table></div>
      <div class="panel"><h2>Commercial actions</h2><div class="hint">Oportunidades abiertas por recomendación.</div><table>{actions_html}</table></div>
      <div class="panel"><h2>Eventos principales</h2><div class="hint">Tipos de evento con más observaciones.</div><table>{event_html}</table></div>
      <div class="panel"><h2>Última corrida Memoria</h2><div class="callout">{latest_html}</div></div>
    </div>
    """
    return base_page("Memoria", content)


def render_demand(conn) -> str:
    rows = []
    counts = []
    try:
        counts = [dict(r) for r in conn.execute(
            """
            SELECT state, COUNT(*) AS n
            FROM demand_intents
            GROUP BY state
            ORDER BY n DESC, state
            """
        ).fetchall()]
    except Exception:
        counts = []

    try:
        rows = [dict(r) for r in conn.execute(
            """
            SELECT
              di.intent_id,
              di.customer_id,
              di.state,
              di.requested_size,
              di.smart_sku,
              di.resolved_sku,
              di.match_status,
              di.match_confidence,
              di.opened_at,
              di.last_seen_at,
              c.first_name,
              c.last_name,
              c.preferred_size,
              c.size_confidence_band
            FROM demand_intents di
            LEFT JOIN customers c ON c.customer_id=di.customer_id
            ORDER BY
              CASE di.state
                WHEN 'RESTOCK_MATCH' THEN 1
                WHEN 'WAITING_STOCK' THEN 2
                WHEN 'AVAILABLE' THEN 3
                WHEN 'UNRESOLVED' THEN 4
                ELSE 5
              END,
              di.last_seen_at DESC
            LIMIT 150
            """
        ).fetchall()]
    except Exception:
        rows = []

    cards = "".join(
        f"<div class='kpi'><div class='tag'>STATE</div><div class='label'>{esc(r['state'])}</div><div class='value'>{r['n']}</div></div>"
        for r in counts
    ) or "<div class='kpi'><div class='label'>Sin intents</div><div class='value'>0</div></div>"

    body = "".join(
        f"""<tr>
          <td>{esc(r.get('state'))}</td>
          <td>{esc((r.get('first_name') or '') + ' ' + (r.get('last_name') or '')) or '—'}</td>
          <td>{esc(r.get('requested_size') or '—')}</td>
          <td>{esc(r.get('preferred_size') or '—')}</td>
          <td>{esc(r.get('resolved_sku') or r.get('smart_sku') or '—')}</td>
          <td>{esc(r.get('match_confidence') or '—')}</td>
          <td>{esc(r.get('last_seen_at'))}</td>
          <td>{f"<a href='/customer?customer_id={r['customer_id']}' style='color:#175cd3;font-weight:800'>360°</a>" if r.get('customer_id') else '—'}</td>
        </tr>"""
        for r in rows
    ) or "<tr><td colspan='8'>Sin intents registrados.</td></tr>"

    content = f"""
    <div class="grid">{cards}</div>
    <div class="panel full" style="margin-top:14px">
      <h2>Demanda Intelligence</h2>
      <div class="hint">Talla solicitada vs talla habitual + resolución de SKU.</div>
      <table>
        <thead><tr><th>Estado</th><th>Cliente</th><th>Talla pedida</th><th>Talla habitual</th><th>SKU</th><th>Match</th><th>Última señal</th><th></th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """
    return base_page("Demanda", content)


PORTAL_RIBBON = """
<div style="font-family:system-ui,-apple-system,sans-serif;background:#071b33;color:white;padding:10px 14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid rgba(255,255,255,.15)">
  <a href="/" style="color:white;font-weight:900;text-decoration:none">SPORTLAND SMART</a>
  <a href="/customer-intelligence" style="color:#dbeafe;text-decoration:none;font-size:12px">Clientes</a>
  <a href="/finance" style="color:#dbeafe;text-decoration:none;font-size:12px">Finanzas</a>
  <a href="/demand" style="color:#dbeafe;text-decoration:none;font-size:12px">Demanda</a>
  <a href="/memory" style="color:#dbeafe;text-decoration:none;font-size:12px">Memoria</a>
  <a href="/growth" style="color:#dbeafe;text-decoration:none;font-size:12px">Crecimiento</a>
  <a href="/amazon" style="color:#dbeafe;text-decoration:none;font-size:12px">Amazon</a>
  <a href="/marketing" style="color:#dbeafe;text-decoration:none;font-size:12px">Marketing</a>
  <a href="/whatsapp-borradores" style="color:#dbeafe;text-decoration:none;font-size:12px">WhatsApp</a>
  <a href="/ops" style="color:#dbeafe;text-decoration:none;font-size:12px">Operaciones</a>
</div>
"""



def _traducir_html_visible(document: str) -> str:
    cambios = {
        "SPORTLAND SMART — CUSTOMER INTELLIGENCE": "SPORTLAND SMART — INTELIGENCIA DE CLIENTES",
        "Customer Intelligence": "Inteligencia de Clientes",
        "Overview": "Resumen",
        ">Customers<": ">Clientes<",
        "Growth Priority Calibration": "Calibración de Prioridades de Crecimiento",
        "Growth Performance": "Rendimiento de Crecimiento",
        "Financial Pulse": "Pulso Financiero",
        "Ops Health": "Salud Operativa",
        "Customer 360": "Cliente 360°",
    }
    out = document
    for antes, despues in cambios.items():
        out = out.replace(antes, despues)
    return out


def add_portal_ribbon(document: str, *, customer_page: bool = False) -> str:
    doc = _traducir_html_visible(document or "")
    if customer_page:
        doc = doc.replace("href='/'", "href='/customer-intelligence'")
        doc = doc.replace('href="/"', 'href="/customer-intelligence"')
    marker = "<body>"
    if marker in doc:
        return doc.replace(marker, marker + PORTAL_RIBBON, 1)
    marker = "<body "
    idx = doc.find(marker)
    if idx >= 0:
        end = doc.find(">", idx)
        if end >= 0:
            return doc[: end + 1] + PORTAL_RIBBON + doc[end + 1 :]
    return PORTAL_RIBBON + doc


def render_missing_artifact(label: str, path: Path) -> str:
    content = f"""
    <div class="panel full">
      <h2>{esc(label)}</h2>
      <div class="callout">
        Este dashboard todavía no existe en <code>{esc(path)}</code>.<br><br>
        Ejecuta el pipeline correspondiente y vuelve a abrir esta ruta.
      </div>
    </div>
    """
    return base_page(label, content)


def serve_artifact_page(project_root: Path, relative_path: str, label: str) -> str:
    path = project_root / relative_path
    if not path.exists():
        return render_missing_artifact(label, path)
    return add_portal_ribbon(path.read_text(encoding="utf-8"))


def render_customer_route(conn, route: str, query: dict[str, list[str]]) -> str:
    if route == "/customer-intelligence":
        return add_portal_ribbon(render_overview(fetch_overview(conn)), customer_page=True)

    if route == "/sizes":
        return add_portal_ribbon(render_sizes(fetch_size_distribution(conn)), customer_page=True)

    if route == "/brands":
        return add_portal_ribbon(render_brands(fetch_brand_distribution(conn)), customer_page=True)

    if route == "/segments":
        return add_portal_ribbon(render_segments(fetch_segments(conn)), customer_page=True)

    if route == "/customers":
        q = (query.get("q") or [""])[0]
        size = (query.get("size") or [""])[0]
        segment = (query.get("segment") or [""])[0]
        rows = search_customers(conn, q=q, size=size, segment=segment, limit=100)
        return add_portal_ribbon(
            render_customers(rows, q=q, size=size, segment=segment),
            customer_page=True,
        )

    if route == "/customer":
        raw = (query.get("customer_id") or [""])[0]
        try:
            customer_id = int(raw)
        except ValueError:
            return base_page("Customer 360", "<div class='panel full'>customer_id inválido.</div>")
        return add_portal_ribbon(
            render_customer_360(fetch_customer_360(conn, customer_id)),
            customer_page=True,
        )

    if route == "/opportunities":
        priority = (query.get("priority") or [""])[0].upper()
        return add_portal_ribbon(
            render_opportunities(
                fetch_opportunities(conn, priority=priority),
                priority=priority,
            ),
            customer_page=True,
        )

    raise KeyError(route)
