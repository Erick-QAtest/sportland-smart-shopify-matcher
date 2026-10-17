"""Flujo de aprobación de publicaciones (funciones puras, sin base de datos)."""
from __future__ import annotations

from typing import Any

STATUSES = (
    "BORRADOR",
    "EN_REVISION",
    "APROBADO",
    "PROGRAMADO",
    "PUBLICADO",
    "MEDIDO",
    "DESCARTADO",
)

STATUS_LABELS = {
    "BORRADOR": "Borrador",
    "EN_REVISION": "En revisión",
    "APROBADO": "Aprobado",
    "PROGRAMADO": "Programado",
    "PUBLICADO": "Publicado",
    "MEDIDO": "Medido",
    "DESCARTADO": "Descartado",
}

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "BORRADOR": ("EN_REVISION", "DESCARTADO"),
    "EN_REVISION": ("APROBADO", "BORRADOR", "DESCARTADO"),
    "APROBADO": ("PROGRAMADO", "PUBLICADO", "BORRADOR"),
    "PROGRAMADO": ("PUBLICADO", "APROBADO", "BORRADOR"),
    "PUBLICADO": ("MEDIDO",),
    "MEDIDO": (),
    "DESCARTADO": ("BORRADOR",),
}

ACTION_LABELS = {
    ("BORRADOR", "EN_REVISION"): "Enviar a revisión",
    ("EN_REVISION", "APROBADO"): "Aprobar",
    ("EN_REVISION", "BORRADOR"): "Rechazar (vuelve a borrador)",
    ("APROBADO", "PROGRAMADO"): "Marcar como programado",
    ("APROBADO", "PUBLICADO"): "Marcar como publicado",
    ("PROGRAMADO", "PUBLICADO"): "Marcar como publicado",
    ("PROGRAMADO", "APROBADO"): "Quitar de programado",
    ("APROBADO", "BORRADOR"): "Reabrir para editar (pierde la aprobación)",
    ("PROGRAMADO", "BORRADOR"): "Reabrir para editar (pierde la aprobación)",
    ("PUBLICADO", "MEDIDO"): "Registrar resultado",
    ("BORRADOR", "DESCARTADO"): "Descartar",
    ("EN_REVISION", "DESCARTADO"): "Descartar",
    ("DESCARTADO", "BORRADOR"): "Restaurar como borrador",
}

# Estados en los que se puede cambiar el contenido. Después de aprobar, editar exige
# reabrir (y por lo tanto volver a aprobar).
EDITABLE = {"BORRADOR", "EN_REVISION"}
# Estados en los que se puede mover la fecha sin perder la aprobación.
RESCHEDULABLE = {"BORRADOR", "EN_REVISION", "APROBADO", "PROGRAMADO"}
# Estados que cuentan como trabajo vivo en vistas de pendientes.
OPEN = {"BORRADOR", "EN_REVISION", "APROBADO", "PROGRAMADO"}


def normalize_status(value: Any) -> str:
    raw = str(value or "").strip().upper().replace(" ", "_")
    return raw if raw in STATUSES else "BORRADOR"


def allowed_targets(current: str) -> tuple[str, ...]:
    return TRANSITIONS.get(normalize_status(current), ())


def transition_errors(item: dict[str, Any], target: str, *, note: str = "") -> list[str]:
    """Errores que impiden mover `item` a `target`. Lista vacía = permitido."""
    current = normalize_status(item.get("workflow_status"))
    target = str(target or "").strip().upper()
    note = str(note or "").strip()
    errors: list[str] = []

    if target not in STATUSES:
        return [f"Estado desconocido: {target or '(vacío)'}."]
    if target not in TRANSITIONS.get(current, ()):
        return [f"No se puede pasar de {STATUS_LABELS[current]} a {STATUS_LABELS[target]}."]

    if target == "EN_REVISION":
        if not str(item.get("topic") or "").strip():
            errors.append("Falta el tema de la publicación.")
        if not str(item.get("channel") or "").strip():
            errors.append("Falta el canal.")
        if not item.get("scheduled_date"):
            errors.append("Falta la fecha.")
    if current == "EN_REVISION" and target == "BORRADOR" and not note:
        errors.append("Para rechazar escribe qué hay que cambiar.")
    if target == "PUBLICADO" and not item.get("approved_at"):
        errors.append("No se puede publicar sin una aprobación registrada.")
    if target == "MEDIDO" and not note:
        errors.append("Escribe el resultado (aunque sea \"sin ventas visibles\").")
    return errors


def edit_errors(item: dict[str, Any]) -> list[str]:
    status = normalize_status(item.get("workflow_status"))
    if status in EDITABLE:
        return []
    if status in {"APROBADO", "PROGRAMADO"}:
        return ["Ya está aprobada. Para cambiar el contenido, reábrela (tendrá que aprobarse de nuevo)."]
    return [f"Una publicación en estado {STATUS_LABELS[status]} ya no se edita."]


def reschedule_errors(item: dict[str, Any]) -> list[str]:
    status = normalize_status(item.get("workflow_status"))
    if status in RESCHEDULABLE:
        return []
    return [f"Una publicación en estado {STATUS_LABELS[status]} ya no se reprograma."]
