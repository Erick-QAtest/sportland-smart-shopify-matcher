from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from typing import TextIO

from psycopg.types.json import Jsonb

from smart_memory.config import MemoryConfig
from smart_memory.db import connect


@dataclass(frozen=True)
class StepSpec:
    name: str
    argv: tuple[str, ...]


@dataclass
class StepResult:
    name: str
    argv: list[str]
    exit_code: int
    status: str
    started_at: str
    finished_at: str
    duration_ms: int
    output_tail: str


def make_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    stamp = current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"memory-{stamp}-{uuid.uuid4().hex[:8]}"


def build_plan(*, python_executable: str, shopify_fixture: str) -> list[StepSpec]:
    py = python_executable
    fixture = shopify_fixture
    return [
        StepSpec("bootstrap", (py, "run_memory_bootstrap.py")),
        StepSpec("import_history", (py, "run_memory_import_v5.py")),
        StepSpec(
            "shopify_snapshot",
            (py, "run_memory_prepare_shopify.py", "--output", fixture),
        ),
        StepSpec(
            "match",
            (py, "run_match.py", "--shopify-fixture", fixture),
        ),
        StepSpec("sync_intents", (py, "run_memory_sync_intents.py")),
        StepSpec(
            "inventory_restock",
            (py, "run_memory_inventory.py", "--shopify-fixture", fixture),
        ),
        StepSpec("lifecycle", (py, "run_memory_lifecycle.py")),
        StepSpec("commercial", (py, "run_memory_commercial.py")),
        StepSpec("scoring", (py, "run_memory_score_opportunities.py")),
        StepSpec("verify", (py, "run_memory_verify.py")),
    ]


def run_step(
    step: StepSpec,
    *,
    cwd: Path,
    log_file: TextIO | None = None,
    env: dict[str, str] | None = None,
) -> StepResult:
    started = datetime.now(timezone.utc)
    started_perf = time.perf_counter()

    header = f"\n===== {step.name} =====\n$ {' '.join(step.argv)}\n"
    print(header, end="")
    if log_file:
        log_file.write(header)
        log_file.flush()

    process = subprocess.Popen(
        list(step.argv),
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        lines.append(line)
        if log_file:
            log_file.write(line)
            log_file.flush()

    exit_code = process.wait()
    finished = datetime.now(timezone.utc)
    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    status = "OK" if exit_code == 0 else "FAILED"
    tail = "".join(lines)[-6000:]

    footer = (
        f"----- {step.name}: {status} "
        f"({duration_ms} ms, exit={exit_code}) -----\n"
    )
    print(footer, end="")
    if log_file:
        log_file.write(footer)
        log_file.flush()

    return StepResult(
        name=step.name,
        argv=list(step.argv),
        exit_code=exit_code,
        status=status,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=duration_ms,
        output_tail=tail,
    )


def _record_run_start(conn, run_id: str, started_at: datetime) -> None:
    conn.execute(
        """
        INSERT INTO memory_runs(run_id, started_at, status, metadata)
        VALUES (%s, %s, 'RUNNING', %s)
        ON CONFLICT (run_id) DO NOTHING
        """,
        (
            run_id,
            started_at,
            Jsonb({
                "orchestrator": "memory-v3.6",
                "automatic_contact": False,
                "shopify_mode": "read_only",
            }),
        ),
    )
    conn.commit()


def _record_step(conn, run_id: str, order: int, result: StepResult) -> None:
    conn.execute(
        """
        INSERT INTO memory_run_steps(
            run_id,
            step_order,
            step_name,
            command,
            status,
            exit_code,
            started_at,
            finished_at,
            duration_ms,
            output_tail
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, step_name)
        DO UPDATE SET
            step_order = EXCLUDED.step_order,
            command = EXCLUDED.command,
            status = EXCLUDED.status,
            exit_code = EXCLUDED.exit_code,
            started_at = EXCLUDED.started_at,
            finished_at = EXCLUDED.finished_at,
            duration_ms = EXCLUDED.duration_ms,
            output_tail = EXCLUDED.output_tail
        """,
        (
            run_id,
            order,
            result.name,
            " ".join(result.argv),
            result.status,
            result.exit_code,
            result.started_at,
            result.finished_at,
            result.duration_ms,
            result.output_tail,
        ),
    )
    conn.commit()


def _finish_run(
    conn,
    *,
    run_id: str,
    status: str,
    failed_step: str | None,
    finished_at: datetime,
    result_count: int,
) -> None:
    conn.execute(
        """
        UPDATE memory_runs
        SET
            finished_at = %s,
            status = %s,
            failed_step = %s,
            metadata = metadata || %s
        WHERE run_id = %s
        """,
        (
            finished_at,
            status,
            failed_step,
            Jsonb({"steps_completed": result_count}),
            run_id,
        ),
    )
    conn.commit()


def write_summary(
    path: Path,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    failed_step: str | None,
    results: list[StepResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": status,
        "failed_step": failed_step,
        "steps": [asdict(item) for item in results],
        "guardrails": {
            "automatic_contact": False,
            "shopify_write": False,
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def execute_daily(
    *,
    project_root: Path,
    python_executable: str | None = None,
    keep_fixture: bool = False,
) -> int:
    project_root = project_root.resolve()
    py = python_executable or sys.executable
    run_id = make_run_id()
    started_at = datetime.now(timezone.utc)

    logs_dir = project_root / "logs" / "memory_runs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{run_id}.log"
    summary_path = logs_dir / f"{run_id}.json"

    fixture_path = Path(tempfile.gettempdir()) / f"{run_id}-shopify.json"
    plan = build_plan(
        python_executable=py,
        shopify_fixture=str(fixture_path),
    )

    results: list[StepResult] = []
    failed_step: str | None = None
    final_status = "FAILED"
    return_code = 1
    db_conn = None
    env = os.environ.copy()

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            print(f"SPORTLAND MEMORY DAILY — {run_id}")
            print(f"Project: {project_root}")
            print("Guardrails: Shopify read-only; no automatic customer contact.")
            log_file.write(f"SPORTLAND MEMORY DAILY — {run_id}\n")
            log_file.write(f"Project: {project_root}\n")

            bootstrap = run_step(
                plan[0],
                cwd=project_root,
                log_file=log_file,
                env=env,
            )
            results.append(bootstrap)

            if bootstrap.exit_code != 0:
                failed_step = bootstrap.name
                final_status = "FAILED"
                return_code = bootstrap.exit_code or 1
            else:
                cfg = MemoryConfig.from_env(str(project_root / ".env"))
                config_errors = cfg.validate()
                if config_errors:
                    print("MEMORY CONFIG ERROR:", "; ".join(config_errors))
                    failed_step = "orchestrator_db_logging"
                    final_status = "FAILED"
                    return_code = 2
                else:
                    db_conn = connect(cfg)
                    _record_run_start(db_conn, run_id, started_at)
                    _record_step(db_conn, run_id, 1, bootstrap)

                    return_code = 0
                    for order, step in enumerate(plan[1:], start=2):
                        result = run_step(
                            step,
                            cwd=project_root,
                            log_file=log_file,
                            env=env,
                        )
                        results.append(result)
                        _record_step(db_conn, run_id, order, result)

                        if result.exit_code != 0:
                            failed_step = step.name
                            final_status = "FAILED"
                            return_code = result.exit_code or 1
                            break

                    if failed_step is None:
                        final_status = "OK"

                    _finish_run(
                        db_conn,
                        run_id=run_id,
                        status=final_status,
                        failed_step=failed_step,
                        finished_at=datetime.now(timezone.utc),
                        result_count=len(results),
                    )

    finally:
        if db_conn is not None:
            db_conn.close()

        if fixture_path.exists() and not keep_fixture:
            fixture_path.unlink()

        finished_at = datetime.now(timezone.utc)
        write_summary(
            summary_path,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            status=final_status,
            failed_step=failed_step,
            results=results,
        )

        print("")
        print("========================================")
        print(f"SPORTLAND MEMORY DAILY: {final_status}")
        print(f"Run ID: {run_id}")
        print(f"Steps completed: {len(results)}/{len(plan)}")
        if failed_step:
            print(f"Failed step: {failed_step}")
        print(f"Log: {log_path}")
        print(f"Summary: {summary_path}")
        print("========================================")

    return return_code
