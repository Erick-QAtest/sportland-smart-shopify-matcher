from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _text(v: Any) -> str:
    return str(v or "").strip()


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_dt(v: Any) -> datetime | None:
    raw = _text(v)
    if not raw:
        return None
    candidates = [raw, raw.replace("Z", "+00:00")]
    for value in candidates:
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _norm(v: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(v)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")


@dataclass(frozen=True)
class EventWeights:
    behavior: float = 0.0
    demand: float = 0.0
    conversion: float = 0.0


DEFAULT_EVENT_WEIGHTS: dict[str, EventWeights] = {
    # Awareness / engagement
    "ENTRADA_WHATSAPP": EventWeights(0.50, 0.20, 0.00),
    "REACCION_CONTENIDO": EventWeights(0.25, 0.10, 0.00),
    "CLICK": EventWeights(0.25, 0.10, 0.00),
    "DM_ACTIVO": EventWeights(0.75, 0.75, 0.10),
    "UNION_COMUNIDAD_WHATSAPP": EventWeights(0.40, 0.05, 0.00),
    "SALIDA_COMUNIDAD_WHATSAPP": EventWeights(-0.40, -0.05, -0.10),
    # Product intent
    "PREGUNTA_TALLA_PRECIO": EventWeights(1.00, 1.25, 0.20),
    "PREGUNTA_SISTEMA_APARTADO": EventWeights(0.80, 0.80, 0.35),
    "PREGUNTA_MODELO_ESPECIFICO": EventWeights(0.90, 1.00, 0.15),
    "PRUEBA_MULTIPLES_MODELOS": EventWeights(1.10, 1.50, 0.30),
    # Commitment / purchase progression
    "APARTADO": EventWeights(1.50, 2.00, 1.50),
    "ABONO_APARTADO": EventWeights(1.50, 2.50, 2.50),
    "LIQUIDACION_APARTADO": EventWeights(1.50, 2.50, 3.50),
    "COMPRA": EventWeights(1.50, 2.50, 4.00),
    "COMPRA_TIENDA_FISICA": EventWeights(1.50, 2.50, 4.00),
    "COMPRA_ECOMMERCE": EventWeights(1.50, 2.50, 4.00),
    "COMPRA_MARKETPLACE": EventWeights(1.50, 2.50, 4.00),
    # Negative outcome: there was demand, but conversion failed.
    "SALE_SIN_COMPRA": EventWeights(0.25, 0.50, -0.75),
    "EVENTO_NEGATIVO": EventWeights(-0.50, -0.40, -0.50),
    "SILENCIO_PROLONGADO": EventWeights(-0.20, -0.15, -0.30),
    # Post-purchase / loyalty
    "REVIEW_POSITIVA": EventWeights(0.25, 0.05, 0.25),
    "REVIEW_NEGATIVA": EventWeights(-0.30, 0.00, -0.25),
    # Merchant/system-side events: deliberately zero, not customer demand.
    "OFERTA_LLEGADA_PROXIMA": EventWeights(),
    "MODELO_NUEVO_INGRESADO": EventWeights(),
    "PROMO_MONEDERO_120": EventWeights(),
    "PROMO_SEGUNDO_PAR_20": EventWeights(),
    "PROMO_ENVIO_GRATIS": EventWeights(),
}


@dataclass
class HistoryRules:
    weight_0_7d: float = 1.00
    weight_8_30d: float = 0.70
    weight_31_60d: float = 0.40
    weight_older: float = 0.20
    weight_unknown_date: float = 0.50
    behavior_moderate: float = 1.00
    behavior_strong: float = 3.00
    demand_moderate: float = 1.00
    demand_strong: float = 3.00
    conversion_moderate: float = 1.00
    conversion_strong: float = 4.00
    medium_confidence_events: int = 20
    high_confidence_events: int = 100

    @classmethod
    def from_json(cls, path: str | Path | None) -> "HistoryRules":
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        allowed = {k: v for k, v in payload.items() if k in cls.__dataclass_fields__}
        return cls(**allowed)


def load_event_weights(path: str | Path | None = None) -> dict[str, EventWeights]:
    weights = dict(DEFAULT_EVENT_WEIGHTS)
    if not path:
        return weights
    p = Path(path)
    if not p.exists():
        return weights
    payload = json.loads(p.read_text(encoding="utf-8"))
    for name, values in payload.items():
        if not isinstance(values, dict):
            continue
        weights[str(name).upper()] = EventWeights(
            behavior=_f(values.get("behavior")),
            demand=_f(values.get("demand")),
            conversion=_f(values.get("conversion")),
        )
    return weights


def _recency(dt: datetime | None, as_of: datetime, rules: HistoryRules) -> tuple[float, int | None]:
    if dt is None:
        return rules.weight_unknown_date, None
    age = max(0, (as_of - dt).days)
    if age <= 7:
        return rules.weight_0_7d, age
    if age <= 30:
        return rules.weight_8_30d, age
    if age <= 60:
        return rules.weight_31_60d, age
    return rules.weight_older, age


def _strength(score: float, moderate: float, strong: float) -> str:
    if score >= strong:
        return "STRONG"
    if score >= moderate:
        return "MODERATE"
    if score > 0:
        return "WEAK"
    if score < 0:
        return "NEGATIVE"
    return "NONE"


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def build_product_lookup(artifacts_dir: str | Path = "artifacts") -> dict[str, dict[str, str]]:
    """Map SKU -> product identity using existing Shopify/decision artifacts. Never infers from SKU text."""
    art = Path(artifacts_dir)
    candidates = [
        art / "smart_finance_decisions_v21.csv",
        art / "shopify_inventory_finance.csv",
        art / "shopify_sku_performance.csv",
        art / "demand_supply_matches.csv",
    ]
    out: dict[str, dict[str, str]] = {}
    for path in candidates:
        for row in _read_csv(path):
            sku = _first(row, "sku", "shopify_sku", "resolved_sku", "smart_sku")
            if not sku:
                continue
            product_id = _first(row, "product_id", "shopify_product_id")
            handle = _first(row, "product_handle", "shopify_handle", "handle")
            title = _first(row, "product_title", "shopify_product_title", "resolved_product_title", "title")
            current = out.setdefault(sku, {})
            if product_id and not current.get("product_id"):
                current["product_id"] = product_id
            if handle and not current.get("product_handle"):
                current["product_handle"] = handle
            if title and not current.get("product_title"):
                current["product_title"] = title
    return out


def _product_identity(sku: str, lookup: dict[str, dict[str, str]]) -> tuple[str, str]:
    row = lookup.get(sku) or {}
    pid = _text(row.get("product_id"))
    handle = _text(row.get("product_handle"))
    title = _text(row.get("product_title"))
    if pid:
        return f"id:{pid}", title
    if handle:
        return f"handle:{_norm(handle)}", title
    if title:
        return f"title:{_norm(title)}", title
    # Conservative fallback: one SKU is one product until Shopify gives us identity.
    return f"sku:{sku}", ""


def build_customer_intelligence(
    events: list[dict[str, Any]],
    *,
    product_lookup: dict[str, dict[str, str]] | None = None,
    as_of: datetime | None = None,
    rules: HistoryRules | None = None,
    event_weights: dict[str, EventWeights] | None = None,
) -> dict[str, Any]:
    rules = rules or HistoryRules()
    event_weights = event_weights or dict(DEFAULT_EVENT_WEIGHTS)
    product_lookup = product_lookup or {}
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)

    def blank_sku() -> dict[str, Any]:
        return {
            "events": 0, "scored_events": 0, "events_7d": 0, "events_30d": 0, "events_60d": 0,
            "behavior_score": 0.0, "demand_score": 0.0, "conversion_score": 0.0,
            "positive_conversion_events": 0, "failed_conversion_events": 0,
            "unique_clients": set(), "last_event_at": "", "event_types": Counter(),
            "product_key": "", "product_title": "",
        }

    by_sku: dict[str, dict[str, Any]] = defaultdict(blank_sku)
    event_type_summary: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0, "sku_events": 0, "behavior_score": 0.0, "demand_score": 0.0, "conversion_score": 0.0
    })

    total_logged = 0
    events_with_sku = 0
    scored_events = 0
    unscored_events = 0
    dated_events = 0
    unique_clients_all: set[str] = set()

    for row in events:
        if _text(row.get("status")).upper() != "LOGGED":
            continue
        total_logged += 1
        typ = _text(row.get("tipo_evento_nombre")).upper()
        sku = _text(row.get("sku"))
        client = _text(row.get("client_uuid"))
        if client:
            unique_clients_all.add(client)
        dt = _parse_dt(row.get("fecha_evento"))
        recency, age = _recency(dt, as_of, rules)
        if dt:
            dated_events += 1
        weights = event_weights.get(typ, EventWeights())
        behavior = weights.behavior * recency
        demand = weights.demand * recency
        conversion = weights.conversion * recency
        scored = any(abs(x) > 1e-12 for x in (weights.behavior, weights.demand, weights.conversion))
        if scored:
            scored_events += 1
        else:
            unscored_events += 1

        es = event_type_summary[typ or "UNKNOWN"]
        es["event_type"] = typ or "UNKNOWN"
        es["events"] += 1
        es["behavior_score"] += behavior
        es["demand_score"] += demand
        es["conversion_score"] += conversion
        if sku:
            es["sku_events"] += 1

        if not sku:
            continue
        events_with_sku += 1
        pkey, title = _product_identity(sku, product_lookup)
        x = by_sku[sku]
        x["sku"] = sku
        x["events"] += 1
        if scored:
            x["scored_events"] += 1
        x["behavior_score"] += behavior
        x["demand_score"] += demand
        x["conversion_score"] += conversion
        x["product_key"] = pkey
        x["product_title"] = title or x["product_title"]
        x["event_types"][typ or "UNKNOWN"] += 1
        if weights.conversion > 0:
            x["positive_conversion_events"] += 1
        elif weights.conversion < 0:
            x["failed_conversion_events"] += 1
        if client:
            x["unique_clients"].add(client)
        if age is not None:
            if age <= 7:
                x["events_7d"] += 1
            if age <= 30:
                x["events_30d"] += 1
            if age <= 60:
                x["events_60d"] += 1
        if dt:
            iso = dt.isoformat()
            if iso > x["last_event_at"]:
                x["last_event_at"] = iso

    sku_rows: list[dict[str, Any]] = []
    by_product: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0, "scored_events": 0, "events_7d": 0, "events_30d": 0, "events_60d": 0,
        "behavior_score": 0.0, "demand_score": 0.0, "conversion_score": 0.0,
        "positive_conversion_events": 0, "failed_conversion_events": 0,
        "unique_clients": set(), "skus": set(), "last_event_at": "", "event_types": Counter(),
        "product_title": "",
    })

    for sku, raw in by_sku.items():
        row = dict(raw)
        row["behavior_score"] = round(_f(row["behavior_score"]), 2)
        row["demand_score"] = round(_f(row["demand_score"]), 2)
        row["conversion_score"] = round(_f(row["conversion_score"]), 2)
        row["behavior_strength"] = _strength(row["behavior_score"], rules.behavior_moderate, rules.behavior_strong)
        row["demand_strength"] = _strength(row["demand_score"], rules.demand_moderate, rules.demand_strong)
        row["conversion_strength"] = _strength(row["conversion_score"], rules.conversion_moderate, rules.conversion_strong)
        row["unique_clients"] = len(raw["unique_clients"])
        row["event_types"] = dict(sorted(raw["event_types"].items()))
        sku_rows.append(row)

        p = by_product[row["product_key"]]
        p["product_key"] = row["product_key"]
        p["product_title"] = row.get("product_title") or p["product_title"]
        p["events"] += row["events"]
        p["scored_events"] += row["scored_events"]
        p["events_7d"] += row["events_7d"]
        p["events_30d"] += row["events_30d"]
        p["events_60d"] += row["events_60d"]
        p["behavior_score"] += row["behavior_score"]
        p["demand_score"] += row["demand_score"]
        p["conversion_score"] += row["conversion_score"]
        p["positive_conversion_events"] += row["positive_conversion_events"]
        p["failed_conversion_events"] += row["failed_conversion_events"]
        p["skus"].add(sku)
        # Product distinct-client count is computed conservatively from SKU-level counts only when raw IDs exist.
        p["unique_clients"].update(raw["unique_clients"])
        p["event_types"].update(raw["event_types"])
        if row["last_event_at"] > p["last_event_at"]:
            p["last_event_at"] = row["last_event_at"]

    sku_rows.sort(key=lambda r: (-_f(r["demand_score"]), -_f(r["conversion_score"]), -_f(r["behavior_score"]), r["sku"]))

    product_rows: list[dict[str, Any]] = []
    for key, raw in by_product.items():
        row = dict(raw)
        row["behavior_score"] = round(_f(row["behavior_score"]), 2)
        row["demand_score"] = round(_f(row["demand_score"]), 2)
        row["conversion_score"] = round(_f(row["conversion_score"]), 2)
        row["behavior_strength"] = _strength(row["behavior_score"], rules.behavior_moderate, rules.behavior_strong)
        row["demand_strength"] = _strength(row["demand_score"], rules.demand_moderate, rules.demand_strong)
        row["conversion_strength"] = _strength(row["conversion_score"], rules.conversion_moderate, rules.conversion_strong)
        row["unique_clients"] = len(raw["unique_clients"])
        row["skus"] = sorted(raw["skus"])
        row["sku_count"] = len(row["skus"])
        row["event_types"] = dict(sorted(raw["event_types"].items()))
        product_rows.append(row)
    product_rows.sort(key=lambda r: (-_f(r["demand_score"]), -_f(r["conversion_score"]), -_f(r["behavior_score"]), r["product_key"]))

    type_rows: list[dict[str, Any]] = []
    for typ, raw in event_type_summary.items():
        row = dict(raw)
        row["behavior_score"] = round(_f(row["behavior_score"]), 2)
        row["demand_score"] = round(_f(row["demand_score"]), 2)
        row["conversion_score"] = round(_f(row["conversion_score"]), 2)
        rule = event_weights.get(typ, EventWeights())
        row["base_behavior_weight"] = rule.behavior
        row["base_demand_weight"] = rule.demand
        row["base_conversion_weight"] = rule.conversion
        type_rows.append(row)
    type_rows.sort(key=lambda r: (-int(r["events"]), r["event_type"]))

    if total_logged >= rules.high_confidence_events:
        confidence = "HIGH"
    elif total_logged >= rules.medium_confidence_events:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "as_of": as_of.isoformat(),
        "summary": {
            "logged_events": total_logged,
            "scored_events": scored_events,
            "unscored_events": unscored_events,
            "events_with_sku": events_with_sku,
            "dated_events": dated_events,
            "unique_clients": len(unique_clients_all),
            "unique_skus": len(sku_rows),
            "unique_products": len(product_rows),
            "data_confidence": confidence,
        },
        "rules": asdict(rules),
        "by_sku": sku_rows,
        "by_product": product_rows,
        "event_types": type_rows,
    }
