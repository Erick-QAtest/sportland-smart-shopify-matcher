from pathlib import Path
import sys

from smart_memory.orchestrator import (
    StepSpec,
    build_plan,
    make_run_id,
    run_step,
)
from smart_memory.intents import state_after_sync


def test_plan_has_safe_expected_order():
    plan = build_plan(
        python_executable="python",
        shopify_fixture="/tmp/shopify.json",
    )
    assert [step.name for step in plan] == [
        "bootstrap",
        "import_history",
        "shopify_snapshot",
        "match",
        "sync_intents",
        "inventory_restock",
        "lifecycle",
        "commercial",
        "scoring",
        "verify",
    ]


def test_match_and_inventory_share_one_shopify_fixture():
    fixture = "/tmp/one-snapshot.json"
    plan = build_plan(
        python_executable="python",
        shopify_fixture=fixture,
    )
    match = next(step for step in plan if step.name == "match")
    inventory = next(step for step in plan if step.name == "inventory_restock")
    assert fixture in match.argv
    assert fixture in inventory.argv


def test_terminal_intents_are_not_reopened():
    assert state_after_sync("PURCHASED", "WAITING_STOCK") == "PURCHASED"
    assert state_after_sync("EXPIRED", "AVAILABLE") == "EXPIRED"
    assert state_after_sync("WAITING_STOCK", "AVAILABLE") == "AVAILABLE"


def test_run_step_success(tmp_path: Path):
    step = StepSpec(
        "ok",
        (sys.executable, "-c", "print('orchestrator-ok')"),
    )
    result = run_step(step, cwd=tmp_path)
    assert result.exit_code == 0
    assert result.status == "OK"
    assert "orchestrator-ok" in result.output_tail


def test_run_step_failure_is_visible(tmp_path: Path):
    step = StepSpec(
        "fail",
        (
            sys.executable,
            "-c",
            "import sys; print('expected-failure'); sys.exit(7)",
        ),
    )
    result = run_step(step, cwd=tmp_path)
    assert result.exit_code == 7
    assert result.status == "FAILED"
    assert "expected-failure" in result.output_tail


def test_run_id_has_memory_prefix():
    assert make_run_id().startswith("memory-")
