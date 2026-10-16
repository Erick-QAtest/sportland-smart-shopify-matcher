"""Cerrar el día (v7.4): el portal pide una corrida del pipeline diario.

El portal no ejecuta el pipeline: escribe logs/ops/run_request y la unidad
sportland-daily.path (systemd) arranca sportland-daily.service, el mismo servicio
del timer de las 7:00. run_daily_sportland.sh usa un candado para no correr dos veces.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from smart_ops.status import load_status
from smart_portal.portal_v60 import esc

TZ = ZoneInfo("America/Mexico_City")
RUNNING_STALE_AFTER = timedelta(hours=3)
REQUEST_PENDING_FOR = timedelta(minutes=3)


def request_path(project_root: Path) -> Path:
    return project_root / "logs" / "ops" / "run_request"


def _parse(ts: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_running(status: dict[str, Any] | None, *, now: datetime) -> bool:
    if not status or status.get("status") != "RUNNING":
        return False
    updated = _parse(status.get("updated_at") or status.get("started_at"))
    return updated is not None and now - updated < RUNNING_STALE_AFTER


def pending_request(project_root: Path, status: dict[str, Any] | None, *, now: datetime) -> bool:
    """Hay una solicitud reciente que el servidor todavía no empieza a correr."""
    path = request_path(project_root)
    if not path.exists():
        return False
    requested = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    started = _parse((status or {}).get("started_at"))
    return now - requested < REQUEST_PENDING_FOR and (started is None or started < requested)


def request_run(project_root: Path, *, actor: str, now: datetime | None = None) -> str:
    """Devuelve 'solicitado', 'en_curso' o 'ya_solicitado'."""
    now = now or datetime.now(timezone.utc)
    status = load_status(project_root)
    if is_running(status, now=now):
        return "en_curso"
    if pending_request(project_root, status, now=now):
        return "ya_solicitado"
    path = request_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"requested_at": now.isoformat(), "actor": actor}), encoding="utf-8")
    os.replace(tmp, path)  # cambio atómico: es lo que vigila sportland-daily.path
    return "solicitado"


MESSAGES = {
    "solicitado": ("ok", "Listo: el cierre del día empezó. Tarda unos minutos; actualiza esta página para ver el avance."),
    "en_curso": ("warn", "Ya hay una corrida en curso; no se inició otra."),
    "ya_solicitado": ("warn", "El cierre ya se pidió hace un momento y está por empezar."),
}


def _local(ts: Any) -> str:
    value = _parse(ts)
    return value.astimezone(TZ).strftime("%d/%m %H:%M") if value else "—"


def render_cierre_panel(
    project_root: Path,
    *,
    csrf_token: str,
    return_to: str,
    message_key: str | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc)
    status = load_status(project_root)
    running = is_running(status, now=now)
    pending = pending_request(project_root, status, now=now)

    if running:
        line = f"Corriendo desde las {_local(status.get('started_at'))} · paso actual: {esc(status.get('current_step') or '—')}"
    elif pending:
        line = "Cierre solicitado; está por empezar."
    elif status:
        state = status.get("status")
        label = {"OK": "terminó bien", "FAILED": f"falló en {esc(status.get('failed_step') or '—')}"}.get(state, esc(state or "—"))
        line = f"Última corrida: {label} · {_local(status.get('finished_at') or status.get('updated_at'))}"
    else:
        line = "Todavía no hay corridas registradas."

    notice = ""
    if message_key in MESSAGES:
        tone, text = MESSAGES[message_key]
        notice = f"<div class='cd-msg cd-{tone}'>{esc(text)}</div>"

    disabled = " disabled" if running or pending else ""
    return f"""
    <style>
    .cd-panel{{margin:24px 0;padding:18px 20px;border:1px solid #dbe7f5;border-radius:16px;background:#fff;display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}}
    .cd-panel h3{{margin:0 0 4px;font-size:17px}}.cd-panel p{{margin:0;color:#667085}}
    .cd-panel button{{min-height:44px;padding:0 22px;border:0;border-radius:10px;background:#0b3d2e;color:#fff;font-weight:700;cursor:pointer}}
    .cd-panel button[disabled]{{opacity:.45;cursor:not-allowed}}
    .cd-msg{{padding:12px 14px;border-radius:12px;margin:12px 0}}.cd-ok{{background:#ecfdf3;color:#05603a}}.cd-warn{{background:#fffaeb;color:#93370d}}
    </style>
    {notice}
    <div class="cd-panel" id="cerrar-dia">
      <div>
        <h3>Cerrar el día</h3>
        <p>Cuando termines de registrar, corre el proceso diario para actualizar recomendaciones, finanzas y respaldo.</p>
        <p style="margin-top:6px"><b>{line}</b> · <a href="{esc(return_to)}#cerrar-dia">Actualizar</a></p>
      </div>
      <form method="post" action="/cerrar-dia">
        <input type="hidden" name="csrf" value="{esc(csrf_token)}">
        <input type="hidden" name="volver" value="{esc(return_to)}">
        <button type="submit"{disabled}>Cerrar el día</button>
      </form>
    </div>
    """
