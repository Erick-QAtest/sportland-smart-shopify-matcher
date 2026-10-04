from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any, Iterable


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    items = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not items:
        path.write_text("", encoding="utf-8")
        return
    fields = list(items[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)


def write_priority_dashboard(
    path: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    def esc(v: Any) -> str:
        return html.escape(str(v if v is not None else ""))

    cards = "".join(
        f'<div class="card"><div class="k">{esc(k)}</div><div class="v">{v}</div></div>'
        for k, v in summary.get("by_priority", {}).items()
    )
    body = "".join(
        f"""
        <tr>
          <td>{esc(r.get("priority_band"))}</td>
          <td>{esc(r.get("priority_score"))}</td>
          <td>{esc(r.get("channel"))}</td>
          <td>{esc(r.get("objective"))}</td>
          <td>{esc(r.get("sku"))}</td>
          <td>{esc(r.get("product_title"))}</td>
          <td>{esc(r.get("priority_reason"))}</td>
        </tr>
        """
        for r in rows[:250]
    )

    path.write_text(
        f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sportland Smart — Growth Priority</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#f6f8fb;color:#111827;margin:0}}
main{{max-width:1280px;margin:auto;padding:30px 18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
.card{{background:#fff;padding:16px;border-radius:14px;box-shadow:0 2px 10px rgba(0,0,0,.05)}}
.k{{font-size:13px;color:#6b7280}} .v{{font-size:28px;font-weight:800}}
.note{{background:#eff6ff;border:1px solid #bfdbfe;padding:14px;border-radius:12px;margin:18px 0}}
table{{width:100%;border-collapse:collapse;background:#fff;margin-top:18px}}
th,td{{padding:9px;border-bottom:1px solid #eef2f7;text-align:left;font-size:12px;vertical-align:top}}
</style></head><body><main>
<h1>Sportland Smart — Growth Priority Calibration v4.1</h1>
<p>Prioridades calibradas por intención, stock, comportamiento y resultados observados.</p>
<div class="note">HIGH es deliberadamente selectivo. Acciones de contenido/revisión tienen límites de prioridad y toda activación sigue requiriendo aprobación humana.</div>
<div class="grid">
<div class="card"><div class="k">Total</div><div class="v">{summary.get("total_actions", 0)}</div></div>
{cards}
</div>
<table><thead><tr>
<th>Prioridad</th><th>Score</th><th>Canal</th><th>Objetivo</th><th>SKU</th><th>Producto</th><th>Razón</th>
</tr></thead><tbody>{body}</tbody></table>
</main></body></html>""",
        encoding="utf-8",
    )


def write_performance_dashboard(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    def esc(v: Any) -> str:
        return html.escape(str(v if v is not None else ""))

    body = "".join(
        f"""
        <tr>
          <td>{esc(r.get("channel"))}</td>
          <td>{esc(r.get("objective"))}</td>
          <td>{esc(r.get("impressions"))}</td>
          <td>{esc(r.get("clicks"))}</td>
          <td>{esc(r.get("orders"))}</td>
          <td>{esc(r.get("revenue"))}</td>
          <td>{esc(r.get("spend"))}</td>
          <td>{esc(r.get("ctr"))}</td>
          <td>{esc(r.get("click_to_order_rate"))}</td>
          <td>{esc(r.get("roas"))}</td>
        </tr>
        """
        for r in rows
    )

    path.write_text(
        f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sportland Smart — Growth Performance</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#f6f8fb;color:#111827;margin:0}}
main{{max-width:1200px;margin:auto;padding:30px 18px}}
.note{{background:#fff7ed;border:1px solid #fed7aa;padding:14px;border-radius:12px;margin:18px 0}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{padding:9px;border-bottom:1px solid #eef2f7;text-align:left;font-size:12px}}
</style></head><body><main>
<h1>Sportland Smart — Growth Performance v4.1</h1>
<p>Resultados observados por canal y objetivo.</p>
<div class="note">Sin suficientes impresiones/órdenes, el sistema mantiene ajuste de performance neutral. No “aprende” de muestras pequeñas.</div>
<table><thead><tr>
<th>Canal</th><th>Objetivo</th><th>Impr.</th><th>Clicks</th><th>Orders</th><th>Revenue</th><th>Spend</th><th>CTR</th><th>CVR</th><th>ROAS</th>
</tr></thead><tbody>{body}</tbody></table>
</main></body></html>""",
        encoding="utf-8",
    )
