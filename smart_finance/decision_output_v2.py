from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
        w.writerows(rows)


def _money(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return html.escape(str(v))


def _pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return html.escape(str(v))


def write_decision_dashboard(path: Path, snapshot: dict[str, Any], plan: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
    health = plan.get("health") or {}
    liq = plan.get("liquidity") or {}
    s = plan.get("summary") or {}

    cards = [
        ("Health", f"{health.get('score', '—')}/100", str(health.get('status') or 'UNKNOWN')),
        ("Caja", _money(liq.get("cash_available")), f"Cobertura {float(liq.get('cash_coverage_ratio') or 0):.2f}x"),
        ("Obligaciones 30d", _money(liq.get("obligations_30d")), f"Brecha {_money(liq.get('cash_gap'))}"),
        ("Vender ahora", str(s.get("sell_now", 0)), "demanda + stock"),
        ("Liquidar", str(s.get("liquidate", 0)), f"capital {_money(s.get('liquidation_capital_at_cost'))}"),
        ("Proteger stock", str(s.get("protect_stock", 0)), "rotación/demanda"),
        ("Demanda perdida", str(s.get("lost_demand_watchlist", 0)), "watchlist"),
        ("Recompra condicional", str(s.get("conditional_restock", 0)), "solo con guardrails"),
    ]
    card_html = "".join(
        f"<div class='card'><div class='label'>{html.escape(a)}</div><div class='value'>{html.escape(b)}</div><div class='note'>{html.escape(c)}</div></div>"
        for a,b,c in cards
    )

    pri_html = "".join(
        f"<div class='priority {html.escape(str(x.get('priority','P2')).lower())}'><b>{html.escape(str(x.get('priority')))} · {html.escape(str(x.get('action')))}</b><div>{html.escape(str(x.get('reason')))}</div></div>"
        for x in plan.get("priorities", [])
    ) or "<div class='priority'>Sin prioridades generadas.</div>"

    rows = []
    for r in decisions[:150]:
        rows.append(
            "<tr>"
            f"<td><span class='pill {html.escape(str(r.get('priority','P2')).lower())}'>{html.escape(str(r.get('priority')))}</span></td>"
            f"<td><b>{html.escape(str(r.get('action')))}</b></td>"
            f"<td>{html.escape(str(r.get('sku')))}</td>"
            f"<td>{html.escape(str(r.get('product_title') or ''))}</td>"
            f"<td>{r.get('inventory_quantity',0)}</td>"
            f"<td>{r.get('units_sold_30d',0)}</td>"
            f"<td>{r.get('units_sold_prev_30d',0)}</td>"
            f"<td>{r.get('demand_events',0)}</td>"
            f"<td>{_pct(r.get('margin_pct'))}</td>"
            f"<td>{_money(r.get('capital_at_cost'))}</td>"
            f"<td>{r.get('liquidation_score',0)}</td>"
            f"<td>{r.get('protect_score',0)}</td>"
            f"<td>{r.get('restock_score',0)}</td>"
            f"<td>{html.escape(str(r.get('reason') or ''))}<br><span class='guard'>{html.escape(str(r.get('guardrail') or ''))}</span></td>"
            "</tr>"
        )
    rows_html = "".join(rows) or "<tr><td colspan='14'>Sin decisiones.</td></tr>"

    doc = f"""<!doctype html>
<html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sportland Smart — Decision Sprint 2</title>
<style>
*{{box-sizing:border-box}}body{{font-family:Inter,system-ui,-apple-system,sans-serif;margin:0;background:#0b0f0d;color:#eef3ef}}
main{{max-width:1480px;margin:auto;padding:28px}}h1{{margin:0 0 6px}}.sub{{color:#9aa6a0;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}.card,section{{background:#141b18;border:1px solid #27332e;border-radius:14px;padding:16px}}
.label{{font-size:12px;color:#a3ada8;text-transform:uppercase;letter-spacing:.04em}}.value{{font-size:26px;font-weight:800;margin:7px 0}}.note{{font-size:12px;color:#7f8c86}}
section{{margin-top:20px;overflow:auto}}.priority{{border-left:4px solid #65736c;padding:10px 12px;margin:8px 0;background:#101613;border-radius:8px}}.priority.p0{{border-left-color:#ff5b5b}}.priority.p1{{border-left-color:#f5b942}}.priority.p2{{border-left-color:#63a7ff}}
table{{border-collapse:collapse;width:100%;font-size:11px;min-width:1300px}}th,td{{padding:8px;border-bottom:1px solid #25302b;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#141b18;color:#a3ada8}}.pill{{padding:3px 7px;border-radius:999px;font-weight:800}}.pill.p0{{background:#4b1f1f;color:#ff9d9d}}.pill.p1{{background:#493a18;color:#ffd97a}}.pill.p2{{background:#16354f;color:#8ac8ff}}.guard{{color:#9aa6a0}}
</style></head><body><main>
<h1>Sportland Smart — Decision Sprint 2</h1><div class='sub'>Read-only · acciones priorizadas por liquidez, demanda, rotación y margen</div>
<div class='grid'>{card_html}</div>
<section><h2>Plan de acción</h2>{pri_html}</section>
<section><h2>Decisiones por SKU</h2><table><thead><tr><th>P</th><th>Acción</th><th>SKU</th><th>Producto</th><th>Stock</th><th>30d</th><th>Prev30</th><th>Demanda</th><th>Margen</th><th>Capital</th><th>Liq.</th><th>Prot.</th><th>Restock</th><th>Razón / guardrail</th></tr></thead><tbody>{rows_html}</tbody></table></section>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
