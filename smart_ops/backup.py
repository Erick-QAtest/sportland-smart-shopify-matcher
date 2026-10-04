from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from smart_memory.config import MemoryConfig
from smart_memory.db import connect
from smart_ops.status import load_status


DEFAULT_RETENTION_DAYS = 14


@dataclass(frozen=True)
class BackupResult:
    path: Path
    mirror_path: Path | None
    database_name: str
    size_bytes: int
    sha256: str
    verified: bool
    deleted_old_backups: int


def database_name_from_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    name = parsed.path.lstrip("/").strip()
    return name or "postgres"


def _binary_candidates(name: str) -> list[Path]:
    candidates: list[Path] = []
    discovered = shutil.which(name)
    if discovered:
        candidates.append(Path(discovered))

    candidates.extend([
        Path(f"/opt/homebrew/opt/postgresql@16/bin/{name}"),
        Path(f"/opt/homebrew/opt/postgresql@17/bin/{name}"),
        Path(f"/opt/homebrew/bin/{name}"),
        Path(f"/usr/local/opt/postgresql@16/bin/{name}"),
        Path(f"/usr/local/opt/postgresql@17/bin/{name}"),
        Path(f"/usr/local/bin/{name}"),
    ])
    return candidates


def find_pg_binary(name: str) -> Path:
    for candidate in _binary_candidates(name):
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        f"No se encontró {name}. Verifica PostgreSQL/Homebrew antes del backup."
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune_old_backups(
    backup_dir: Path,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(days=retention_days)
    deleted = 0

    for path in backup_dir.glob("*.dump"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            path.unlink()
            deleted += 1

    return deleted


def create_backup(
    project_root: Path,
    *,
    retention_days: int | None = None,
    mirror_dir: Path | None = None,
) -> BackupResult:
    cfg = MemoryConfig.from_env(str(project_root / ".env"))
    errors = cfg.validate()
    if errors:
        raise RuntimeError("; ".join(errors))

    days = retention_days or int(
        os.getenv("SPORTLAND_BACKUP_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
    )
    if days < 1:
        raise ValueError("SPORTLAND_BACKUP_RETENTION_DAYS debe ser >= 1")

    db_name = database_name_from_url(cfg.database_url)
    backup_dir = project_root / "backups" / "postgres"
    backup_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    stamp = now.astimezone().strftime("%Y%m%d_%H%M%S")
    path = backup_dir / f"{db_name}_{stamp}.dump"

    pg_dump = find_pg_binary("pg_dump")
    pg_restore = find_pg_binary("pg_restore")

    dump = subprocess.run(
        [
            str(pg_dump),
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(path),
            cfg.database_url,
        ],
        text=True,
        capture_output=True,
    )
    if dump.returncode != 0:
        if path.exists():
            path.unlink()
        detail = (dump.stderr or dump.stdout or "").strip()
        raise RuntimeError(f"pg_dump falló: {detail[-1000:]}")

    verify = subprocess.run(
        [str(pg_restore), "--list", str(path)],
        text=True,
        capture_output=True,
    )
    if verify.returncode != 0:
        detail = (verify.stderr or verify.stdout or "").strip()
        raise RuntimeError(f"Backup creado pero no verificable: {detail[-1000:]}")

    size_bytes = path.stat().st_size
    digest = sha256_file(path)

    resolved_mirror = mirror_dir
    if resolved_mirror is None:
        raw = os.getenv("SPORTLAND_BACKUP_MIRROR_DIR", "").strip()
        if raw:
            resolved_mirror = Path(raw).expanduser()

    mirrored: Path | None = None
    if resolved_mirror is not None:
        resolved_mirror.mkdir(parents=True, exist_ok=True)
        mirrored = resolved_mirror / path.name
        shutil.copy2(path, mirrored)

    deleted = prune_old_backups(
        backup_dir,
        retention_days=days,
        now=now,
    )

    run_status = load_status(project_root) or {}
    run_id = run_status.get("run_id")

    try:
        with connect(cfg) as conn:
            conn.execute(
                """
                INSERT INTO ops_backups(
                    created_at,
                    run_id,
                    database_name,
                    backup_path,
                    mirror_path,
                    size_bytes,
                    sha256,
                    verified,
                    retention_days,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                """,
                (
                    now,
                    run_id,
                    db_name,
                    str(path),
                    str(mirrored) if mirrored else None,
                    size_bytes,
                    digest,
                    days,
                    Jsonb({
                        "format": "pg_dump_custom",
                        "deleted_old_backups": deleted,
                    }),
                ),
            )
            conn.commit()
    except Exception:
        # A valid filesystem backup must remain usable even if audit logging fails.
        pass

    return BackupResult(
        path=path,
        mirror_path=mirrored,
        database_name=db_name,
        size_bytes=size_bytes,
        sha256=digest,
        verified=True,
        deleted_old_backups=deleted,
    )
