from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _f(v: Any, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _i(v: Any, default=0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _dt(v: Any) -> datetime | None:
    raw = str(v or "").strip()
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


MATCHER_TYPES = {"PREGUNTA_TALLA_PRECIO", "PREGUNTA_MODELO_ESPECIFICO", "PRUEBA_MULTIPLES_MODELOS"}
BASE_WEIGHTS = {
    "ENTRADA_WHATSAPP": 0.05,
    "REACCION_CONTENIDO": 0.10,
    "CLICK": 0.25,
    "OBSERVA_PRODUCTO": 0.20,
    "DM_ACTIVO": 0.75,
    "PREGUNTA_SISTEMA_APARTADO": 0.80,
    "APARTADO": 1.80,
    "ABONO_APARTADO": 2.00,
    "LIQUIDACION_APARTADO": 2.20,
    "SALE_SIN_COMPRA": 0.35,
}


def _recency(dt: datetime | None, now: datetime) -> float:
    if not dt:
        return 0.5
    age = max(0, (now - dt.astimezone(timezone.utc)).days)
    if age <= 7:
        return 1.0
    if age <= 30:
        return 0.6
    if age <= 60:
        return 0.3
    return 0.1


def build_behavior(events: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    by_sku: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0, "behavior_score": 0.0, "events_7d": 0, "events_30d": 0,
        "add_to_cart": 0, "size_select": 0, "product_views": 0, "last_event_at": ""
    })
    total = 0
    sku_resolved = 0
    matcher_events = 0
    for row in events:
        if str(row.get("status") or "").upper() != "LOGGED":
            continue
        total += 1
        typ = str(row.get("tipo_evento_nombre") or "").upper()
        if typ in MATCHER_TYPES:
            matcher_events += 1
            # Already represented in demand_supply_matches; avoid double counting.
            continue
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        sku_resolved += 1
        meta = {}
        try:
            meta = json.loads(str(row.get("meta_json") or "{}"))
        except Exception:
            pass
        action = str(meta.get("raw_action") or "").lower()
        base = BASE_WEIGHTS.get(typ, 0.0)
        if action == "add_to_cart":
            base = max(base, 1.20)
        elif action == "size_select":
            base = max(base, 0.60)
        elif action in {"product_view", "view_item"}:
            base = max(base, 0.20)
        if base <= 0:
            continue
        dt = _dt(row.get("fecha_evento"))
        score = base * _recency(dt, now)
        x = by_sku[sku]
        x["sku"] = sku
        x["events"] += 1
        x["behavior_score"] += score
        if dt:
            age = max(0, (now - dt.astimezone(timezone.utc)).days)
            if age <= 7:
                x["events_7d"] += 1
            if age <= 30:
                x["events_30d"] += 1
            iso = dt.isoformat()
            if iso > x["last_event_at"]:
                x["last_event_at"] = iso
        if action == "add_to_cart":
            x["add_to_cart"] += 1
        elif action == "size_select":
            x["size_select"] += 1
        elif action in {"product_view", "view_item"}:
            x["product_views"] += 1
    rows = []
    for sku, row in by_sku.items():
        row = dict(row)
        row["behavior_score"] = round(row["behavior_score"], 2)
        rows.append(row)
    rows.sort(key=lambda r: (-_f(r["behavior_score"]), -_i(r["events"]), r["sku"]))
    return {
        "summary": {"logged_events": total, "matcher_events": matcher_events, "behavior_events_with_sku": sku_resolved},
        "by_sku": rows,
    }


def write_behavior_artifacts(artifacts_dir: str | Path, behavior: dict[str, Any]) -> None:
    d = Path(artifacts_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "customer_behavior_summary_v22.json").write_text(json.dumps(behavior["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    rows = behavior["by_sku"]
    fields = ["sku", "events", "behavior_score", "events_7d", "events_30d", "add_to_cart", "size_select", "product_views", "last_event_at"]
    with (d / "customer_behavior_by_sku_v22.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
