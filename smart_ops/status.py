from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from smart_memory.config import MemoryConfig
from smart_memory.db import connect


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def status_path(project_root: Path) -> Path:
    return project_root / "logs" / "ops" / "latest_daily_status.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_status(project_root: Path) -> dict[str, Any] | None:
    path = status_path(project_root)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _persist_db(project_root: Path, payload: dict[str, Any]) -> str | None:
    try:
        cfg = MemoryConfig.from_env(str(project_root / ".env"))
        errors = cfg.validate()
        if errors:
            return "; ".join(errors)

        with connect(cfg) as conn:
            conn.execute(
                """
                INSERT INTO ops_daily_runs(
                    run_id,
                    started_at,
                    finished_at,
                    status,
                    current_step,
                    failed_step,
                    exit_code,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id)
                DO UPDATE SET
                    finished_at = EXCLUDED.finished_at,
                    status = EXCLUDED.status,
                    current_step = EXCLUDED.current_step,
                    failed_step = EXCLUDED.failed_step,
                    exit_code = EXCLUDED.exit_code,
                    metadata = EXCLUDED.metadata
                """,
                (
                    payload["run_id"],
                    payload["started_at"],
                    payload.get("finished_at"),
                    payload["status"],
                    payload.get("current_step"),
                    payload.get("failed_step"),
                    payload.get("exit_code"),
                    Jsonb({
                        "completed_steps": payload.get("completed_steps", []),
                        "updated_at": payload.get("updated_at"),
                    }),
                ),
            )
            conn.commit()
        return None
    except Exception as exc:  # best-effort ops logging
        return str(exc)


def start_run(project_root: Path) -> tuple[dict[str, Any], str | None]:
    now = utc_now()
    run_id = f"daily-{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    payload = {
        "run_id": run_id,
        "started_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "finished_at": None,
        "status": "RUNNING",
        "current_step": "startup",
        "failed_step": None,
        "exit_code": None,
        "completed_steps": [],
    }
    _write_json(status_path(project_root), payload)
    return payload, _persist_db(project_root, payload)


def set_step(
    project_root: Path,
    step_name: str,
) -> tuple[dict[str, Any], str | None]:
    payload = load_status(project_root)
    if payload is None or payload.get("status") != "RUNNING":
        payload, _ = start_run(project_root)

    previous = str(payload.get("current_step") or "").strip()
    completed = list(payload.get("completed_steps") or [])
    if previous and previous != "startup" and previous != step_name:
        if previous not in completed:
            completed.append(previous)

    now = utc_now()
    payload.update({
        "status": "RUNNING",
        "current_step": step_name,
        "updated_at": now.isoformat(),
        "completed_steps": completed,
    })
    _write_json(status_path(project_root), payload)
    return payload, _persist_db(project_root, payload)


def fail_run(
    project_root: Path,
    *,
    step_name: str,
    exit_code: int,
) -> tuple[dict[str, Any], str | None]:
    payload = load_status(project_root)
    if payload is None:
        payload, _ = start_run(project_root)

    now = utc_now()
    payload.update({
        "status": "FAILED",
        "current_step": step_name,
        "failed_step": step_name,
        "exit_code": int(exit_code),
        "updated_at": now.isoformat(),
        "finished_at": now.isoformat(),
    })
    _write_json(status_path(project_root), payload)
    return payload, _persist_db(project_root, payload)


def finish_run(project_root: Path) -> tuple[dict[str, Any], str | None]:
    payload = load_status(project_root)
    if payload is None:
        payload, _ = start_run(project_root)

    completed = list(payload.get("completed_steps") or [])
    current = str(payload.get("current_step") or "").strip()
    if current and current != "startup" and current not in completed:
        completed.append(current)

    now = utc_now()
    payload.update({
        "status": "OK",
        "current_step": "complete",
        "failed_step": None,
        "exit_code": 0,
        "updated_at": now.isoformat(),
        "finished_at": now.isoformat(),
        "completed_steps": completed,
    })
    _write_json(status_path(project_root), payload)
    return payload, _persist_db(project_root, payload)
