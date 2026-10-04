from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_kpis_csv(path: Path, snapshot: dict[str, Any], health: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value", "source"])
        w.writerow(["financial_health_score", health.get("score"), "hybrid"])
        w.writerow(["financial_health_status", health.get("status"), "hybrid"])
        for key, val in snapshot.get("kpis", {}).items():
            if key.startswith((
                "sales_", "orders_", "average_", "net_product", "discounts",
                "order_reductions", "units_sold", "estimated_cogs", "gross_margin",
                "inventory_", "sell_through", "gmroi"
            )):
                src = "shopify"
            elif key.startswith((
                "cash_", "projected_", "buying_", "known_debt", "debt_",
                "monthly_interest", "interest_", "scheduled_"
            )):
                src = "finance_sheet/hybrid"
            else:
                src = "hybrid"
            w.writerow([key, val, src])


def write_rows_csv(path: Path, rows: list[dict[str, Any]], default_header: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(default_header or "status\nempty\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for k in row:
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
        return f"{float(v) * 100:.1f}%"
    except Exception:
        return html.escape(str(v))


def write_dashboard(
    path: Path,
    snapshot: dict[str, Any],
    health: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    k = snapshot["kpis"]
    cards = [
        ("Salud financiera", f"{health.get('score', '—')}/100", health.get("status", "UNKNOWN"), "Hybrid"),
        ("Ventas 30 días", _money(k.get("sales_30d")), _pct(k.get("sales_change_vs_previous_30d")), "Shopify"),
        ("Pedidos 30 días", str(k.get("orders_30d") or 0), f"AOV {_money(k.get('average_order_value_30d'))}", "Shopify"),
        ("Margen bruto estimado", _money(k.get("gross_margin_30d")), _pct(k.get("gross_margin_pct_30d")), "Shopify + costo"),
        ("Caja disponible", _money(k.get("cash_available")), "Efectivo + cuentas", "Finanzas"),
        ("Pagos 30 días", _money(k.get("projected_obligations_30d")), "Compromisos programados", "Finanzas"),
        ("Cobertura de caja", f"{(k.get('cash_coverage_ratio') or 0):.2f}x", f"Brecha {_money(k.get('projected_cash_gap'))}", "Hybrid"),
        ("Deuda conocida", _money(k.get("known_debt_total")), f"Servicio {_money(k.get('scheduled_debt_service'))}", "Finanzas"),
        ("Inventario", f"{k.get('inventory_units') or 0} uds", f"Costo conocido {_money(k.get('inventory_cost_value_known'))}", "Shopify"),
        ("Valor retail inventario", _money(k.get("inventory_retail_value")), f"Sin costo: {k.get('inventory_missing_cost_units') or 0} uds", "Shopify"),
        ("Sell-through proxy 30d", _pct(k.get("sell_through_30d_proxy")), f"Cobertura {round(k.get('inventory_coverage_days_proxy') or 0)} días", "Shopify"),
        ("GMROI proxy 30d", f"{(k.get('gmroi_30d_proxy') or 0):.2f}x", "Margen 30d / inventario a costo", "Hybrid"),
    ]

    card_html = "".join(
        f"<div class='card'><div class='src'>{html.escape(src)}</div><div class='label'>{html.escape(a)}</div><div class='value'>{html.escape(str(b))}</div><div class='note'>{html.escape(str(c))}</div></div>"
        for a, b, c, src in cards
    )
    rows_html = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('priority', '')))}</td>"
        f"<td>{html.escape(str(r.get('sku', '')))}</td>"
        f"<td>{html.escape(str(r.get('product_title', '')))}</td>"
        f"<td>{r.get('inventory_quantity', 0)}</td>"
        f"<td>{r.get('units_sold_30d', 0)}</td>"
        f"<td>{r.get('demand_events', 0)}</td>"
        f"<td><b>{html.escape(str(r.get('decision', '')))}</b></td>"
        f"<td>{html.escape(str(r.get('reason', '')))}</td>"
        "</tr>"
        for r in decisions[:100]
    ) or "<tr><td colspan='8'>Sin decisiones.</td></tr>"

    doc = f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sportland Smart Finance v0.2</title>
<style>
body{{font-family:Inter,system-ui,-apple-system,sans-serif;margin:0;background:#f5f7fa;color:#101828}}
main{{max-width:1280px;margin:auto;padding:28px}}
h1{{margin-bottom:4px}}.sub{{color:#667085;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.card,section{{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:17px}}
.src{{font-size:10px;text-transform:uppercase;color:#175cd3;font-weight:700}}
.label{{font-size:13px;color:#667085;margin-top:4px}}.value{{font-size:25px;font-weight:760;margin:8px 0 3px}}
.note{{font-size:12px;color:#98a2b3}}section{{margin-top:24px;overflow:auto}}
table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:9px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}
th{{color:#475467;position:sticky;top:0;background:#fff}}
</style>
</head>
<body><main>
<h1>Sportland Smart — Financial Pulse v0.2</h1>
<div class='sub'>Shopify-first + Finanzas externas · Read-only · {html.escape(str(snapshot.get('as_of') or ''))}</div>
<div class='grid'>{card_html}</div>
<section><h2>Decisiones por SKU</h2><table><thead><tr><th>P</th><th>SKU</th><th>Producto</th><th>Stock</th><th>Vend. 30d</th><th>Demanda</th><th>Decisión</th><th>Razón</th></tr></thead><tbody>{rows_html}</tbody></table></section>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
