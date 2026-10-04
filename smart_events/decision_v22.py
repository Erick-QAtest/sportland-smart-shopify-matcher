from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _f(v: Any, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def read_csv(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def enhance_decisions(decisions: list[dict[str, Any]], behavior_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bmap = {str(r.get("sku") or "").strip(): r for r in behavior_rows}
    out: list[dict[str, Any]] = []
    for row in decisions:
        x = dict(row)
        sku = str(x.get("sku") or "").strip()
        b = bmap.get(sku, {})
        score = _f(b.get("behavior_score"))
        stock = int(_f(x.get("inventory_quantity")))
        action = str(x.get("action") or "")
        x["behavior_score"] = round(score, 2)
        x["behavior_events"] = b.get("events", 0)
        x["behavior_events_30d"] = b.get("events_30d", 0)
        x["behavior_add_to_cart"] = b.get("add_to_cart", 0)
        x["behavior_size_select"] = b.get("size_select", 0)
        x["action_v21"] = action

        # Financial guardrails still win. We do not turn demand into restock when liquidity blocks it.
        if action in {"NO_RECOMPRAR_AUN", "DEMANDA_PERDIDA"}:
            pass
        elif stock > 0 and score >= 3.0:
            x["action"] = "PROTEGER_STOCK"
            x["reason_v22"] = "Comportamiento cliente fuerte/repetido con stock; no liquidar y priorizar conversión."
        elif stock > 0 and score >= 1.0:
            x["action"] = "VENDER_AHORA"
            x["reason_v22"] = "Señal conductual reciente con stock; convertir intención en caja antes de descontar."
        elif action == "LIQUIDAR_VARIANTE" and score >= 0.50:
            x["action"] = "REVISAR_VARIANTE"
            x["reason_v22"] = "Hay interacción reciente suficiente para frenar liquidación automática de esta variante."
        else:
            x["reason_v22"] = "Sin señal conductual suficiente para modificar la decisión 2.1."
        out.append(x)
    return out


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
