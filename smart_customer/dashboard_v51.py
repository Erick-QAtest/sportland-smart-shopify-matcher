from __future__ import annotations

from datetime import datetime
import html
import json
from typing import Any
from urllib.parse import quote


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _money(value: Any, currency: str = "MXN") -> str:
    if value in (None, ""):
        return "—"
    try:
        amount = float(value)
        return f"${amount:,.0f} {currency}"
    except (TypeError, ValueError):
        return _esc(value)


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return _esc(value)


def _dt(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.astimezone().strftime("%d %b %Y · %H:%M")
    raw = str(value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y · %H:%M")
    except ValueError:
        return _esc(raw)


def _bar(value: int, max_value: int) -> str:
    width = 0 if max_value <= 0 else max(3, round((value / max_value) * 100))
    return (
        "<div class='bar-track'>"
        f"<div class='bar-fill' style='width:{width}%'></div>"
        "</div>"
    )


BASE_CSS = r"""
:root {
  --navy:#0b1f3a;
  --blue:#175cd3;
  --red:#d92d20;
  --ink:#101828;
  --muted:#667085;
  --line:#e4e7ec;
  --panel:#ffffff;
  --bg:#f4f7fb;
  --good:#067647;
  --warn:#b54708;
  --soft-blue:#eff8ff;
  --soft-red:#fff1f0;
  --soft-green:#ecfdf3;
}
*{box-sizing:border-box}
body{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:var(--bg);color:var(--ink)}
a{color:inherit;text-decoration:none}
.shell{max-width:1440px;margin:0 auto;padding:22px}
.topbar{background:linear-gradient(135deg,var(--navy),#123a68);color:white;border-radius:20px;padding:22px 24px;display:flex;gap:20px;align-items:center;justify-content:space-between;box-shadow:0 10px 30px rgba(11,31,58,.16)}
.brand{display:flex;align-items:center;gap:14px}
.logo{width:44px;height:44px;border-radius:14px;background:white;color:var(--navy);display:grid;place-items:center;font-weight:900;font-size:21px}
.brand h1{font-size:22px;margin:0}
.brand .sub{font-size:12px;opacity:.76;margin-top:3px}
.guardrail{font-size:11px;line-height:1.4;text-align:right;opacity:.8}
.nav{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 20px}
.nav a{background:white;border:1px solid var(--line);padding:10px 13px;border-radius:12px;font-size:13px;font-weight:700;color:#344054}
.nav a.active,.nav a:hover{background:var(--navy);color:white;border-color:var(--navy)}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:0 2px 10px rgba(16,24,40,.04)}
.card{grid-column:span 3;padding:17px}
.card .eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--blue);font-weight:800}
.card .label{font-size:12px;color:var(--muted);margin-top:5px}
.card .value{font-size:26px;font-weight:820;margin-top:7px}
.card .note{font-size:11px;color:#98a2b3;margin-top:4px}
.panel{grid-column:span 6;padding:18px;overflow:hidden}
.panel.full{grid-column:1/-1}
.panel.third{grid-column:span 4}
.panel h2{font-size:16px;margin:0 0 4px}
.panel .hint{font-size:12px;color:var(--muted);margin-bottom:16px}
.metric-row{display:grid;grid-template-columns:100px 1fr 60px;gap:10px;align-items:center;margin:10px 0;font-size:12px}
.metric-row .name{font-weight:700}
.metric-row .n{text-align:right;font-variant-numeric:tabular-nums}
.bar-track{height:9px;background:#eef2f6;border-radius:20px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--blue),#53b1fd);border-radius:20px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{padding:10px 9px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}
th{color:#475467;font-size:11px;text-transform:uppercase;letter-spacing:.02em;background:#fff;position:sticky;top:0}
tbody tr:hover{background:#f9fbfd}
.badge{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:800}
.badge.high,.badge.ok{background:var(--soft-green);color:var(--good)}
.badge.medium{background:#fff7ed;color:var(--warn)}
.badge.low,.badge.signal{background:#f2f4f7;color:#475467}
.badge.hold{background:var(--soft-red);color:var(--red)}
.searchbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
input,select{border:1px solid #d0d5dd;border-radius:10px;padding:10px 11px;background:white;color:#101828;min-height:40px}
input[type=text]{min-width:280px;flex:1}
button,.button{border:0;background:var(--navy);color:white;padding:10px 14px;border-radius:10px;font-weight:750;cursor:pointer;display:inline-block}
.button.secondary{background:white;color:var(--navy);border:1px solid #d0d5dd}
.kv{display:grid;grid-template-columns:150px 1fr;gap:0}
.kv div{padding:9px 0;border-bottom:1px solid #f0f2f5;font-size:12px}
.kv div:nth-child(odd){color:var(--muted)}
.hero-size{display:flex;align-items:end;gap:14px}
.hero-size .size{font-size:58px;font-weight:900;line-height:1}
.hero-size .confidence{padding-bottom:8px}
.callout{background:var(--soft-blue);border:1px solid #b2ddff;border-radius:14px;padding:14px;font-size:12px}
.warning{background:#fffaeb;border-color:#fedf89}
.empty{padding:28px;text-align:center;color:var(--muted);font-size:13px}
.footer{color:#98a2b3;font-size:11px;text-align:center;margin:22px 0 6px}
@media(max-width:980px){
  .card{grid-column:span 6}
  .panel,.panel.third{grid-column:1/-1}
  .guardrail{display:none}
}
@media(max-width:620px){
  .shell{padding:10px}
  .topbar{border-radius:14px}
  .card{grid-column:1/-1}
  .metric-row{grid-template-columns:80px 1fr 48px}
  input[type=text]{min-width:100%}
}
"""


def _nav(active: str) -> str:
    links = [
        ("overview", "/", "Overview"),
        ("customers", "/customers", "Customers"),
        ("sizes", "/sizes", "Tallas"),
        ("brands", "/brands", "Marcas"),
        ("segments", "/segments", "Segmentos"),
        ("opportunities", "/opportunities", "Oportunidades"),
    ]
    return "<div class='nav'>" + "".join(
        f"<a class='{'active' if key == active else ''}' href='{url}'>{label}</a>"
        for key, url, label in links
    ) + "</div>"


def _page(title: str, active: str, content: str, subtitle: str = "") -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · Sportland Smart</title>
<style>{BASE_CSS}</style>
</head>
<body>
<div class="shell">
  <div class="topbar">
    <div class="brand">
      <div class="logo">S</div>
      <div>
        <h1>Sportland Smart — Customer Intelligence</h1>
        <div class="sub">{_esc(subtitle or "CRM + comportamiento de compra + talla habitual")}</div>
      </div>
    </div>
    <div class="guardrail">LOCALHOST · READ-ONLY SHOPIFY<br>PII no se exporta a artifacts · sin contacto automático</div>
  </div>
  {_nav(active)}
  {content}
  <div class="footer">Sportland Smart Customer Intelligence v5.1 · datos leídos desde PostgreSQL local</div>
</div>
</body>
</html>"""


def fetch_overview(conn) -> dict[str, Any]:
    customer = conn.execute(
        """
        SELECT
          COUNT(*) AS customers,
          COUNT(*) FILTER (WHERE shopify_customer_id IS NOT NULL) AS shopify_customers,
          COUNT(*) FILTER (WHERE phone_e164 IS NOT NULL) AS with_phone,
          COUNT(*) FILTER (WHERE email IS NOT NULL) AS with_email,
          COUNT(*) FILTER (WHERE preferred_size IS NOT NULL) AS with_size,
          COUNT(*) FILTER (WHERE size_confidence_band = 'HIGH') AS size_high,
          COUNT(*) FILTER (WHERE size_confidence_band = 'MEDIUM') AS size_medium,
          COUNT(*) FILTER (WHERE size_confidence_band = 'LOW') AS size_low,
          COUNT(*) FILTER (WHERE COALESCE(shopify_orders_count,0) >= 2) AS repeat_buyers,
          COUNT(*) FILTER (WHERE COALESCE(shopify_total_spent,0) >= 3000) AS vip_3000,
          COALESCE(SUM(shopify_total_spent),0) AS lifetime_value
        FROM customers
        """
    ).fetchone()

    purchases = conn.execute(
        """
        SELECT
          COUNT(*) AS purchase_lines,
          COALESCE(SUM(quantity),0) AS units,
          COUNT(DISTINCT customer_id) AS purchasing_customers,
          COUNT(*) FILTER (WHERE size IS NOT NULL) AS lines_with_size,
          MAX(purchased_at) AS latest_purchase
        FROM customer_purchase_items
        WHERE cancelled = FALSE AND quantity > 0
        """
    ).fetchone()

    latest_sync = conn.execute(
        """
        SELECT *
        FROM customer_sync_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()

    opportunity = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE lifecycle_status='OPEN') AS open_opportunities,
          COUNT(*) FILTER (
            WHERE lifecycle_status='OPEN' AND action='CONTACT_CANDIDATE'
          ) AS contact_candidates,
          COUNT(*) FILTER (
            WHERE lifecycle_status='OPEN' AND priority_band='HIGH'
          ) AS high_opportunities
        FROM commercial_opportunities
        """
    ).fetchone()

    sizes = [
        dict(r) for r in conn.execute(
            """
            SELECT preferred_size AS size, COUNT(*) AS customers
            FROM customer_size_profiles
            WHERE preferred_size IS NOT NULL
            GROUP BY preferred_size
            ORDER BY preferred_size::numeric
            """
        ).fetchall()
    ]

    brands = [
        dict(r) for r in conn.execute(
            """
            SELECT brand, COUNT(*) AS profiles
            FROM customer_brand_size_profiles
            GROUP BY brand
            ORDER BY profiles DESC, brand
            LIMIT 12
            """
        ).fetchall()
    ]

    return {
        "customer": dict(customer),
        "purchases": dict(purchases),
        "sync": dict(latest_sync) if latest_sync else None,
        "opportunity": dict(opportunity),
        "sizes": sizes,
        "brands": brands,
    }


def fetch_size_distribution(conn) -> list[dict[str, Any]]:
    return [
        dict(r) for r in conn.execute(
            """
            SELECT
              preferred_size AS size,
              COUNT(*) AS customers,
              COUNT(*) FILTER (WHERE confidence_band='HIGH') AS high,
              COUNT(*) FILTER (WHERE confidence_band='MEDIUM') AS medium,
              COUNT(*) FILTER (WHERE confidence_band='LOW') AS low,
              ROUND(AVG(confidence),4) AS avg_confidence,
              SUM(observation_count) AS observations
            FROM customer_size_profiles
            WHERE preferred_size IS NOT NULL
            GROUP BY preferred_size
            ORDER BY preferred_size::numeric
            """
        ).fetchall()
    ]


def fetch_brand_distribution(conn) -> list[dict[str, Any]]:
    return [
        dict(r) for r in conn.execute(
            """
            SELECT
              brand,
              preferred_size AS size,
              COUNT(*) AS customers,
              SUM(observation_count) AS observations,
              ROUND(AVG(confidence),4) AS avg_confidence
            FROM customer_brand_size_profiles
            WHERE preferred_size IS NOT NULL
            GROUP BY brand, preferred_size
            ORDER BY brand, preferred_size::numeric
            """
        ).fetchall()
    ]


def fetch_segments(conn) -> list[dict[str, Any]]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE COALESCE(shopify_orders_count,0) >= 2) AS repeat_buyers,
          COUNT(*) FILTER (WHERE COALESCE(shopify_total_spent,0) >= 3000) AS vip_3000,
          COUNT(*) FILTER (WHERE preferred_size IS NOT NULL) AS size_known,
          COUNT(*) FILTER (WHERE preferred_size IS NULL) AS size_unknown,
          COUNT(*) FILTER (WHERE size_confidence_band='HIGH') AS size_high,
          COUNT(*) FILTER (WHERE size_confidence_band='MEDIUM') AS size_medium,
          COUNT(*) FILTER (WHERE size_confidence_band='LOW') AS size_low
        FROM customers
        """
    ).fetchone()

    recent = conn.execute(
        """
        SELECT COUNT(DISTINCT customer_id) AS recent_buyers
        FROM customer_purchase_items
        WHERE cancelled=FALSE
          AND quantity > 0
          AND purchased_at >= now() - interval '30 days'
        """
    ).fetchone()

    variable_sizes = conn.execute(
        """
        SELECT COUNT(*) AS variable_size_customers
        FROM customer_size_profiles
        WHERE unique_sizes >= 2
        """
    ).fetchone()

    opportunities = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE lifecycle_status='OPEN' AND action='CONTACT_CANDIDATE'
          ) AS contact_candidates,
          COUNT(*) FILTER (
            WHERE lifecycle_status='OPEN' AND priority_band='HIGH'
          ) AS high_opportunities,
          COUNT(*) FILTER (
            WHERE lifecycle_status='OPEN' AND priority_band='MEDIUM'
          ) AS medium_opportunities
        FROM commercial_opportunities
        """
    ).fetchone()

    segments = [
        ("Clientes recurrentes", row["repeat_buyers"], "2+ pedidos registrados en Shopify", "/customers?segment=repeat"),
        ("Alto valor", row["vip_3000"], "$3,000+ MXN de gasto acumulado", "/customers?segment=vip"),
        ("Talla conocida", row["size_known"], "Perfil de talla disponible", "/customers?segment=size_known"),
        ("Talla HIGH", row["size_high"], "Patrón de talla fuerte y repetido", "/customers?segment=size_high"),
        ("Talla MEDIUM", row["size_medium"], "Patrón útil, todavía no definitivo", "/customers?segment=size_medium"),
        ("Talla variable", variable_sizes["variable_size_customers"], "Ha comprado 2+ tallas distintas", "/customers?segment=variable"),
        ("Compradores 30d", recent["recent_buyers"], "Compra capturada en los últimos 30 días", "/customers?segment=recent"),
        ("Contact candidates", opportunities["contact_candidates"], "Oportunidad abierta y elegible para revisión", "/opportunities"),
        ("Oportunidades HIGH", opportunities["high_opportunities"], "Scoring comercial HIGH", "/opportunities?priority=HIGH"),
        ("Sin talla conocida", row["size_unknown"], "Aún sin compra con talla interpretable", "/customers?segment=size_unknown"),
    ]
    return [
        {"name": name, "count": count, "description": desc, "url": url}
        for name, count, desc, url in segments
    ]


def search_customers(
    conn,
    *,
    q: str = "",
    size: str = "",
    segment: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    q = q.strip()
    size = size.strip()
    segment = segment.strip()

    if q:
        like = f"%{q}%"
        clauses.append(
            """(
              COALESCE(c.first_name,'') ILIKE %s
              OR COALESCE(c.last_name,'') ILIKE %s
              OR COALESCE(c.email,'') ILIKE %s
              OR COALESCE(c.phone_e164,'') ILIKE %s
              OR COALESCE(c.shopify_customer_id,'') ILIKE %s
            )"""
        )
        params.extend([like] * 5)

    if size:
        clauses.append("c.preferred_size = %s")
        params.append(size)

    segment_sql = {
        "repeat": "COALESCE(c.shopify_orders_count,0) >= 2",
        "vip": "COALESCE(c.shopify_total_spent,0) >= 3000",
        "size_known": "c.preferred_size IS NOT NULL",
        "size_unknown": "c.preferred_size IS NULL",
        "size_high": "c.size_confidence_band = 'HIGH'",
        "size_medium": "c.size_confidence_band = 'MEDIUM'",
        "variable": "COALESCE(sp.unique_sizes,0) >= 2",
        "recent": "lp.last_purchase >= now() - interval '30 days'",
    }
    if segment in segment_sql:
        clauses.append(segment_sql[segment])

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
    SELECT
      c.customer_id,
      c.first_name,
      c.last_name,
      c.email,
      c.phone_e164,
      c.shopify_orders_count,
      c.shopify_total_spent,
      c.shopify_currency,
      c.preferred_size,
      c.last_purchase_size,
      c.size_confidence,
      c.size_confidence_band,
      c.size_observation_count,
      sp.unique_sizes,
      lp.last_purchase
    FROM customers c
    LEFT JOIN customer_size_profiles sp
      ON sp.customer_id = c.customer_id
    LEFT JOIN LATERAL (
      SELECT MAX(purchased_at) AS last_purchase
      FROM customer_purchase_items p
      WHERE p.customer_id = c.customer_id
        AND p.cancelled=FALSE
        AND p.quantity > 0
    ) lp ON TRUE
    {where}
    ORDER BY
      c.shopify_total_spent DESC NULLS LAST,
      c.shopify_orders_count DESC NULLS LAST,
      c.customer_id DESC
    LIMIT %s
    """
    params.append(max(1, min(limit, 250)))
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def fetch_customer_360(conn, customer_id: int) -> dict[str, Any] | None:
    customer = conn.execute(
        """
        SELECT c.*, sp.unique_sizes, sp.size_counts,
               sp.first_observed_at, sp.last_observed_at
        FROM customers c
        LEFT JOIN customer_size_profiles sp
          ON sp.customer_id = c.customer_id
        WHERE c.customer_id = %s
        """,
        (customer_id,),
    ).fetchone()
    if not customer:
        return None

    brands = [
        dict(r) for r in conn.execute(
            """
            SELECT *
            FROM customer_brand_size_profiles
            WHERE customer_id = %s
            ORDER BY observation_count DESC, brand
            """,
            (customer_id,),
        ).fetchall()
    ]

    purchases = [
        dict(r) for r in conn.execute(
            """
            SELECT
              shopify_order_name,
              product_title,
              brand,
              sku,
              variant_title,
              size,
              quantity,
              unit_price,
              currency,
              purchased_at,
              cancelled
            FROM customer_purchase_items
            WHERE customer_id = %s
            ORDER BY purchased_at DESC, purchase_item_id DESC
            LIMIT 100
            """,
            (customer_id,),
        ).fetchall()
    ]

    events = [
        dict(r) for r in conn.execute(
            """
            SELECT
              event_type_name,
              detail,
              sku,
              size,
              amount,
              currency,
              channel,
              occurred_at
            FROM customer_events
            WHERE customer_id = %s
            ORDER BY occurred_at DESC NULLS LAST, event_id DESC
            LIMIT 100
            """,
            (customer_id,),
        ).fetchall()
    ]

    intents = [
        dict(r) for r in conn.execute(
            """
            SELECT
              intent_id,
              requested_size,
              smart_sku,
              resolved_sku,
              state,
              match_status,
              match_confidence,
              opened_at,
              last_seen_at,
              resolution
            FROM demand_intents
            WHERE customer_id = %s
            ORDER BY opened_at DESC
            LIMIT 50
            """,
            (customer_id,),
        ).fetchall()
    ]

    opportunities = [
        dict(r) for r in conn.execute(
            """
            SELECT
              opportunity_id,
              action,
              eligible_for_contact,
              source_state,
              reason,
              opportunity_score,
              priority_band,
              lifecycle_status,
              evaluated_at,
              closed_at,
              close_reason
            FROM commercial_opportunities
            WHERE customer_id = %s
            ORDER BY evaluated_at DESC
            LIMIT 50
            """,
            (customer_id,),
        ).fetchall()
    ]

    return {
        "customer": dict(customer),
        "brands": brands,
        "purchases": purchases,
        "events": events,
        "intents": intents,
        "opportunities": opportunities,
    }


def fetch_opportunities(
    conn,
    *,
    priority: str = "",
    limit: int = 150,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    clause = "WHERE co.lifecycle_status='OPEN'"
    if priority in {"HIGH", "MEDIUM", "LOW", "HOLD", "SIGNAL"}:
        clause += " AND co.priority_band=%s"
        params.append(priority)

    params.append(max(1, min(limit, 300)))

    return [
        dict(r) for r in conn.execute(
            f"""
            SELECT
              co.opportunity_id,
              co.customer_id,
              co.action,
              co.eligible_for_contact,
              co.source_state,
              co.reason,
              co.opportunity_score,
              co.priority_band,
              co.evaluated_at,
              c.first_name,
              c.last_name,
              c.preferred_size,
              c.size_confidence_band,
              c.shopify_orders_count,
              c.shopify_total_spent,
              di.requested_size,
              di.resolved_sku,
              di.state AS intent_state
            FROM commercial_opportunities co
            LEFT JOIN customers c
              ON c.customer_id = co.customer_id
            LEFT JOIN demand_intents di
              ON di.intent_id = co.intent_id
            {clause}
            ORDER BY
              CASE co.priority_band
                WHEN 'HIGH' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3
                WHEN 'HOLD' THEN 4
                ELSE 5
              END,
              co.opportunity_score DESC NULLS LAST,
              co.evaluated_at DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    ]


def render_overview(data: dict[str, Any]) -> str:
    c = data["customer"]
    p = data["purchases"]
    s = data.get("sync") or {}
    o = data["opportunity"]

    cards = [
        ("Clientes", c.get("customers", 0), "Shopify + Memory reconciliados", "CRM"),
        ("Con talla", c.get("with_size", 0), "Perfil habitual disponible", "SIZE"),
        ("Recurrentes", c.get("repeat_buyers", 0), "2+ pedidos en Shopify", "VALUE"),
        ("Valor histórico", _money(c.get("lifetime_value")), "Suma de Shopify amountSpent", "LTV"),
        ("Compras capturadas", p.get("purchase_lines", 0), f"{p.get('units',0)} unidades", "PURCHASES"),
        ("Contact candidates", o.get("contact_candidates", 0), "Requieren revisión humana", "GROWTH"),
        ("Talla HIGH", c.get("size_high", 0), "Patrón consistente", "CONFIDENCE"),
        ("Último sync", s.get("status", "—"), f"{s.get('orders_read',0)} pedidos leídos", "SYNC"),
    ]

    card_html = "".join(
        f"""<div class="card">
          <div class="eyebrow">{_esc(src)}</div>
          <div class="label">{_esc(label)}</div>
          <div class="value">{_esc(value)}</div>
          <div class="note">{_esc(note)}</div>
        </div>"""
        for label, value, note, src in cards
    )

    sizes = data["sizes"]
    max_size = max([int(x["customers"]) for x in sizes] or [1])
    size_html = "".join(
        f"""<div class="metric-row">
          <div class="name">{_esc(r["size"])}</div>
          {_bar(int(r["customers"]), max_size)}
          <div class="n">{int(r["customers"])}</div>
        </div>"""
        for r in sizes
    ) or "<div class='empty'>Aún no hay perfiles de talla.</div>"

    brands = data["brands"]
    max_brand = max([int(x["profiles"]) for x in brands] or [1])
    brand_html = "".join(
        f"""<div class="metric-row">
          <div class="name">{_esc(r["brand"])}</div>
          {_bar(int(r["profiles"]), max_brand)}
          <div class="n">{int(r["profiles"])}</div>
        </div>"""
        for r in brands
    ) or "<div class='empty'>Aún no hay perfiles por marca.</div>"

    warning = ""
    if s and int(s.get("orders_read") or 0) < 500:
        warning = """<div class="panel full callout warning">
          <b>Historial todavía parcial.</b>
          La talla habitual mejora conforme Shopify expone más pedidos históricos.
          El dashboard nunca convierte una sola compra en confianza HIGH.
        </div>"""

    content = f"""
    <div class="grid">{card_html}</div>
    <div class="grid" style="margin-top:14px">
      <div class="panel">
        <h2>Distribución de talla habitual</h2>
        <div class="hint">Clientes con una talla preferida inferida desde compras reales.</div>
        {size_html}
      </div>
      <div class="panel">
        <h2>Marcas con más perfiles</h2>
        <div class="hint">Cantidad de perfiles cliente × marca con talla observada.</div>
        {brand_html}
      </div>
      {warning}
    </div>
    """
    return _page("Overview", "overview", content, "Visión ejecutiva del cliente, compra y talla")


def render_sizes(rows: list[dict[str, Any]]) -> str:
    max_value = max([int(r["customers"]) for r in rows] or [1])
    chart = "".join(
        f"""<div class="metric-row">
          <div class="name">{_esc(r["size"])}</div>
          {_bar(int(r["customers"]), max_value)}
          <div class="n">{int(r["customers"])}</div>
        </div>"""
        for r in rows
    )

    body = "".join(
        f"""<tr>
          <td><b>{_esc(r["size"])}</b></td>
          <td>{r["customers"]}</td>
          <td>{r["observations"]}</td>
          <td>{r["high"]}</td>
          <td>{r["medium"]}</td>
          <td>{r["low"]}</td>
          <td>{_pct(r["avg_confidence"])}</td>
          <td><a class="button secondary" href="/customers?size={quote(str(r['size']))}">Ver clientes</a></td>
        </tr>"""
        for r in rows
    ) or "<tr><td colspan='8'>Sin perfiles de talla.</td></tr>"

    content = f"""
    <div class="grid">
      <div class="panel">
        <h2>Tallas habituales</h2>
        <div class="hint">Distribución por talla preferida.</div>
        {chart or "<div class='empty'>Sin datos.</div>"}
      </div>
      <div class="panel">
        <h2>Cómo se interpreta</h2>
        <div class="callout">
          <b>HIGH</b>: varias observaciones y patrón dominante.<br><br>
          <b>MEDIUM</b>: señal útil, todavía no definitiva.<br><br>
          <b>LOW</b>: normalmente una observación o patrón débil.<br><br>
          La talla habitual nunca reemplaza la validación con el cliente.
        </div>
      </div>
      <div class="panel full">
        <h2>Detalle por talla</h2>
        <table>
          <thead><tr><th>Talla</th><th>Clientes</th><th>Observaciones</th><th>HIGH</th><th>MEDIUM</th><th>LOW</th><th>Conf. media</th><th></th></tr></thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </div>
    """
    return _page("Tallas", "sizes", content, "Inteligencia de talla basada en compras reales")


def render_brands(rows: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["brand"]), []).append(row)

    blocks = []
    for brand, items in grouped.items():
        max_value = max(int(x["customers"]) for x in items)
        bars = "".join(
            f"""<div class="metric-row">
              <div class="name">{_esc(x["size"])}</div>
              {_bar(int(x["customers"]), max_value)}
              <div class="n">{int(x["customers"])}</div>
            </div>"""
            for x in items
        )
        total = sum(int(x["customers"]) for x in items)
        blocks.append(
            f"""<div class="panel third">
              <h2>{_esc(brand)}</h2>
              <div class="hint">{total} perfiles cliente × talla</div>
              {bars}
            </div>"""
        )

    content = (
        "<div class='grid'>" + "".join(blocks) + "</div>"
        if blocks
        else "<div class='panel full empty'>Todavía no hay perfiles por marca.</div>"
    )
    return _page("Marcas", "brands", content, "Cómo cambia la talla habitual según la marca")


def render_segments(rows: list[dict[str, Any]]) -> str:
    cards = "".join(
        f"""<a class="card" href="{_esc(r['url'])}">
          <div class="eyebrow">SEGMENT</div>
          <div class="label">{_esc(r['name'])}</div>
          <div class="value">{_esc(r['count'])}</div>
          <div class="note">{_esc(r['description'])}</div>
        </a>"""
        for r in rows
    )
    content = f"""
    <div class="callout" style="margin-bottom:14px">
      Los segmentos son filtros de análisis. No disparan mensajes, campañas ni cambios en Shopify.
    </div>
    <div class="grid">{cards}</div>
    """
    return _page("Segmentos", "segments", content, "Audiencias operativas para análisis y revisión")


def render_customers(
    rows: list[dict[str, Any]],
    *,
    q: str = "",
    size: str = "",
    segment: str = "",
) -> str:
    body = "".join(
        f"""<tr>
          <td><a href="/customer?customer_id={r['customer_id']}"><b>{_esc((r.get('first_name') or '') + ' ' + (r.get('last_name') or '')) or 'Sin nombre'}</b></a></td>
          <td>{_esc(r.get('email') or '—')}<br><span style="color:#98a2b3">{_esc(r.get('phone_e164') or '')}</span></td>
          <td>{_esc(r.get('shopify_orders_count') or 0)}</td>
          <td>{_money(r.get('shopify_total_spent'), r.get('shopify_currency') or 'MXN')}</td>
          <td><b>{_esc(r.get('preferred_size') or '—')}</b></td>
          <td><span class="badge {_esc(str(r.get('size_confidence_band') or 'low').lower())}">{_esc(r.get('size_confidence_band') or '—')}</span><br>{_pct(r.get('size_confidence'))}</td>
          <td>{_dt(r.get('last_purchase'))}</td>
          <td><a class="button secondary" href="/customer?customer_id={r['customer_id']}">360°</a></td>
        </tr>"""
        for r in rows
    ) or "<tr><td colspan='8'>No se encontraron clientes con esos filtros.</td></tr>"

    content = f"""
    <div class="panel full">
      <h2>Buscar clientes</h2>
      <div class="hint">La información personal se muestra solo en este dashboard local.</div>
      <form class="searchbar" method="get" action="/customers">
        <input type="text" name="q" value="{_esc(q)}" placeholder="Nombre, email, teléfono o Shopify ID">
        <input type="text" name="size" value="{_esc(size)}" placeholder="Talla, ej. 27" style="min-width:120px;max-width:150px">
        <input type="hidden" name="segment" value="{_esc(segment)}">
        <button type="submit">Buscar</button>
        <a class="button secondary" href="/customers">Limpiar</a>
      </form>
      <table>
        <thead><tr><th>Cliente</th><th>Contacto</th><th>Pedidos</th><th>Valor</th><th>Talla</th><th>Confianza</th><th>Última compra</th><th></th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """
    return _page("Customers", "customers", content, f"{len(rows)} clientes mostrados · máximo 100 por vista")


def render_customer_360(data: dict[str, Any] | None) -> str:
    if not data:
        return _page(
            "Customer 360",
            "customers",
            "<div class='panel full empty'>Cliente no encontrado.</div>",
        )

    c = data["customer"]
    name = " ".join(
        x for x in [c.get("first_name"), c.get("last_name")] if x
    ) or "Cliente sin nombre"

    counts = c.get("size_counts") or {}
    if isinstance(counts, str):
        try:
            counts = json.loads(counts)
        except Exception:
            counts = {}

    max_count = max([int(v) for v in counts.values()] or [1])
    size_history = "".join(
        f"""<div class="metric-row">
          <div class="name">{_esc(k)}</div>
          {_bar(int(v), max_count)}
          <div class="n">{_esc(v)}</div>
        </div>"""
        for k, v in sorted(counts.items(), key=lambda x: float(x[0]))
    ) or "<div class='empty'>Sin historial interpretable de talla.</div>"

    brand_rows = "".join(
        f"""<tr>
          <td><b>{_esc(r.get('brand'))}</b></td>
          <td>{_esc(r.get('preferred_size') or '—')}</td>
          <td>{_esc(r.get('last_purchase_size') or '—')}</td>
          <td>{_esc(r.get('observation_count') or 0)}</td>
          <td><span class="badge {_esc(str(r.get('confidence_band') or 'low').lower())}">{_esc(r.get('confidence_band') or '—')}</span> {_pct(r.get('confidence'))}</td>
        </tr>"""
        for r in data["brands"]
    ) or "<tr><td colspan='5'>Sin perfil por marca.</td></tr>"

    purchase_rows = "".join(
        f"""<tr>
          <td>{_dt(r.get('purchased_at'))}</td>
          <td>{_esc(r.get('shopify_order_name'))}</td>
          <td><b>{_esc(r.get('product_title'))}</b><br><span style="color:#98a2b3">{_esc(r.get('sku') or '')}</span></td>
          <td>{_esc(r.get('brand') or '—')}</td>
          <td><b>{_esc(r.get('size') or r.get('variant_title') or '—')}</b></td>
          <td>{_esc(r.get('quantity'))}</td>
          <td>{_money(r.get('unit_price'), r.get('currency') or 'MXN')}</td>
        </tr>"""
        for r in data["purchases"]
    ) or "<tr><td colspan='7'>Sin compras importadas.</td></tr>"

    event_rows = "".join(
        f"""<tr>
          <td>{_dt(r.get('occurred_at'))}</td>
          <td><b>{_esc(r.get('event_type_name'))}</b></td>
          <td>{_esc(r.get('detail') or '')}</td>
          <td>{_esc(r.get('sku') or '')}</td>
          <td>{_esc(r.get('size') or '')}</td>
          <td>{_money(r.get('amount'), r.get('currency') or 'MXN')}</td>
        </tr>"""
        for r in data["events"]
    ) or "<tr><td colspan='6'>Sin eventos.</td></tr>"

    intent_rows = "".join(
        f"""<tr>
          <td>{_dt(r.get('opened_at'))}</td>
          <td><b>{_esc(r.get('state'))}</b></td>
          <td>{_esc(r.get('requested_size') or '—')}</td>
          <td>{_esc(r.get('resolved_sku') or r.get('smart_sku') or '—')}</td>
          <td>{_esc(r.get('match_confidence') or '—')}</td>
          <td>{_esc(r.get('resolution') or '')}</td>
        </tr>"""
        for r in data["intents"]
    ) or "<tr><td colspan='6'>Sin intents.</td></tr>"

    opp_rows = "".join(
        f"""<tr>
          <td>{_dt(r.get('evaluated_at'))}</td>
          <td><span class="badge {_esc(str(r.get('priority_band') or 'low').lower())}">{_esc(r.get('priority_band') or '—')}</span></td>
          <td>{_esc(r.get('opportunity_score') or '—')}</td>
          <td><b>{_esc(r.get('action'))}</b></td>
          <td>{_esc(r.get('lifecycle_status'))}</td>
          <td>{_esc(r.get('reason') or '')}</td>
        </tr>"""
        for r in data["opportunities"]
    ) or "<tr><td colspan='6'>Sin oportunidades.</td></tr>"

    content = f"""
    <div class="grid">
      <div class="panel">
        <h2>{_esc(name)}</h2>
        <div class="hint">Customer 360 · ID local {c.get('customer_id')}</div>
        <div class="kv">
          <div>Email</div><div>{_esc(c.get('email') or '—')}</div>
          <div>Teléfono</div><div>{_esc(c.get('phone_e164') or '—')}</div>
          <div>Shopify ID</div><div>{_esc(c.get('shopify_customer_id') or '—')}</div>
          <div>Pedidos</div><div>{_esc(c.get('shopify_orders_count') or 0)}</div>
          <div>Valor acumulado</div><div>{_money(c.get('shopify_total_spent'), c.get('shopify_currency') or 'MXN')}</div>
          <div>Primera señal</div><div>{_dt(c.get('first_seen_at'))}</div>
          <div>Última señal</div><div>{_dt(c.get('last_seen_at'))}</div>
        </div>
      </div>
      <div class="panel">
        <h2>Perfil de talla</h2>
        <div class="hero-size">
          <div class="size">{_esc(c.get('preferred_size') or '—')}</div>
          <div class="confidence">
            <div><span class="badge {_esc(str(c.get('size_confidence_band') or 'low').lower())}">{_esc(c.get('size_confidence_band') or 'SIN PERFIL')}</span></div>
            <div style="font-size:12px;color:#667085;margin-top:6px">Confianza {_pct(c.get('size_confidence'))} · {c.get('size_observation_count') or 0} observaciones</div>
          </div>
        </div>
        <div style="margin-top:18px">{size_history}</div>
      </div>
      <div class="panel full">
        <h2>Talla por marca</h2>
        <table><thead><tr><th>Marca</th><th>Habitual</th><th>Última</th><th>Observaciones</th><th>Confianza</th></tr></thead><tbody>{brand_rows}</tbody></table>
      </div>
      <div class="panel full">
        <h2>Historial de compras</h2>
        <table><thead><tr><th>Fecha</th><th>Orden</th><th>Producto</th><th>Marca</th><th>Talla</th><th>Qty</th><th>Precio</th></tr></thead><tbody>{purchase_rows}</tbody></table>
      </div>
      <div class="panel full">
        <h2>Memory timeline</h2>
        <table><thead><tr><th>Fecha</th><th>Evento</th><th>Detalle</th><th>SKU</th><th>Talla</th><th>Monto</th></tr></thead><tbody>{event_rows}</tbody></table>
      </div>
      <div class="panel full">
        <h2>Demand intents</h2>
        <table><thead><tr><th>Fecha</th><th>Estado</th><th>Talla</th><th>SKU</th><th>Confianza</th><th>Resolución</th></tr></thead><tbody>{intent_rows}</tbody></table>
      </div>
      <div class="panel full">
        <h2>Oportunidades comerciales</h2>
        <table><thead><tr><th>Fecha</th><th>Prioridad</th><th>Score</th><th>Acción</th><th>Estado</th><th>Razón</th></tr></thead><tbody>{opp_rows}</tbody></table>
      </div>
    </div>
    """
    return _page(name, "customers", content, "Customer 360 local · PII visible solo en localhost")


def render_opportunities(rows: list[dict[str, Any]], *, priority: str = "") -> str:
    body = "".join(
        f"""<tr>
          <td><span class="badge {_esc(str(r.get('priority_band') or 'low').lower())}">{_esc(r.get('priority_band') or '—')}</span></td>
          <td>{_esc(r.get('opportunity_score') or '—')}</td>
          <td>{_esc(r.get('action'))}</td>
          <td>{_esc((r.get('first_name') or '') + ' ' + (r.get('last_name') or '')) or 'Sin identidad'}</td>
          <td>{_esc(r.get('preferred_size') or '—')}</td>
          <td>{_esc(r.get('requested_size') or '—')}</td>
          <td>{_esc(r.get('resolved_sku') or '—')}</td>
          <td>{_esc(r.get('reason') or '')}</td>
          <td>{f"<a class='button secondary' href='/customer?customer_id={r['customer_id']}'>360°</a>" if r.get('customer_id') else '—'}</td>
        </tr>"""
        for r in rows
    ) or "<tr><td colspan='9'>No hay oportunidades abiertas con ese filtro.</td></tr>"

    content = f"""
    <div class="callout" style="margin-bottom:14px">
      <b>Guardrail:</b> una oportunidad es una recomendación para revisión. Este dashboard no envía WhatsApp, email ni activa campañas.
    </div>
    <div class="panel full">
      <form class="searchbar" method="get" action="/opportunities">
        <select name="priority">
          <option value="">Todas las prioridades</option>
          {''.join(f"<option value='{x}' {'selected' if priority==x else ''}>{x}</option>" for x in ['HIGH','MEDIUM','LOW','HOLD','SIGNAL'])}
        </select>
        <button type="submit">Filtrar</button>
      </form>
      <table>
        <thead><tr><th>Prioridad</th><th>Score</th><th>Acción</th><th>Cliente</th><th>Talla hab.</th><th>Talla pedida</th><th>SKU</th><th>Razón</th><th></th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """
    return _page("Oportunidades", "opportunities", content, "Scoring comercial + intención + perfil de cliente")
