from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from smart_ops.backup import database_name_from_url, prune_old_backups
from smart_ops.health import classify_health
from smart_ops.status import fail_run, load_status, start_run


def test_database_name_from_url():
    assert database_name_from_url("postgresql:///sportland_smart") == "sportland_smart"
    assert (
        database_name_from_url("postgresql://user@localhost:5432/example")
        == "example"
    )


def test_prune_old_backups(tmp_path: Path):
    old = tmp_path / "old.dump"
    fresh = tmp_path / "fresh.dump"
    old.write_bytes(b"old")
    fresh.write_bytes(b"fresh")

    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(days=20)).timestamp()
    fresh_time = (now - timedelta(days=1)).timestamp()

    import os
    os.utime(old, (old_time, old_time))
    os.utime(fresh, (fresh_time, fresh_time))

    deleted = prune_old_backups(tmp_path, retention_days=14, now=now)
    assert deleted == 1
    assert not old.exists()
    assert fresh.exists()


def test_health_is_healthy_when_all_current():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="OK",
        daily_age_hours=2,
        memory_status="OK",
        backup_verified=True,
        backup_age_hours=2,
    )
    assert status == "HEALTHY"
    assert reasons == []


def test_failed_daily_is_fail():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="FAILED",
        daily_age_hours=1,
        memory_status="OK",
        backup_verified=True,
        backup_age_hours=1,
    )
    assert status == "FAIL"
    assert reasons


def test_missing_backup_is_warn():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="OK",
        daily_age_hours=1,
        memory_status="OK",
        backup_verified=False,
        backup_age_hours=None,
    )
    assert status == "WARN"
    assert any("backup" in item.lower() for item in reasons)


def test_local_status_survives_without_database(tmp_path: Path):
    # No .env is present, so DB persistence will warn but local state must work.
    payload, warning = start_run(tmp_path)
    assert payload["status"] == "RUNNING"
    assert warning

    payload, warning = fail_run(
        tmp_path,
        step_name="test-step",
        exit_code=9,
    )
    assert payload["status"] == "FAILED"
    assert payload["exit_code"] == 9

    stored = load_status(tmp_path)
    assert stored is not None
    assert stored["failed_step"] == "test-step"
