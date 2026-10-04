from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list, tuple, set)):
        return json.dumps(list(v) if isinstance(v, set) else v, ensure_ascii=False)
    return v


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("status\nempty\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: _cell(row.get(k, "")) for k in fields})


def write_dashboard(
    path: str | Path,
    intelligence: dict[str, Any],
    decisions: list[dict[str, Any]],
    products: list[dict[str, Any]],
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    s = intelligence.get("summary") or {}

    def count(action: str) -> int:
        return sum(1 for r in decisions if r.get("action") == action)

    cards = [
        ("Eventos LOGGED", s.get("logged_events", 0), f"Confianza {s.get('data_confidence','LOW')}"),
        ("Con SKU", s.get("events_with_sku", 0), f"{s.get('unique_skus',0)} SKU(s)"),
        ("Clientes", s.get("unique_clients", 0), "UUID distintos; no expone teléfono"),
        ("Vender ahora", count("VENDER_AHORA"), "histórico + stock"),
        ("Proteger stock", count("PROTEGER_STOCK"), "demanda/conversión fuerte"),
        ("Revisar variante", count("REVISAR_VARIANTE"), "histórico contradice liquidación"),
        ("Liquidar variante", count("LIQUIDAR_VARIANTE"), "guardrails conservados"),
    ]
    card_html = "".join(
        f"<div class='card'><div class='label'>{html.escape(str(a))}</div><div class='value'>{html.escape(str(b))}</div><div class='note'>{html.escape(str(c))}</div></div>"
        for a, b, c in cards
    )

    sku_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('sku','')))}</td>"
        f"<td>{html.escape(str(r.get('product_title','')))}</td>"
        f"<td>{r.get('events',0)}</td>"
        f"<td>{_f(r.get('behavior_score')):.2f}</td>"
        f"<td>{_f(r.get('demand_score')):.2f}</td>"
        f"<td>{_f(r.get('conversion_score')):.2f}</td>"
        f"<td>{html.escape(str(r.get('demand_strength','')))}</td>"
        f"<td>{html.escape(str(r.get('conversion_strength','')))}</td>"
        f"<td>{html.escape(str(r.get('last_event_at','')))}</td>"
        "</tr>"
        for r in (intelligence.get("by_sku") or [])[:100]
    ) or "<tr><td colspan='9'>Sin eventos por SKU.</td></tr>"

    decision_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(r.get('priority','')))}</td>"
        f"<td><b>{html.escape(str(r.get('action','')))}</b></td>"
        f"<td>{html.escape(str(r.get('sku','')))}</td>"
        f"<td>{html.escape(str(r.get('product_title','')))}</td>"
        f"<td>{r.get('inventory_quantity',0)}</td>"
        f"<td>{_f(r.get('history_demand_score')):.2f}</td>"
        f"<td>{_f(r.get('conversion_score')):.2f}</td>"
        f"<td>{html.escape(str(r.get('action_v21','')))}</td>"
        f"<td>{html.escape(str(r.get('reason_v23','')))}</td>"
        "</tr>"
        for r in decisions[:180]
    ) or "<tr><td colspan='9'>Sin decisiones.</td></tr>"

    product_rows = "".join(
        "<tr>"
        f"<td><b>{html.escape(str(r.get('product_action','')))}</b></td>"
        f"<td>{html.escape(str(r.get('product_title','') or r.get('product_key','')))}</td>"
        f"<td>{_f(r.get('history_demand_score')):.2f}</td>"
        f"<td>{_f(r.get('conversion_score')):.2f}</td>"
        f"<td>{html.escape(str(r.get('product_action_v21','')))}</td>"
        f"<td>{html.escape(str(r.get('reason_v23','')))}</td>"
        "</tr>"
        for r in products[:100]
    ) or "<tr><td colspan='6'>Sin decisiones de producto.</td></tr>"

    doc = f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sportland Smart — Behavior Intelligence 2.3</title><style>
*{{box-sizing:border-box}}body{{font-family:Inter,system-ui,-apple-system,sans-serif;margin:0;background:#0b0f0d;color:#eef3ef}}main{{max-width:1500px;margin:auto;padding:28px}}h1{{margin:0 0 6px}}.sub{{color:#9aa6a0;margin-bottom:22px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px}}.card,section{{background:#141b18;border:1px solid #27332e;border-radius:14px;padding:16px}}.label{{font-size:12px;color:#a3ada8;text-transform:uppercase}}.value{{font-size:25px;font-weight:800;margin:7px 0}}.note{{font-size:12px;color:#7f8c86}}section{{margin-top:20px;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:11px;min-width:1000px}}th,td{{padding:8px;border-bottom:1px solid #25302b;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#141b18;color:#a3ada8}}</style></head><body><main>
<h1>Sportland Smart — Behavior Intelligence Sprint 2.3</h1><div class='sub'>Todo eventos_log_v5 + Shopify + Finanzas · análisis read-only</div><div class='grid'>{card_html}</div>
<section><h2>Inteligencia por SKU</h2><table><thead><tr><th>SKU</th><th>Producto</th><th>Eventos</th><th>Behavior</th><th>Demand</th><th>Conversion</th><th>Demanda</th><th>Conversión</th><th>Último evento</th></tr></thead><tbody>{sku_rows}</tbody></table></section>
<section><h2>Decisiones actualizadas</h2><table><thead><tr><th>P</th><th>Acción 2.3</th><th>SKU</th><th>Producto</th><th>Stock</th><th>Demand hist.</th><th>Conversion</th><th>Acción 2.1</th><th>Razón</th></tr></thead><tbody>{decision_rows}</tbody></table></section>
<section><h2>Producto completo</h2><table><thead><tr><th>Acción 2.3</th><th>Producto</th><th>Demand hist.</th><th>Conversion</th><th>Acción 2.1</th><th>Razón</th></tr></thead><tbody>{product_rows}</tbody></table></section>
</main></body></html>"""
    p.write_text(doc, encoding="utf-8")
