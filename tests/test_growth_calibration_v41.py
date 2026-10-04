from smart_growth.calibration import (
    CalibrationRules,
    calibrate_action,
    performance_adjustment,
)


RULES = CalibrationRules(
    high_threshold=80,
    medium_threshold=55,
)


def action(objective: str, channel: str = "META", **metadata):
    return {
        "objective": objective,
        "channel": channel,
        "priority_band": "HIGH",
        "initial_priority_band": "HIGH",
        "metadata": {
            "conversion_score": 0,
            "history_demand_score": 0,
            "demand_score": 0,
            "behavior_score": 0,
            "inventory_quantity": 5,
            **metadata,
        },
    }


def test_content_support_is_capped_at_medium():
    result = calibrate_action(
        action(
            "CONTENT_SUPPORT",
            "YOUTUBE",
            conversion_score=10,
            history_demand_score=10,
            behavior_score=10,
        ),
        rules=RULES,
    )
    assert result.band == "MEDIUM"


def test_search_review_is_capped_at_medium():
    result = calibrate_action(
        action(
            "SEARCH_DEMAND_REVIEW",
            "GOOGLE_SEO",
            conversion_score=10,
            history_demand_score=10,
        ),
        rules=RULES,
    )
    assert result.band == "MEDIUM"


def test_out_of_stock_capture_is_signal():
    result = calibrate_action(
        action("OUT_OF_STOCK_DEMAND_CAPTURE", "GOOGLE_SEO"),
        rules=RULES,
    )
    assert result.band == "SIGNAL"


def test_strong_conversion_campaign_can_be_high():
    result = calibrate_action(
        action(
            "CONVERSION_CAMPAIGN_REVIEW",
            conversion_score=5,
            history_demand_score=4,
            behavior_score=3,
            inventory_quantity=4,
        ),
        rules=RULES,
    )
    assert result.band == "HIGH"


def test_weak_clearance_not_automatically_high():
    result = calibrate_action(
        action(
            "CLEARANCE_CAMPAIGN_REVIEW",
            conversion_score=0,
            history_demand_score=0,
            behavior_score=0,
            inventory_quantity=8,
        ),
        rules=RULES,
    )
    assert result.band in {"LOW", "MEDIUM"}


def test_sale_like_action_without_stock_is_low():
    result = calibrate_action(
        action(
            "CONVERSION_CAMPAIGN_REVIEW",
            conversion_score=10,
            history_demand_score=10,
            inventory_quantity=0,
        ),
        rules=RULES,
    )
    assert result.band == "LOW"


def test_small_performance_sample_is_ignored():
    adj, context = performance_adjustment({
        "impressions": 100,
        "orders": 1,
        "roas": 5,
        "ctr": 0.10,
        "click_to_order_rate": 0.20,
    }, RULES)
    assert adj == 0
    assert context["performance_used"] is False


def test_good_performance_adds_bonus():
    adj, context = performance_adjustment({
        "impressions": 1000,
        "orders": 20,
        "roas": 4,
        "ctr": 0.04,
        "click_to_order_rate": 0.05,
    }, RULES)
    assert adj > 0
    assert context["performance_used"] is True


def test_bad_performance_adds_penalty():
    adj, context = performance_adjustment({
        "impressions": 1000,
        "orders": 0,
        "roas": 0.2,
        "ctr": 0.001,
        "click_to_order_rate": 0.0,
    }, RULES)
    assert adj < 0
    assert context["performance_used"] is True


def test_calibration_uses_only_latest_growth_run():
    from smart_growth.store import read_latest_growth_actions_for_calibration

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class FakeConnection:
        def execute(self, sql, params=None):
            if "FROM growth_runs" in sql:
                return Result([{"growth_run_id": "NEW-RUN"}])

            if "FROM growth_actions" in sql:
                assert "growth_run_id = %s" in sql
                assert params == ("NEW-RUN",)

                data = {
                    "OLD-RUN": [{"sku": "OLD-1"}],
                    "NEW-RUN": [{"sku": "NEW-1"}],
                }
                return Result(data[params[0]])

            raise AssertionError(f"Unexpected query: {sql}")

    actions = read_latest_growth_actions_for_calibration(FakeConnection())

    assert {row["sku"] for row in actions} == {"NEW-1"}

