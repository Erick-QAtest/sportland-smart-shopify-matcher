"""Lectura honesta de encuestas (funciones puras).

En una encuesta de opción múltiple cada persona puede marcar varias opciones, así que la
suma de selecciones no es el número de participantes. Solo se habla de "votantes" cuando
se conoce el dato.
"""
from __future__ import annotations

from typing import Any


def summarize(poll: dict[str, Any], options: list[dict[str, Any]]) -> dict[str, Any]:
    selections = [max(0, int(o.get("selections") or 0)) for o in options]
    total = sum(selections)
    multi = bool(poll.get("multi_select"))
    voters = poll.get("unique_voters")
    voters = int(voters) if voters not in (None, "") else None
    if voters is None and not multi:
        voters = total  # en opción única, cada selección es una persona

    rows = []
    for option, count in zip(options, selections):
        rows.append({
            **option,
            "selections": count,
            "share_of_selections": (count / total) if total else None,
            "share_of_voters": (count / voters) if voters else None,
        })
    top = max(rows, key=lambda r: r["selections"]) if rows and total else None

    warnings = []
    if multi and poll.get("unique_voters") in (None, ""):
        warnings.append(
            f"Opción múltiple sin votantes conocidos: {total} selecciones, no {total} personas."
        )
    if not multi and poll.get("unique_voters") not in (None, "") and total != int(poll["unique_voters"]):
        warnings.append("En opción única las selecciones deberían sumar el número de votantes.")
    if total and total < 30:
        warnings.append("Muestra chica: úsala como señal, no como conclusión.")

    return {
        "total_selections": total,
        "voters": voters,
        "voters_known": poll.get("unique_voters") not in (None, "") or not multi,
        "options": rows,
        "top_label": top["label"] if top else None,
        "warnings": warnings,
    }


def parse_option_rows(form: dict[str, list[str]], max_rows: int = 8) -> tuple[list[dict[str, Any]], list[str]]:
    """Lee opcion_label_i / opcion_sel_i / opcion_min_i / opcion_max_i del formulario."""
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    def value(name: str) -> str:
        return (form.get(name) or [""])[0].strip()

    for i in range(max_rows):
        label = value(f"opcion_label_{i}")
        raw_sel = value(f"opcion_sel_{i}")
        raw_min = value(f"opcion_min_{i}")
        raw_max = value(f"opcion_max_{i}")
        if not label and not raw_sel:
            continue
        if not label:
            errors.append(f"Opción {i + 1}: falta el texto.")
            continue
        try:
            sel = int(raw_sel or "0")
            if sel < 0:
                raise ValueError
        except ValueError:
            errors.append(f"Opción {i + 1}: las selecciones deben ser un número entero ≥ 0.")
            continue

        def money(raw: str, label_txt: str):
            if not raw:
                return None
            try:
                return float(raw.replace("$", "").replace(",", ""))
            except ValueError:
                errors.append(f"Opción {i + 1}: {label_txt} inválido.")
                return None

        rows.append({
            "position": len(rows) + 1,
            "label": label[:200],
            "selections": sel,
            "price_min_mxn": money(raw_min, "precio mínimo"),
            "price_max_mxn": money(raw_max, "precio máximo"),
        })
    if len(rows) < 2 and not errors:
        errors.append("Una encuesta necesita al menos 2 opciones.")
    return rows, errors
