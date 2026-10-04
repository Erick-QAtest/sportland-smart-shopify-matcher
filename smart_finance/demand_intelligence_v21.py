from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _text(v: Any) -> str:
    return str(v or "").strip()


def _norm(s: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(s)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text


def _parse_dt(v: Any) -> datetime | None:
    raw = _text(v)
    if not raw:
        return None
    # Common ISO / Shopify / Google Sheets forms.
    candidates = [raw, raw.replace("Z", "+00:00")]
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _first(row: dict[str, Any], names: Iterable[str]) -> str:
    for name in names:
        value = _text(row.get(name))
        if value:
            return value
    return ""


@dataclass
class DemandRules:
    weight_0_7d: float = 1.00
    weight_8_30d: float = 0.60
    weight_31_60d: float = 0.30
    weight_older: float = 0.10
    weight_unknown_date: float = 0.50
    explicit_size_bonus: float = 0.35
    exact_sku_bonus: float = 0.25
    available_bonus: float = 0.10
    out_of_stock_bonus: float = 0.50
    unresolved_penalty: float = 0.15
    repeated_sku_bonus_step: float = 0.15
    repeated_sku_bonus_cap: float = 0.60
    moderate_threshold: float = 1.00
    strong_threshold: float = 3.00
    product_strong_threshold: float = 4.00
    min_events_for_medium_confidence: int = 20
    min_events_for_high_confidence: int = 100


def _intent_multiplier(row: dict[str, Any]) -> float:
    kind = _first(row, ("demand_type", "event_type", "intent", "tipo_evento", "event_name")).upper()
    if not kind:
        return 1.0
    # High-intent signals should matter more, but never dominate the financial guardrails.
    if any(k in kind for k in ("COMPRA", "CART", "CHECKOUT", "APART", "RESERV")):
        return 1.40
    if any(k in kind for k in ("TALLA_PRECIO", "PRECIO_TALLA", "DISPONIBIL", "STOCK")):
        return 1.20
    if "TALLA" in kind:
        return 1.10
    if "PRECIO" in kind:
        return 1.05
    return 1.0


def _recency_weight(dt: datetime | None, as_of: datetime, rules: DemandRules) -> tuple[float, int | None]:
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


def _status(row: dict[str, Any]) -> str:
    return _first(row, ("match_status", "status", "resolution_status")).upper()


def _sku(row: dict[str, Any]) -> str:
    return _first(row, ("shopify_sku", "resolved_sku", "sku", "smart_sku"))


def _title(row: dict[str, Any]) -> str:
    return _first(row, ("shopify_product_title", "product_title", "resolved_product_title", "title", "smart_product"))


def _product_key_from_match(row: dict[str, Any]) -> str:
    pid = _first(row, ("shopify_product_id", "product_id"))
    if pid:
        return f"id:{pid}"
    handle = _first(row, ("shopify_handle", "product_handle", "handle"))
    if handle:
        return f"handle:{_norm(handle)}"
    title = _title(row)
    if title:
        return f"title:{_norm(title)}"
    return ""


def _event_dt(row: dict[str, Any]) -> datetime | None:
    raw = _first(row, (
        "event_at", "event_time", "event_timestamp", "timestamp", "created_at",
        "event_date", "date", "fecha", "fecha_evento"
    ))
    return _parse_dt(raw)


def _has_explicit_size(row: dict[str, Any]) -> bool:
    return bool(_first(row, ("requested_size", "size", "talla", "smart_size", "requested_talla")))


def build_demand_intelligence(
    matches: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
    rules: DemandRules | None = None,
) -> dict[str, Any]:
    rules = rules or DemandRules()
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    else:
        as_of = as_of.astimezone(timezone.utc)

    sku_rows: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0,
        "demand_score": 0.0,
        "available_events": 0,
        "oos_events": 0,
        "unresolved_events": 0,
        "explicit_size_events": 0,
        "events_7d": 0,
        "events_30d": 0,
        "events_60d": 0,
        "last_event_at": None,
        "product_key": "",
        "product_title": "",
    })
    product_rows: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "events": 0,
        "demand_score": 0.0,
        "available_events": 0,
        "oos_events": 0,
        "unresolved_events": 0,
        "explicit_size_events": 0,
        "events_7d": 0,
        "events_30d": 0,
        "events_60d": 0,
        "last_event_at": None,
        "product_title": "",
        "skus": set(),
    })

    total = 0
    resolved_sku_events = 0
    unresolved_events = 0
    dated_events = 0
    seen_per_sku: dict[str, int] = defaultdict(int)

    for row in matches:
        total += 1
        sku = _sku(row)
        pkey = _product_key_from_match(row)
        title = _title(row)
        status = _status(row)
        dt = _event_dt(row)
        if dt is not None:
            dated_events += 1
        recency, age = _recency_weight(dt, as_of, rules)
        score = recency * _intent_multiplier(row)

        explicit_size = _has_explicit_size(row)
        if explicit_size:
            score += rules.explicit_size_bonus
        if sku and status.startswith("MATCH"):
            score += rules.exact_sku_bonus
        if status == "MATCH_OUT_OF_STOCK":
            score += rules.out_of_stock_bonus
        elif status == "MATCH_AVAILABLE":
            score += rules.available_bonus
        if status.startswith("NEEDS_") or status in {"NO_SHOPIFY_MATCH", "AMBIGUOUS_MATCH", "SIZE_CONFLICT"}:
            score = max(0.05, score - rules.unresolved_penalty)
            unresolved_events += 1

        if sku:
            resolved_sku_events += 1
            repeat_count = seen_per_sku[sku]
            repeat_bonus = min(rules.repeated_sku_bonus_cap, repeat_count * rules.repeated_sku_bonus_step)
            score += repeat_bonus
            seen_per_sku[sku] += 1

            s = sku_rows[sku]
            s["sku"] = sku
            s["events"] += 1
            s["demand_score"] += score
            s["product_key"] = pkey or s["product_key"]
            s["product_title"] = title or s["product_title"]
            if explicit_size:
                s["explicit_size_events"] += 1
            if status == "MATCH_AVAILABLE":
                s["available_events"] += 1
            elif status == "MATCH_OUT_OF_STOCK":
                s["oos_events"] += 1
            elif status.startswith("NEEDS_") or status in {"NO_SHOPIFY_MATCH", "AMBIGUOUS_MATCH", "SIZE_CONFLICT"}:
                s["unresolved_events"] += 1
            if age is not None:
                if age <= 7:
                    s["events_7d"] += 1
                if age <= 30:
                    s["events_30d"] += 1
                if age <= 60:
                    s["events_60d"] += 1
            if dt is not None:
                iso = dt.isoformat()
                if not s["last_event_at"] or iso > s["last_event_at"]:
                    s["last_event_at"] = iso

        if pkey:
            p = product_rows[pkey]
            p["product_key"] = pkey
            p["events"] += 1
            p["demand_score"] += score
            p["product_title"] = title or p["product_title"]
            if sku:
                p["skus"].add(sku)
            if explicit_size:
                p["explicit_size_events"] += 1
            if status == "MATCH_AVAILABLE":
                p["available_events"] += 1
            elif status == "MATCH_OUT_OF_STOCK":
                p["oos_events"] += 1
            elif status.startswith("NEEDS_") or status in {"NO_SHOPIFY_MATCH", "AMBIGUOUS_MATCH", "SIZE_CONFLICT"}:
                p["unresolved_events"] += 1
            if age is not None:
                if age <= 7:
                    p["events_7d"] += 1
                if age <= 30:
                    p["events_30d"] += 1
                if age <= 60:
                    p["events_60d"] += 1
            if dt is not None:
                iso = dt.isoformat()
                if not p["last_event_at"] or iso > p["last_event_at"]:
                    p["last_event_at"] = iso

    def strength(score: float) -> str:
        if score >= rules.strong_threshold:
            return "STRONG"
        if score >= rules.moderate_threshold:
            return "MODERATE"
        if score > 0:
            return "WEAK"
        return "NONE"

    sku_list: list[dict[str, Any]] = []
    for sku, row in sku_rows.items():
        clean = dict(row)
        clean["demand_score"] = round(_f(clean["demand_score"]), 2)
        clean["demand_strength"] = strength(clean["demand_score"])
        sku_list.append(clean)
    sku_list.sort(key=lambda r: (-_f(r["demand_score"]), -_i(r["events"]), str(r["sku"])))

    product_list: list[dict[str, Any]] = []
    for key, row in product_rows.items():
        clean = dict(row)
        clean["demand_score"] = round(_f(clean["demand_score"]), 2)
        clean["demand_strength"] = (
            "STRONG" if clean["demand_score"] >= rules.product_strong_threshold
            else strength(clean["demand_score"])
        )
        clean["skus"] = sorted(clean["skus"])
        clean["sku_count"] = len(clean["skus"])
        product_list.append(clean)
    product_list.sort(key=lambda r: (-_f(r["demand_score"]), -_i(r["events"]), str(r["product_key"])))

    if total >= rules.min_events_for_high_confidence:
        confidence = "HIGH"
    elif total >= rules.min_events_for_medium_confidence:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "as_of": as_of.isoformat(),
        "summary": {
            "total_events": total,
            "resolved_sku_events": resolved_sku_events,
            "unresolved_events": unresolved_events,
            "dated_events": dated_events,
            "unique_skus_with_demand": len(sku_list),
            "unique_products_with_demand": len(product_list),
            "data_confidence": confidence,
        },
        "by_sku": sku_list,
        "by_product": product_list,
    }
