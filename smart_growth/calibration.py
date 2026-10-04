from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


CALIBRATION_VERSION = "growth-v4.1.0"
BAND_ORDER = {"SIGNAL": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class CalibrationRules:
    high_threshold: float = 80.0
    medium_threshold: float = 55.0
    minimum_impressions_for_performance: int = 250
    minimum_orders_for_performance: int = 2
    performance_bonus_cap: float = 12.0
    performance_penalty_cap: float = 12.0
    objective_base_scores: dict[str, float] | None = None
    max_band_by_objective: dict[str, str] | None = None

    @classmethod
    def from_json(cls, path: str | Path | None) -> "CalibrationRules":
        if not path:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        payload = json.loads(p.read_text(encoding="utf-8"))
        allowed = {
            k: v for k, v in payload.items()
            if k in cls.__dataclass_fields__
        }
        return cls(**allowed)

    def base_score(self, objective: str) -> float:
        defaults = {
            "CONVERSION_CAMPAIGN_REVIEW": 58.0,
            "ONE_TO_ONE_CONTACT_REVIEW": 62.0,
            "CLEARANCE_CAMPAIGN_REVIEW": 50.0,
            "COMMUNITY_PROMOTION_REVIEW": 52.0,
            "COMMUNITY_CLEARANCE_REVIEW": 46.0,
            "ORGANIC_DEMAND_CAPTURE": 48.0,
            "CONTENT_SUPPORT": 40.0,
            "SEARCH_DEMAND_REVIEW": 38.0,
            "OUT_OF_STOCK_DEMAND_CAPTURE": 18.0,
            "AGGREGATE_AUDIENCE_SIGNAL": 22.0,
        }
        return float((self.objective_base_scores or defaults).get(objective, 35.0))

    def max_band(self, objective: str) -> str | None:
        defaults = {
            "CONTENT_SUPPORT": "MEDIUM",
            "SEARCH_DEMAND_REVIEW": "MEDIUM",
            "COMMUNITY_CLEARANCE_REVIEW": "MEDIUM",
            "OUT_OF_STOCK_DEMAND_CAPTURE": "SIGNAL",
            "AGGREGATE_AUDIENCE_SIGNAL": "SIGNAL",
        }
        return (self.max_band_by_objective or defaults).get(objective)


@dataclass(frozen=True)
class CalibratedPriority:
    score: float
    band: str
    reason: str
    performance_adjustment: float
    breakdown: dict[str, float | str | bool | None]


def _band_for(score: float, rules: CalibrationRules) -> str:
    if score >= rules.high_threshold:
        return "HIGH"
    if score >= rules.medium_threshold:
        return "MEDIUM"
    return "LOW"


def _cap_band(band: str, cap: str | None) -> str:
    if not cap:
        return band
    if BAND_ORDER.get(band, 0) > BAND_ORDER.get(cap, 0):
        return cap
    return band


def performance_adjustment(
    perf: dict[str, Any] | None,
    rules: CalibrationRules,
) -> tuple[float, dict[str, Any]]:
    perf = perf or {}
    impressions = _i(perf.get("impressions"))
    orders = _i(perf.get("orders"))
    roas = _f(perf.get("roas"), -1.0)
    ctr = _f(perf.get("ctr"), -1.0)
    cvr = _f(perf.get("click_to_order_rate"), -1.0)

    enough = (
        impressions >= rules.minimum_impressions_for_performance
        or orders >= rules.minimum_orders_for_performance
    )
    if not enough:
        return 0.0, {
            "performance_used": False,
            "impressions": impressions,
            "orders": orders,
            "roas": None if roas < 0 else roas,
            "ctr": None if ctr < 0 else ctr,
            "click_to_order_rate": None if cvr < 0 else cvr,
        }

    adjustment = 0.0

    if roas >= 3.0:
        adjustment += 8.0
    elif roas >= 2.0:
        adjustment += 5.0
    elif roas >= 1.2:
        adjustment += 2.0
    elif roas >= 0 and roas < 0.7:
        adjustment -= 8.0

    if ctr >= 0.03:
        adjustment += 3.0
    elif ctr >= 0.015:
        adjustment += 1.5
    elif ctr >= 0 and ctr < 0.005 and impressions >= 500:
        adjustment -= 3.0

    if cvr >= 0.04:
        adjustment += 3.0
    elif cvr >= 0.02:
        adjustment += 1.5
    elif cvr >= 0 and cvr < 0.005 and impressions >= 500:
        adjustment -= 3.0

    adjustment = max(
        -rules.performance_penalty_cap,
        min(rules.performance_bonus_cap, adjustment),
    )

    return round(adjustment, 2), {
        "performance_used": True,
        "impressions": impressions,
        "orders": orders,
        "roas": None if roas < 0 else roas,
        "ctr": None if ctr < 0 else ctr,
        "click_to_order_rate": None if cvr < 0 else cvr,
    }


def calibrate_action(
    row: dict[str, Any],
    *,
    performance: dict[str, Any] | None = None,
    rules: CalibrationRules | None = None,
) -> CalibratedPriority:
    rules = rules or CalibrationRules()

    objective = _text(row.get("objective")).upper()
    channel = _text(row.get("channel")).upper()
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    initial_band = _text(
        row.get("initial_priority_band") or row.get("priority_band")
    ).upper()

    if objective in {
        "OUT_OF_STOCK_DEMAND_CAPTURE",
        "AGGREGATE_AUDIENCE_SIGNAL",
    }:
        return CalibratedPriority(
            score=0.0,
            band="SIGNAL",
            reason="Señal útil para aprendizaje, no una prioridad de activación comercial.",
            performance_adjustment=0.0,
            breakdown={
                "objective_base": rules.base_score(objective),
                "hard_signal_guardrail": True,
            },
        )

    base = rules.base_score(objective)

    conversion = _f(metadata.get("conversion_score"))
    demand = max(
        _f(metadata.get("history_demand_score")),
        _f(metadata.get("demand_score")),
    )
    behavior = _f(metadata.get("behavior_score"))
    stock = _i(metadata.get("inventory_quantity"), 0)

    conversion_points = min(18.0, max(0.0, conversion * 3.0))
    demand_points = min(14.0, max(0.0, demand * 2.5))
    behavior_points = min(8.0, max(0.0, behavior * 1.5))

    inventory_points = 0.0
    sale_like = objective in {
        "CONVERSION_CAMPAIGN_REVIEW",
        "CLEARANCE_CAMPAIGN_REVIEW",
        "COMMUNITY_PROMOTION_REVIEW",
        "COMMUNITY_CLEARANCE_REVIEW",
        "ONE_TO_ONE_CONTACT_REVIEW",
    }
    if sale_like:
        if stock <= 0:
            inventory_points = -25.0
        elif stock <= 3:
            inventory_points = 6.0
        else:
            inventory_points = 4.0
    elif stock > 0:
        inventory_points = 2.0

    initial_points = {
        "HIGH": 4.0,
        "MEDIUM": 2.0,
        "LOW": 0.0,
        "SIGNAL": -5.0,
    }.get(initial_band, 0.0)

    perf_adjust, perf_context = performance_adjustment(performance, rules)

    raw = (
        base
        + conversion_points
        + demand_points
        + behavior_points
        + inventory_points
        + initial_points
        + perf_adjust
    )
    score = round(max(0.0, min(100.0, raw)), 2)
    band = _band_for(score, rules)

    cap = rules.max_band(objective)
    band = _cap_band(band, cap)

    if sale_like and stock <= 0:
        band = "LOW"

    reason = (
        f"{objective}: base={base:.0f}, conversion={conversion_points:.1f}, "
        f"demand={demand_points:.1f}, behavior={behavior_points:.1f}, "
        f"inventory={inventory_points:.1f}, performance={perf_adjust:.1f}."
    )
    if cap and _band_for(score, rules) != band:
        reason += f" Guardrail: prioridad máxima {cap} para este objetivo."

    return CalibratedPriority(
        score=score,
        band=band,
        reason=reason,
        performance_adjustment=perf_adjust,
        breakdown={
            "objective": objective,
            "channel": channel,
            "objective_base": base,
            "conversion_points": round(conversion_points, 2),
            "demand_points": round(demand_points, 2),
            "behavior_points": round(behavior_points, 2),
            "inventory_points": round(inventory_points, 2),
            "initial_priority_points": round(initial_points, 2),
            "performance_adjustment": perf_adjust,
            **perf_context,
        },
    )
