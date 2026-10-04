from smart_growth.measurement_v41 import result_key


def test_result_key_is_stable():
    row = {
        "growth_action_id": "10",
        "external_ref": "meta-abc",
        "impressions": "1000",
        "clicks": "20",
        "conversations": "3",
        "orders": "2",
        "revenue": "1500",
        "spend": "300",
    }
    assert result_key(row) == result_key(dict(row))


def test_result_key_changes_when_metrics_change():
    a = {
        "growth_action_id": "10",
        "external_ref": "meta-abc",
        "impressions": "1000",
        "clicks": "20",
        "conversations": "3",
        "orders": "2",
        "revenue": "1500",
        "spend": "300",
    }
    b = dict(a)
    b["orders"] = "3"
    assert result_key(a) != result_key(b)
