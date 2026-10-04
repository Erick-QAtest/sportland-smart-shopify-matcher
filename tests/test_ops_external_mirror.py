from datetime import datetime, timezone
from pathlib import Path

import pytest

from smart_ops.backup import (
    copy_and_verify_mirror,
    sha256_file,
    validate_mirror_location,
)
from smart_ops.health import classify_health
from run_ops_mirror_setup import update_env


def test_copy_and_verify_mirror(tmp_path: Path):
    source_dir = tmp_path / "local"
    mirror_dir = tmp_path / "external"
    source_dir.mkdir()
    source = source_dir / "db.dump"
    source.write_bytes(b"sportland-backup-data")

    digest = sha256_file(source)
    size = source.stat().st_size

    destination, mirror_size, mirror_sha, verified = copy_and_verify_mirror(
        source,
        mirror_dir,
        expected_sha256=digest,
        expected_size_bytes=size,
    )

    assert destination.exists()
    assert mirror_size == size
    assert mirror_sha == digest
    assert verified is True


def test_mirror_inside_project_is_rejected(tmp_path: Path):
    project = tmp_path / "project"
    mirror = project / "backups" / "mirror"
    project.mkdir()

    with pytest.raises(ValueError):
        validate_mirror_location(project, mirror)


def test_required_unverified_mirror_is_health_fail():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="OK",
        daily_age_hours=1,
        memory_status="OK",
        backup_verified=True,
        backup_age_hours=1,
        mirror_required=True,
        mirror_verified=False,
    )
    assert status == "FAIL"
    assert any("mirror" in reason.lower() for reason in reasons)


def test_required_verified_mirror_is_healthy():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="OK",
        daily_age_hours=1,
        memory_status="OK",
        backup_verified=True,
        backup_age_hours=1,
        mirror_required=True,
        mirror_verified=True,
    )
    assert status == "HEALTHY"
    assert reasons == []


def test_optional_missing_mirror_does_not_break_health():
    status, reasons = classify_health(
        db_ok=True,
        daily_status="OK",
        daily_age_hours=1,
        memory_status="OK",
        backup_verified=True,
        backup_age_hours=1,
        mirror_required=False,
        mirror_verified=None,
    )
    assert status == "HEALTHY"
    assert reasons == []


def test_update_env_replaces_mirror_settings(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        'DATABASE_URL="postgresql:///sportland_smart"\n'
        'SPORTLAND_BACKUP_MIRROR_DIR="/old/path"\n'
        'SPORTLAND_BACKUP_REQUIRE_MIRROR=false\n',
        encoding="utf-8",
    )
    mirror = tmp_path / "Cloud Drive" / "Sportland"
    backup_path = update_env(env, mirror, 45)

    text = env.read_text(encoding="utf-8")
    assert 'DATABASE_URL="postgresql:///sportland_smart"' in text
    assert f'SPORTLAND_BACKUP_MIRROR_DIR="{mirror}"' in text
    assert "SPORTLAND_BACKUP_REQUIRE_MIRROR=true" in text
    assert "SPORTLAND_BACKUP_MIRROR_RETENTION_DAYS=45" in text
    assert backup_path.exists()
