from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
from typing import Any

from smart_memory.config import MemoryConfig
from smart_memory.db import connect
from smart_ops.status import load_status


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _age_hours(value: Any, now: datetime) -> float | None:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600)


def classify_health(
    *,
    db_ok: bool,
    daily_status: str | None,
    daily_age_hours: float | None,
    memory_status: str | None,
    backup_verified: bool,
    backup_age_hours: float | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if not db_ok:
        reasons.append("PostgreSQL no disponible")
        return "FAIL", reasons

    if daily_status == "FAILED":
        reasons.append("La última corrida diaria falló")
        return "FAIL", reasons

    if memory_status == "FAILED":
        reasons.append("La última corrida de Memory falló")
        return "FAIL", reasons

    if daily_status is None:
        reasons.append("Aún no hay estado diario registrado")
    elif daily_age_hours is not None and daily_age_hours > 36:
        reasons.append("La última corrida diaria tiene más de 36 horas")

    if memory_status is None:
        reasons.append("No hay corrida Memory registrada")

    if not backup_verified:
        reasons.append("No existe un backup PostgreSQL verificado")
    elif backup_age_hours is not None and backup_age_hours > 36:
        reasons.append("El último backup tiene más de 36 horas")

    return ("WARN", reasons) if reasons else ("HEALTHY", [])


def collect_health(project_root: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    daily = load_status(project_root) or {}

    payload: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "project_root": str(project_root),
        "daily": daily or None,
        "database": {"ok": False},
        "memory_run": None,
        "backup": None,
        "overall": "WARN",
        "reasons": [],
    }

    cfg = MemoryConfig.from_env(str(project_root / ".env"))
    errors = cfg.validate()
    if errors:
        payload["reasons"] = errors
        payload["overall"] = "FAIL"
        return payload

    try:
        with connect(cfg) as conn:
            health = conn.execute(
                "SELECT * FROM smart_memory_health_v"
            ).fetchone()
            payload["database"] = {
                "ok": True,
                "health": dict(health) if health else {},
            }

            memory = conn.execute(
                """
                SELECT run_id, started_at, finished_at, status, failed_step
                FROM memory_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
            if memory:
                payload["memory_run"] = dict(memory)

            backup = conn.execute(
                """
                SELECT
                    backup_id,
                    created_at,
                    database_name,
                    backup_path,
                    mirror_path,
                    size_bytes,
                    sha256,
                    verified,
                    retention_days
                FROM ops_backups
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            if backup:
                payload["backup"] = dict(backup)

    except Exception as exc:
        payload["database"] = {
            "ok": False,
            "error": str(exc),
        }

    daily_status = daily.get("status")
    daily_age = _age_hours(
        daily.get("finished_at") or daily.get("updated_at"),
        now,
    )
    memory = payload.get("memory_run") or {}
    backup = payload.get("backup") or {}

    backup_verified = bool(backup.get("verified"))
    backup_age = _age_hours(backup.get("created_at"), now)

    overall, reasons = classify_health(
        db_ok=bool(payload["database"].get("ok")),
        daily_status=daily_status,
        daily_age_hours=daily_age,
        memory_status=memory.get("status"),
        backup_verified=backup_verified,
        backup_age_hours=backup_age,
    )
    payload["overall"] = overall
    payload["reasons"] = reasons
    payload["metrics"] = {
        "daily_age_hours": round(daily_age, 2) if daily_age is not None else None,
        "backup_age_hours": round(backup_age, 2) if backup_age is not None else None,
    }
    return payload


def _fmt_bytes(value: Any) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "-"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def render_html(payload: dict[str, Any]) -> str:
    overall = html.escape(str(payload.get("overall") or "UNKNOWN"))
    daily = payload.get("daily") or {}
    memory = payload.get("memory_run") or {}
    backup = payload.get("backup") or {}
    db = payload.get("database") or {}
    db_health = db.get("health") or {}
    reasons = payload.get("reasons") or []

    reason_html = (
        "".join(f"<li>{html.escape(str(item))}</li>" for item in reasons)
        if reasons else
        "<li>Sin alertas operativas activas.</li>"
    )

    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else "-"))

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sportland Smart — Ops Health</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f7fa;color:#111827}}
main{{max-width:1080px;margin:0 auto;padding:32px 20px}}
h1{{margin:0 0 8px}}
.sub{{color:#6b7280;margin-bottom:28px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.card{{background:white;border-radius:16px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.value{{font-size:28px;font-weight:700;margin-top:8px}}
small{{color:#6b7280}}
table{{width:100%;border-collapse:collapse}}
td{{padding:8px 0;border-bottom:1px solid #eef2f7}}
td:last-child{{text-align:right;font-weight:600}}
ul{{margin-bottom:0}}
</style>
</head>
<body>
<main>
<h1>Sportland Smart — Ops Health</h1>
<div class="sub">Generado: {esc(payload.get("generated_at"))}</div>

<div class="grid">
  <div class="card"><small>Estado general</small><div class="value">{overall}</div></div>
  <div class="card"><small>Daily pipeline</small><div class="value">{esc(daily.get("status"))}</div><small>{esc(daily.get("current_step"))}</small></div>
  <div class="card"><small>Memory</small><div class="value">{esc(memory.get("status"))}</div><small>{esc(memory.get("run_id"))}</small></div>
  <div class="card"><small>Último backup</small><div class="value">{'OK' if backup.get('verified') else '-'}</div><small>{_fmt_bytes(backup.get("size_bytes"))}</small></div>
</div>

<div class="grid" style="margin-top:16px">
  <div class="card">
    <h3>Memoria</h3>
    <table>
      <tr><td>Customers</td><td>{esc(db_health.get("customers"))}</td></tr>
      <tr><td>Events</td><td>{esc(db_health.get("events"))}</td></tr>
      <tr><td>Demand intents</td><td>{esc(db_health.get("demand_intents"))}</td></tr>
      <tr><td>Waiting stock</td><td>{esc(db_health.get("waiting_stock"))}</td></tr>
      <tr><td>Restock matches</td><td>{esc(db_health.get("restock_matches"))}</td></tr>
    </table>
  </div>
  <div class="card">
    <h3>Respaldo</h3>
    <table>
      <tr><td>Database</td><td>{esc(backup.get("database_name"))}</td></tr>
      <tr><td>Creado</td><td>{esc(backup.get("created_at"))}</td></tr>
      <tr><td>Verificado</td><td>{esc(backup.get("verified"))}</td></tr>
      <tr><td>Retención</td><td>{esc(backup.get("retention_days"))} días</td></tr>
      <tr><td>Mirror</td><td>{esc(backup.get("mirror_path"))}</td></tr>
    </table>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <h3>Alertas / atención</h3>
  <ul>{reason_html}</ul>
</div>
</main>
</body>
</html>
"""


def write_health_artifacts(project_root: Path) -> tuple[Path, Path, dict[str, Any]]:
    payload = collect_health(project_root)
    out_dir = project_root / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "ops_health.json"
    html_path = out_dir / "ops_health_dashboard.html"

    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    html_path.write_text(render_html(payload), encoding="utf-8")
    return json_path, html_path, payload
