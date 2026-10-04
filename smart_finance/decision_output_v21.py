from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _csv_value(v: Any) -> Any:
    if isinstance(v, (list, dict, tuple, set)):
        return json.dumps(list(v) if isinstance(v, set) else v, ensure_ascii=False)
    return v


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("status\nempty\n", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: _csv_value(v) for k, v in r.items()})


def _money(v: Any) -> str:
    if v in (None, ""):
        return "—"
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return html.escape(str(v))


def _pct(v: Any) -> str:
    if v in (None, ""):
        return "—"
    try:
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return html.escape(str(v))


def write_dashboard(path: Path, plan: dict[str, Any], decisions: list[dict[str, Any]], products: list[dict[str, Any]]) -> None:
    h = plan.get("health") or {}
    l = plan.get("liquidity") or {}
    d = plan.get("demand") or {}
    s = plan.get("summary") or {}
    cards = [
        ("Health", f"{h.get('score','—')}/100", str(h.get("status") or "UNKNOWN")),
        ("Caja", _money(l.get("cash_available")), f"Cobertura {float(l.get('cash_coverage_ratio') or 0):.2f}x"),
        ("Eventos Smart", str(d.get("total_events", 0)), f"Confianza {d.get('data_confidence','LOW')}"),
        ("Demanda→caja", str(s.get("sell_now", 0)), "SKU con stock"),
        ("Liquidar variante", str(s.get("liquidate_variant", 0)), "sin castigar todo el modelo"),
        ("Liquidar producto", str(s.get("liquidate_product_count", 0)), "requiere cobertura Smart suficiente"),
        ("Capital candidato", _money(s.get("liquidation_capital_at_cost")), "a costo"),
        ("Caja potencial", _money(s.get("liquidation_recoverable_cash_est")), "estimada, no garantizada"),
    ]
    cards_html = "".join(
        f"<div class='card'><div class='label'>{html.escape(a)}</div><div class='value'>{html.escape(b)}</div><div class='note'>{html.escape(c)}</div></div>"
        for a,b,c in cards
    )
    pri_html = "".join(
        f"<div class='priority {str(x.get('priority','P2')).lower()}'><b>{html.escape(str(x.get('priority')))} · {html.escape(str(x.get('action')))}</b><div>{html.escape(str(x.get('reason')))}</div></div>"
        for x in plan.get("priorities", [])
    ) or "<div>Sin prioridades.</div>"

    product_rows = "".join(
        "<tr>"
        f"<td><b>{html.escape(str(r.get('product_action')))}</b></td>"
        f"<td>{html.escape(str(r.get('product_title') or r.get('product_key')))}</td>"
        f"<td>{r.get('stock_units',0)}</td><td>{r.get('units_sold_30d',0)}</td><td>{r.get('units_sold_prev_30d',0)}</td>"
        f"<td>{r.get('product_demand_score',0)}</td><td>{html.escape(str(r.get('demand_data_confidence')))}</td>"
        f"<td>{float(r.get('slow_variant_share') or 0)*100:.0f}%</td><td>{_money(r.get('capital_at_cost'))}</td>"
        f"<td>{html.escape(str(r.get('reason') or ''))}</td></tr>"
        for r in products[:80]
    ) or "<tr><td colspan='10'>Sin productos.</td></tr>"

    decision_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('priority')))}</td><td><b>{html.escape(str(r.get('action')))}</b></td>"
        f"<td>{html.escape(str(r.get('decision_scope')))}</td><td>{html.escape(str(r.get('sku')))}</td>"
        f"<td>{html.escape(str(r.get('product_title') or ''))}</td><td>{r.get('inventory_quantity',0)}</td>"
        f"<td>{r.get('units_sold_30d',0)}</td><td>{r.get('demand_score',0)}</td><td>{html.escape(str(r.get('demand_strength')))}</td>"
        f"<td>{r.get('product_demand_score',0)}</td><td>{_money(r.get('recommended_price'))}</td><td>{_pct(r.get('recommended_discount_pct'))}</td>"
        f"<td>{_money(r.get('price_floor'))}</td><td>{_money(r.get('recoverable_cash_est'))}</td>"
        f"<td>{html.escape(str(r.get('reason') or ''))}<br><span class='guard'>{html.escape(str(r.get('guardrail') or ''))}</span></td></tr>"
        for r in decisions[:180]
    ) or "<tr><td colspan='15'>Sin decisiones.</td></tr>"

    doc = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sportland Smart — Demand Intelligence 2.1</title><style>
*{{box-sizing:border-box}}body{{font-family:Inter,system-ui,-apple-system,sans-serif;margin:0;background:#0b0f0d;color:#eef3ef}}main{{max-width:1500px;margin:auto;padding:28px}}h1{{margin:0 0 6px}}.sub{{color:#9aa6a0;margin-bottom:22px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}.card,section{{background:#141b18;border:1px solid #27332e;border-radius:14px;padding:16px}}.label{{font-size:12px;color:#a3ada8;text-transform:uppercase}}.value{{font-size:25px;font-weight:800;margin:7px 0}}.note{{font-size:12px;color:#7f8c86}}section{{margin-top:20px;overflow:auto}}.priority{{border-left:4px solid #65736c;padding:10px 12px;margin:8px 0;background:#101613;border-radius:8px}}.priority.p0{{border-left-color:#ff5b5b}}.priority.p1{{border-left-color:#f5b942}}.priority.p2{{border-left-color:#63a7ff}}table{{border-collapse:collapse;width:100%;font-size:11px;min-width:1300px}}th,td{{padding:8px;border-bottom:1px solid #25302b;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#141b18;color:#a3ada8}}.guard{{color:#9aa6a0}}</style></head><body><main>
<h1>Sportland Smart — Demand Intelligence Sprint 2.1</h1><div class='sub'>Eventos del cliente + Shopify + Finanzas · read-only</div><div class='grid'>{cards_html}</div>
<section><h2>Plan de acción</h2>{pri_html}</section>
<section><h2>Decisión por producto</h2><table><thead><tr><th>Acción</th><th>Producto</th><th>Stock</th><th>30d</th><th>Prev30</th><th>Demand score</th><th>Conf.</th><th>% variantes lentas</th><th>Capital</th><th>Razón</th></tr></thead><tbody>{product_rows}</tbody></table></section>
<section><h2>Decisión por SKU / talla</h2><table><thead><tr><th>P</th><th>Acción</th><th>Scope</th><th>SKU</th><th>Producto</th><th>Stock</th><th>30d</th><th>Demand score</th><th>Señal</th><th>Demand producto</th><th>Precio sugerido</th><th>Desc.</th><th>Piso</th><th>Caja est.</th><th>Razón / guardrail</th></tr></thead><tbody>{decision_rows}</tbody></table></section>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
