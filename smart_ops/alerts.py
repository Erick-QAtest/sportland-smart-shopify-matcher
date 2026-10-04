from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any


def write_alert(
    project_root: Path,
    *,
    step: str,
    exit_code: int,
    message: str | None = None,
) -> tuple[Path, bool]:
    now = datetime.now(timezone.utc)
    logs_dir = project_root / "logs" / "ops"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "alerts.jsonl"

    payload: dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": "FAILED",
        "step": step,
        "exit_code": int(exit_code),
        "message": message or f"Daily pipeline failed at {step}",
    }

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    notified = False
    if platform.system() == "Darwin" and shutil.which("osascript"):
        safe_step = step.replace('"', "'")
        safe_message = payload["message"].replace('"', "'")
        script = (
            f'display notification "{safe_message}" '
            f'with title "Sportland Smart" subtitle "{safe_step}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
        )
        notified = result.returncode == 0

    return path, notified
