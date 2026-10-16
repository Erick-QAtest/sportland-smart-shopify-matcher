from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Any

from smart_portal.portal_v60 import base_page, collect_status, esc, money


@dataclass(frozen=True)
class Recommendation:
    key: str
    priority: str
    score: int
    confidence: str
    category: str
    title: str
    summary: str
    evidence: tuple[str, ...]
    action_label: str
    action_url: str
    source: tuple[str, ...]


_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "OK": 3}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def collect_decision_context(conn, project_root: Path) -> dict[str, Any]:
    status = collect_status(conn, project_root)

    customer = {}
    purchase = {}
    sync = {}
    opportunity = {}
    demand_groups: list[dict[str, Any]] = []

    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS customers,
              COUNT(*) FILTER (WHERE preferred_size IS NOT NULL) AS with_size,
              COUNT(*) FILTER (WHERE size_confidence_band='HIGH') AS size_high,
              COUNT(*) FILTER (WHERE size_confidence_band='MEDIUM') AS size_medium,
              COUNT(*) FILTER (WHERE COALESCE(shopify_orders_count,0) >= 2) AS repeat_buyers,
              COALESCE(SUM(shopify_orders_count),0) AS known_customer_orders,
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
            SELECT
              COUNT(*) AS purchase_lines,
              COUNT(DISTINCT shopify_order_id) AS captured_orders,
              COUNT(DISTINCT customer_id) AS captured_customers,
              COUNT(*) FILTER (WHERE size IS NOT NULL) AS lines_with_size,
              COUNT(DISTINCT customer_id) FILTER (WHERE size IS NOT NULL) AS customers_with_observed_size,
              MAX(purchased_at) AS latest_purchase
            FROM customer_purchase_items
            WHERE cancelled=FALSE AND quantity > 0
            """
        ).fetchone()
        purchase = dict(row) if row else {}
    except Exception:
        purchase = {}

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
        row = conn.execute(
            """
            SELECT
              COUNT(*) FILTER (
                WHERE lifecycle_status='OPEN'
              ) AS open_opportunities,
              COUNT(*) FILTER (
                WHERE lifecycle_status='OPEN'
                  AND action='CONTACT_CANDIDATE'
              ) AS contact_candidates,
              COUNT(*) FILTER (
                WHERE lifecycle_status='OPEN'
                  AND priority_band='HIGH'
              ) AS high_opportunities,
              MAX(opportunity_score) FILTER (
                WHERE lifecycle_status='OPEN'
              ) AS max_score
            FROM commercial_opportunities
            """
        ).fetchone()
        opportunity = dict(row) if row else {}
    except Exception:
        opportunity = {}

    try:
        demand_groups = [
            dict(r) for r in conn.execute(
                """
                WITH latest_inventory AS (
                  SELECT DISTINCT ON (
                    COALESCE(NULLIF(sku,''), shopify_variant_id)
                  )
                    COALESCE(NULLIF(sku,''), shopify_variant_id) AS inventory_key,
                    sku,
                    shopify_variant_id,
                    inventory_quantity,
                    captured_at
                  FROM inventory_snapshots
                  ORDER BY
                    COALESCE(NULLIF(sku,''), shopify_variant_id),
                    captured_at DESC,
                    snapshot_id DESC
                )
                SELECT
                  COALESCE(
                    NULLIF(di.resolved_sku,''),
                    NULLIF(di.smart_sku,''),
                    di.shopify_variant_id
                  ) AS sku,
                  di.requested_size,
                  COUNT(*) AS signals,
                  COUNT(*) FILTER (WHERE di.state='WAITING_STOCK') AS waiting_stock,
                  COUNT(*) FILTER (WHERE di.state='RESTOCK_MATCH') AS restock_matches,
                  COUNT(DISTINCT di.customer_id) FILTER (
                    WHERE di.customer_id IS NOT NULL
                  ) AS identified_customers,
                  MAX(li.inventory_quantity) AS stock_quantity
                FROM demand_intents di
                LEFT JOIN latest_inventory li
                  ON (
                    li.shopify_variant_id = di.shopify_variant_id
                    OR (
                      NULLIF(di.resolved_sku,'') IS NOT NULL
                      AND li.sku = di.resolved_sku
                    )
                    OR (
                      NULLIF(di.smart_sku,'') IS NOT NULL
                      AND li.sku = di.smart_sku
                    )
                  )
                WHERE di.state IN ('WAITING_STOCK','RESTOCK_MATCH')
                GROUP BY
                  COALESCE(
                    NULLIF(di.resolved_sku,''),
                    NULLIF(di.smart_sku,''),
                    di.shopify_variant_id
                  ),
                  di.requested_size
                ORDER BY
                  restock_matches DESC,
                  signals DESC,
                  identified_customers DESC
                LIMIT 20
                """
            ).fetchall()
        ]
    except Exception:
        demand_groups = []

    finance = _read_json(project_root / "artifacts" / "financial_snapshot.json")
    ops = _read_json(project_root / "artifacts" / "ops_health.json")

    # collect_status already has these, but direct artifact reads make the
    # decision context explicit and independently testable.
    context = {
        "customer": customer,
        "purchase": purchase,
        "sync": sync,
        "opportunity": opportunity,
        "demand_groups": demand_groups,
        "finance": finance or status.get("finance") or {},
        "ops": ops or status.get("ops") or {},
        "growth": status.get("growth") or {},
        "memory": status.get("memory") or {},
    }
    return context


def build_recommendations(context: dict[str, Any]) -> list[Recommendation]:
    recs: list[Recommendation] = []

    customer = context.get("customer") or {}
    purchase = context.get("purchase") or {}
    sync = context.get("sync") or {}
    opportunity = context.get("opportunity") or {}
    finance = context.get("finance") or {}
    ops = context.get("ops") or {}
    growth = context.get("growth") or {}
    memory = context.get("memory") or {}
    demand_groups = context.get("demand_groups") or []

    finance_health = finance.get("financial_health") or {}
    kpis = finance.get("kpis") or {}
    health_score = _num(finance_health.get("score"), 100.0)
    health_status = str(finance_health.get("status") or "UNKNOWN")
    cash_coverage = kpis.get("cash_coverage_ratio")
    projected_gap = kpis.get("projected_cash_gap")

    # 1) Operational incidents override everything else.
    ops_state = str(ops.get("overall") or "UNKNOWN").upper()
    ops_reasons = [str(x) for x in (ops.get("reasons") or []) if x]
    if ops_state == "FAIL":
        recs.append(Recommendation(
            key="ops-fail",
            priority="HIGH",
            score=100,
            confidence="HIGH",
            category="OPS",
            title="Resolver la alerta operativa antes de tomar decisiones comerciales",
            summary="El sistema reporta un fallo operativo. Antes de actuar sobre clientes, inventario o Growth, conviene restaurar la confiabilidad del pipeline.",
            evidence=tuple(ops_reasons[:4] or ("Ops Health reporta FAIL.",)),
            action_label="Abrir Ops Health",
            action_url="/ops",
            source=("Ops Health",),
        ))
    elif ops_state == "WARN":
        recs.append(Recommendation(
            key="ops-warn",
            priority="MEDIUM",
            score=78,
            confidence="HIGH",
            category="OPS",
            title="Revisar las advertencias operativas",
            summary="El sistema está disponible, pero existe al menos una condición que merece revisión antes de depender de la información como si fuera completamente fresca.",
            evidence=tuple(ops_reasons[:4] or ("Ops Health reporta WARN.",)),
            action_label="Revisar Ops",
            action_url="/ops",
            source=("Ops Health",),
        ))

    # 2) Finance constrains inventory recommendations.
    if health_score < 50:
        evidence = [
            f"Financial Health: {health_score:.1f}/100 ({health_status}).",
        ]
        if cash_coverage is not None:
            evidence.append(f"Cobertura de caja: {_num(cash_coverage):.2f}x.")
        if projected_gap is not None:
            evidence.append(f"Brecha de caja proyectada: {money(projected_gap)}.")
        recs.append(Recommendation(
            key="finance-protect-liquidity",
            priority="HIGH",
            score=95,
            confidence="HIGH",
            category="FINANCE",
            title="Proteger liquidez y evitar compras amplias sin priorización",
            summary="La salud financiera está en zona restrictiva. Cualquier reposición debería concentrarse en SKUs respaldados por demanda, rotación y margen, no en compras generales.",
            evidence=tuple(evidence),
            action_label="Abrir Finance",
            action_url="/finance",
            source=("Finance",),
        ))
    elif health_score < 65:
        recs.append(Recommendation(
            key="finance-selective-buying",
            priority="MEDIUM",
            score=72,
            confidence="HIGH",
            category="FINANCE",
            title="Mantener compras selectivas",
            summary="La salud financiera no está en zona crítica, pero todavía recomienda disciplina de inventario y priorización por retorno.",
            evidence=(
                f"Financial Health: {health_score:.1f}/100 ({health_status}).",
            ),
            action_label="Revisar Finance",
            action_url="/finance",
            source=("Finance",),
        ))

    # 3) Demand + inventory.
    for index, row in enumerate(demand_groups[:5]):
        signals = _int(row.get("signals"))
        waiting = _int(row.get("waiting_stock"))
        restock = _int(row.get("restock_matches"))
        identified = _int(row.get("identified_customers"))
        stock_raw = row.get("stock_quantity")
        stock = None if stock_raw is None else _int(stock_raw)
        sku = str(row.get("sku") or "SKU sin resolver")
        size = str(row.get("requested_size") or "sin talla")

        if signals <= 0:
            continue

        constrained = stock is not None and stock <= signals
        strong = restock > 0 or (signals >= 2 and constrained)
        if not strong and signals < 2:
            continue

        finance_limited = health_score < 50
        score = 92 if restock > 0 else (86 if constrained else 76)
        priority = "HIGH" if score >= 85 else "MEDIUM"
        confidence = "HIGH" if stock is not None and signals >= 2 else "MEDIUM"

        if finance_limited:
            title = f"Revisar reposición selectiva de {sku} · talla {size}"
            summary = "Existe una señal de demanda real, pero Finance recomienda evitar compras amplias. Revisa una reposición puntual respaldada por el número de clientes y el stock."
        else:
            title = f"Revisar reposición de {sku} · talla {size}"
            summary = "La demanda observada y el inventario justifican revisar una reposición o disponibilidad de esta combinación SKU/talla."

        evidence = [
            f"{signals} señales activas de demanda.",
            f"{waiting} WAITING_STOCK y {restock} RESTOCK_MATCH.",
            f"{identified} clientes identificados.",
        ]
        evidence.append(
            f"Stock más reciente: {stock} unidades."
            if stock is not None
            else "Stock reciente no pudo resolverse para esta señal."
        )
        if finance_limited:
            evidence.append(f"Financial Health: {health_score:.1f}/100.")

        recs.append(Recommendation(
            key=f"demand-{index}-{sku}-{size}",
            priority=priority,
            score=score,
            confidence=confidence,
            category="DEMAND",
            title=title,
            summary=summary,
            evidence=tuple(evidence),
            action_label="Abrir Demand",
            action_url="/demand",
            source=("Demand", "Inventory", "Finance") if finance_limited else ("Demand", "Inventory"),
        ))

    # 4) Commercial opportunities already passed through Memory gate/scoring.
    contact_candidates = _int(opportunity.get("contact_candidates"))
    high_opportunities = _int(opportunity.get("high_opportunities"))
    max_opp_score = opportunity.get("max_score")
    if contact_candidates > 0:
        priority = "HIGH" if high_opportunities > 0 else "MEDIUM"
        score = 90 if high_opportunities > 0 else 80
        evidence = [
            f"{contact_candidates} CONTACT_CANDIDATE abiertos.",
            f"{high_opportunities} oportunidades con prioridad HIGH.",
        ]
        if max_opp_score is not None:
            evidence.append(f"Score comercial máximo: {_num(max_opp_score):.1f}.")
        recs.append(Recommendation(
            key="commercial-review-candidates",
            priority=priority,
            score=score,
            confidence="HIGH",
            category="CUSTOMER",
            title="Revisar clientes con oportunidad comercial activa",
            summary="Memory ya encontró clientes cuya intención y estado cumplen el gate comercial. La siguiente acción sigue siendo revisión humana, no contacto automático.",
            evidence=tuple(evidence),
            action_label="Ver oportunidades",
            action_url="/opportunities",
            source=("Memory", "Customer Intelligence",),
        ))

    # 5) Growth: surface already-calibrated actions.
    growth_high = _int(growth.get("HIGH"))
    growth_medium = _int(growth.get("MEDIUM"))
    if growth_high > 0:
        recs.append(Recommendation(
            key="growth-high-review",
            priority="MEDIUM",
            score=79,
            confidence="HIGH",
            category="GROWTH",
            title="Revisar las acciones HIGH de Growth",
            summary="Growth ya priorizó acciones para revisión. Conviene resolver primero las HIGH y luego las MEDIUM, sin activar automáticamente campañas.",
            evidence=(
                f"{growth_high} acciones HIGH.",
                f"{growth_medium} acciones MEDIUM.",
            ),
            action_label="Abrir Growth",
            action_url="/growth",
            source=("Growth",),
        ))

    # 6) Data coverage: historical Shopify access matters for normal size.
    customers = _int(customer.get("customers"))
    with_size = _int(customer.get("with_size"))
    known_orders = _int(customer.get("known_customer_orders"))
    captured_orders = _int(purchase.get("captured_orders"))
    size_coverage = (with_size / customers) if customers else None
    order_capture = (
        captured_orders / known_orders
        if known_orders > 0
        else None
    )

    partial_history = (
        (size_coverage is not None and size_coverage < 0.05)
        or (order_capture is not None and order_capture < 0.35)
    )

    if partial_history:
        evidence = []
        if customers:
            evidence.append(
                f"{with_size} de {customers} clientes tienen talla habitual ({_pct(size_coverage)})."
            )
        if known_orders > 0:
            evidence.append(
                f"{captured_orders} pedidos capturados frente a {known_orders} pedidos acumulados en perfiles Shopify ({_pct(order_capture)})."
            )
        if sync:
            evidence.append(
                f"Último Customer Sync: {sync.get('status','—')} · {sync.get('orders_read',0)} pedidos leídos."
            )

        recs.append(Recommendation(
            key="data-complete-order-history",
            priority="MEDIUM",
            score=77,
            confidence="HIGH",
            category="DATA",
            title="Completar el historial de pedidos para mejorar la talla habitual",
            summary="La cobertura de compras históricas todavía es limitada. Antes de usar talla habitual como una señal fuerte a gran escala, conviene ampliar el historial accesible de Shopify.",
            evidence=tuple(evidence or ("Cobertura histórica insuficiente.",)),
            action_label="Abrir Customer Intelligence",
            action_url="/customer-intelligence",
            source=("Shopify", "Customer Intelligence",),
        ))

    # 7) If there is no action-worthy signal, explicitly say so.
    if not recs:
        recs.append(Recommendation(
            key="all-clear",
            priority="OK",
            score=0,
            confidence="HIGH",
            category="SYSTEM",
            title="No hay una acción prioritaria respaldada por los datos actuales",
            summary="Los módulos revisados no muestran una condición suficientemente fuerte para recomendar una acción inmediata.",
            evidence=("El Decision Center no encontró reglas activas de prioridad HIGH o MEDIUM.",),
            action_label="Ver estado del negocio",
            action_url="/",
            source=("Decision Center",),
        ))

    recs.sort(
        key=lambda r: (
            _PRIORITY_ORDER.get(r.priority, 9),
            -r.score,
            r.category,
            r.title,
        )
    )
    return recs


def recommendations_as_dicts(recs: list[Recommendation]) -> list[dict[str, Any]]:
    return [asdict(r) for r in recs]


def _priority_badge(priority: str) -> str:
    klass = {
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
        "OK": "ok",
    }.get(priority, "")
    label = {
        "HIGH": "ALTA",
        "MEDIUM": "MEDIA",
        "LOW": "BAJA",
        "OK": "OK",
    }.get(priority, priority)
    return f"<span class='decision-badge {klass}'>{esc(label)}</span>"


def _confidence_badge(confidence: str) -> str:
    klass = {
        "HIGH": "high",
        "MEDIUM": "medium",
        "LOW": "low",
    }.get(confidence, "")
    label = {
        "HIGH": "alta",
        "MEDIUM": "media",
        "LOW": "baja",
    }.get(confidence, confidence)
    return f"<span class='decision-confidence {klass}'>Confianza {esc(label)}</span>"


DECISION_CSS = r"""
<style>
.today-hero{background:linear-gradient(135deg,#ffffff,#f8fbff);border:1px solid #dbe7f5;border-radius:18px;padding:20px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.today-hero .big{font-size:30px;font-weight:900;letter-spacing:-.02em}.today-hero .small{font-size:12px;color:#667085;margin-top:5px}
.decision-list{display:grid;gap:12px}
.decision-card{background:#fff;border:1px solid #e4e7ec;border-radius:17px;padding:17px;display:grid;grid-template-columns:78px 1fr auto;gap:15px;align-items:start;box-shadow:0 3px 14px rgba(16,24,40,.04)}
.decision-rank{font-size:29px;font-weight:900;color:#d0d5dd}
.decision-meta{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:7px}
.decision-badge,.decision-confidence,.decision-source{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:10px;font-weight:850}
.decision-badge.high{background:#fff1f0;color:#b42318}.decision-badge.medium{background:#fff7ed;color:#b54708}.decision-badge.low{background:#f2f4f7;color:#475467}.decision-badge.ok{background:#ecfdf3;color:#067647}
.decision-confidence{background:#f2f4f7;color:#475467}.decision-confidence.high{background:#eff8ff;color:#175cd3}
.decision-source{background:#f8fafc;color:#667085;border:1px solid #e4e7ec}
.decision-title{font-size:16px;font-weight:850;margin:0 0 5px}.decision-summary{font-size:12px;color:#667085;line-height:1.5;margin-bottom:10px}
.decision-evidence{margin:0;padding-left:18px;color:#475467;font-size:11px;line-height:1.55}.decision-actions{align-self:center;display:flex;flex-direction:column;gap:7px}.decision-action{white-space:nowrap;background:#071b33;color:#fff;padding:10px 13px;border-radius:10px;font-size:11px;font-weight:850;text-align:center}.decision-action.secondary{background:#eff8ff;color:#175cd3;border:1px solid #b2ddff}
.decision-score{font-size:11px;color:#98a2b3;margin-top:6px}
.decision-section-title{display:flex;justify-content:space-between;align-items:end;margin:20px 2px 10px}.decision-section-title h2{font-size:17px;margin:0}.decision-section-title span{font-size:11px;color:#667085}
@media(max-width:760px){.decision-card{grid-template-columns:45px 1fr}.decision-actions{grid-column:2;justify-self:start;align-items:flex-start}.today-hero{align-items:flex-start;flex-direction:column}}
</style>
"""


def render_recommendation_cards(
    recommendations: list[Recommendation],
    *,
    limit: int | None = None,
    tracking: dict[str, dict[str, Any]] | None = None,
) -> str:
    items = recommendations if limit is None else recommendations[:limit]
    cards = []

    tracking = tracking or {}

    for idx, rec in enumerate(items, start=1):
        evidence = "".join(
            f"<li>{esc(item)}</li>" for item in rec.evidence
        )
        sources = "".join(
            f"<span class='decision-source'>{esc(source)}</span>"
            for source in rec.source
        )
        track = tracking.get(rec.key) or {}
        tracking_link = ""
        if track.get("recommendation_episode_id"):
            status = str(track.get("action_status") or "PENDIENTE").lower()
            tracking_link = (
                f"<a class='decision-action secondary' "
                f"href='/impacto/recomendacion?id={int(track['recommendation_episode_id'])}'>"
                f"Seguimiento · {esc(status)} →</a>"
            )
        cards.append(
            f"""
            <div class="decision-card">
              <div class="decision-rank">{idx:02d}</div>
              <div>
                <div class="decision-meta">
                  {_priority_badge(rec.priority)}
                  {_confidence_badge(rec.confidence)}
                  <span class="decision-source">{esc(rec.category)}</span>
                  {sources}
                </div>
                <div class="decision-title">{esc(rec.title)}</div>
                <div class="decision-summary">{esc(rec.summary)}</div>
                <ul class="decision-evidence">{evidence}</ul>
                <div class="decision-score">Puntaje de decisión {rec.score}/100 · regla determinística y explicable</div>
              </div>
              <div class="decision-actions">
                <a class="decision-action" href="{esc(rec.action_url)}">{esc(rec.action_label)} →</a>
                {tracking_link}
              </div>
            </div>
            """
        )

    return DECISION_CSS + "<div class='decision-list'>" + "".join(cards) + "</div>"


def render_today_home(
    conn,
    project_root: Path,
    status: dict[str, Any] | None = None,
) -> str:
    status = status or collect_status(conn, project_root)
    context = collect_decision_context(conn, project_root)
    recommendations = build_recommendations(context)

    actionable = [
        r for r in recommendations if r.priority in {"HIGH", "MEDIUM"}
    ]
    high = sum(1 for r in recommendations if r.priority == "HIGH")
    medium = sum(1 for r in recommendations if r.priority == "MEDIUM")

    if high:
        headline = f"{high} prioridad{'es' if high != 1 else ''} HIGH"
        sub = f"{medium} MEDIUM · revisar antes de ejecutar acciones"
    elif medium:
        headline = f"{medium} prioridad{'es' if medium != 1 else ''} MEDIUM"
        sub = "No hay una señal HIGH en este momento"
    else:
        headline = "Sin acciones urgentes"
        sub = "El sistema no detectó una señal suficientemente fuerte"

    cards = render_recommendation_cards(recommendations, limit=5)

    # Keep the original business modules below the Decision Center by using
    # the existing status collector's values, but without nesting a second HTML page.
    c = status.get("customer") or {}
    m = status.get("memory") or {}
    g = status.get("growth") or {}
    f = status.get("finance") or {}
    o = status.get("ops") or {}
    s = status.get("customer_sync") or {}
    fk = f.get("kpis") or {}
    fh = f.get("financial_health") or {}
    overall = o.get("overall") or "UNKNOWN"

    kpis = [
        ("Customers", c.get("customers", 0), f"{c.get('with_size',0)} con talla conocida", "CRM"),
        ("Ventas 30d", money(fk.get("sales_30d")), f"{fk.get('orders_30d',0)} pedidos", "FINANCE"),
        ("Financial health", fh.get("score", "—"), fh.get("status", "—"), "FINANCE"),
        ("Growth HIGH", g.get("HIGH", 0), f"{g.get('MEDIUM',0)} MEDIUM", "GROWTH"),
        ("Open opportunities", m.get("open_commercial_opportunities", 0), f"{m.get('contact_candidates',0)} candidates", "MEMORY"),
        ("Waiting stock", m.get("waiting_stock", 0), f"{m.get('restock_matches',0)} restock matches", "DEMAND"),
        ("Customer sync", s.get("status", "—"), f"{s.get('orders_read',0)} orders · {s.get('customers_read',0)} customers", "SYNC"),
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
        ("CI", "Customer Intelligence", "Clientes, historial de compra, talla habitual, talla por marca, segmentos y Customer 360.", "/customer-intelligence", f"{c.get('customers',0)} clientes · {c.get('with_size',0)} con talla"),
        ("FI", "Finance", "Ventas, caja, obligaciones, deuda, inventario, margen y decisiones financieras.", "/finance", f"{fh.get('score','—')} / 100 · {fh.get('status','—')}"),
        ("DE", "Demand", "Intenciones, tallas solicitadas, waiting stock, restock matches y señales pendientes.", "/demand", f"{m.get('demand_intents',0)} intents"),
        ("ME", "Memory", "Estado de memoria comercial, eventos, oportunidades y última corrida del orchestrator.", "/memory", f"{m.get('events',0)} eventos"),
        ("GR", "Growth", "Prioridades de Growth, canales, objetivos y performance observada.", "/growth", f"HIGH {g.get('HIGH',0)} · MEDIUM {g.get('MEDIUM',0)}"),
        ("OP", "Ops Health", "Daily pipeline, PostgreSQL, backups verificados e iCloud mirror.", "/ops", str(overall)),
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
    {DECISION_CSS}
    <div class="today-hero">
      <div>
        <div style="font-size:11px;font-weight:850;color:#175cd3;text-transform:uppercase;letter-spacing:.08em">TODAY · DECISION CENTER</div>
        <div class="big">{esc(headline)}</div>
        <div class="small">{esc(sub)}</div>
      </div>
      <a class="decision-action" href="/recommendations">Ver todas las recomendaciones →</a>
    </div>

    <div class="decision-section-title">
      <h2>Qué necesita atención hoy</h2>
      <span>{len(actionable)} acciones HIGH/MEDIUM · ninguna se ejecuta automáticamente</span>
    </div>
    {cards}

    <div class="section-title"><h2>Estado del negocio</h2><span>Contexto para decidir</span></div>
    <div class="grid">{kpi_html}</div>

    <div class="section-title"><h2>Módulos</h2><span>Profundiza en la evidencia</span></div>
    <div class="grid">{module_html}</div>

    <div class="callout" style="margin-top:14px">
      <b>Cómo funciona:</b> las recomendaciones son reglas determinísticas sobre datos de Finance, Demand, Customer Intelligence, Memory, Growth y Ops.
      Cada recomendación muestra su evidencia y confianza. No compra inventario, no contacta clientes y no activa campañas.
    </div>
    """

    return base_page("Today", content, health=str(overall))


def render_recommendations_page(conn, project_root: Path) -> str:
    context = collect_decision_context(conn, project_root)
    recs = build_recommendations(context)

    high = sum(1 for r in recs if r.priority == "HIGH")
    medium = sum(1 for r in recs if r.priority == "MEDIUM")
    low = sum(1 for r in recs if r.priority == "LOW")
    ok = sum(1 for r in recs if r.priority == "OK")

    summary = f"""
    {DECISION_CSS}
    <div class="grid">
      <div class="kpi"><div class="tag">HIGH</div><div class="label">Atención prioritaria</div><div class="value">{high}</div></div>
      <div class="kpi"><div class="tag">MEDIUM</div><div class="label">Revisar después</div><div class="value">{medium}</div></div>
      <div class="kpi"><div class="tag">LOW</div><div class="label">Señales débiles</div><div class="value">{low}</div></div>
      <div class="kpi"><div class="tag">OK</div><div class="label">Sin acción</div><div class="value">{ok}</div></div>
    </div>
    <div class="decision-section-title"><h2>Decision Center</h2><span>Ordenado por prioridad y score</span></div>
    {render_recommendation_cards(recs)}
    <div class="callout" style="margin-top:14px">
      <b>Guardrail:</b> Decision Center recomienda; no ejecuta. Las decisiones comerciales siguen requiriendo revisión humana.
    </div>
    """
    ops = context.get("ops") or {}
    return base_page(
        "Recomendaciones",
        summary,
        health=str(ops.get("overall") or "LOCAL"),
    )
