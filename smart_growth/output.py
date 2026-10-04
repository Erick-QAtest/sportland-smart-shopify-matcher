from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any, Iterable

from smart_growth.planner import GrowthAction


RESULT_FIELDS = [
    "growth_action_id",
    "external_ref",
    "impressions",
    "clicks",
    "conversations",
    "orders",
    "revenue",
    "spend",
]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_actions_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    items = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "growth_action_id",
        "channel",
        "objective",
        "priority_band",
        "activation_mode",
        "status",
        "sku",
        "product_title",
        "source_type",
        "source_ref",
        "reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)


def write_results_template(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(rows)
    by_channel: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_objective: dict[str, int] = {}

    for row in items:
        channel = str(row.get("channel") or "UNKNOWN")
        priority = str(row.get("priority_band") or "UNKNOWN")
        objective = str(row.get("objective") or "UNKNOWN")
        by_channel[channel] = by_channel.get(channel, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1
        by_objective[objective] = by_objective.get(objective, 0) + 1

    return {
        "total_actions": len(items),
        "by_channel": by_channel,
        "by_priority": by_priority,
        "by_objective": by_objective,
        "guardrails": {
            "automatic_activation": False,
            "requires_human_approval": True,
            "customer_contact": "manual_review_only",
        },
    }


def write_dashboard(path: Path, rows: Iterable[dict[str, Any]], summary: dict[str, Any]) -> None:
    items = list(rows)

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""))

    cards = "".join(
        f"""
        <div class="card">
          <div class="k">{esc(channel)}</div>
          <div class="v">{count}</div>
        </div>
        """
        for channel, count in sorted(summary.get("by_channel", {}).items())
    )

    body = "".join(
        f"""
        <tr>
          <td>{esc(row.get("priority_band"))}</td>
          <td>{esc(row.get("channel"))}</td>
          <td>{esc(row.get("objective"))}</td>
          <td>{esc(row.get("sku"))}</td>
          <td>{esc(row.get("product_title"))}</td>
          <td>{esc(row.get("status"))}</td>
        </tr>
        """
        for row in items[:250]
    )

    path.write_text(
        f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sportland Smart Growth</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#f6f8fb;color:#111827;margin:0}}
main{{max-width:1200px;margin:auto;padding:32px 20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
.card{{background:#fff;padding:18px;border-radius:14px;box-shadow:0 2px 10px rgba(0,0,0,.05)}}
.k{{color:#6b7280;font-size:13px}} .v{{font-size:30px;font-weight:800}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;margin-top:18px}}
th,td{{padding:10px;border-bottom:1px solid #eef2f7;text-align:left;font-size:13px}}
.note{{background:#fff7ed;border:1px solid #fed7aa;padding:14px;border-radius:12px;margin:18px 0}}
</style>
</head>
<body>
<main>
<h1>Sportland Smart — Growth Activation Plan</h1>
<p>Puente entre inteligencia comercial y publicidad/contenido.</p>
<div class="note"><strong>Guardrail:</strong> todas las acciones son DRAFT y requieren aprobación humana. No se envían anuncios, WhatsApp ni publicaciones automáticamente.</div>
<div class="grid">
<div class="card"><div class="k">Total acciones</div><div class="v">{summary.get("total_actions",0)}</div></div>
{cards}
</div>
<table>
<thead><tr><th>Prioridad</th><th>Canal</th><th>Objetivo</th><th>SKU</th><th>Producto</th><th>Estado</th></tr></thead>
<tbody>{body}</tbody>
</table>
</main>
</body>
</html>""",
        encoding="utf-8",
    )
