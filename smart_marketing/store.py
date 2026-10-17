"""Acceso a datos de Marketing Intelligence (v8.0).

Cada escritura deja rastro en `marketing_change_log` (antes, después, quién, cuándo).
Nada aquí publica, envía mensajes ni escribe en Shopify.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import re
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection
from psycopg.types.json import Jsonb

from smart_marketing import templates, workflow

TZ = ZoneInfo("America/Mexico_City")

CHANNELS = (
    "WhatsApp comunidad",
    "Instagram",
    "Facebook página",
    "Facebook grupos",
    "YouTube",
    "TikTok",
    "Google Business Profile",
    "Blog SEO",
)

# Filtro por plataforma sobre el texto libre del canal (el CSV usa "IG/FB", "IG Reel + TikTok"...).
PLATFORMS = {
    "whatsapp": ("WhatsApp", r"\mwhatsapp\M"),
    "instagram": ("Instagram", r"\m(ig|instagram|stories)\M"),
    "facebook": ("Facebook", r"\m(fb|facebook)\M"),
    "youtube": ("YouTube", r"\myoutube\M"),
    "tiktok": ("TikTok", r"\mtiktok\M"),
    "google": ("Google Business", r"\mgoogle\M"),
    "blog": ("Blog / SEO", r"\m(blog|seo)\M"),
}

CONTENT_TYPES = {
    "PRODUCTO": "Producto",
    "ENCUESTA": "Encuesta",
    "OFERTA": "Oferta",
    "EDUCATIVO": "Educativo",
    "PAGOS": "Pagos",
    "OTRO": "Otro",
}

OBJECTIVES = ("Visita a tienda", "Compra online", "Participación", "Educación / SEO", "Retención")
PRIORITIES = ("MUY ALTA", "ALTA", "MEDIA", "BAJA")

ITEM_FIELDS = (
    "scheduled_date", "suggested_time", "channel", "community_code", "content_type",
    "objective", "campaign_id", "pillar", "topic", "hook", "copy_text", "cta", "kpi",
    "priority", "shopify_product_id", "shopify_variant_ids",
)


def today_mx() -> date:
    return datetime.now(TZ).date()


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def log_change(
    conn: Connection,
    *,
    entity_type: str,
    entity_key: str,
    action: str,
    actor: str,
    from_status: str | None = None,
    to_status: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    note: str | None = None,
) -> None:
    conn.execute(
        """INSERT INTO marketing_change_log(entity_type, entity_key, action, from_status, to_status,
               before_data, after_data, note, actor)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            entity_type, str(entity_key), action, from_status, to_status,
            Jsonb({k: _jsonable(v) for k, v in (before or {}).items()}) if before is not None else None,
            Jsonb({k: _jsonable(v) for k, v in (after or {}).items()}) if after is not None else None,
            (note or "").strip() or None, actor,
        ),
    )


# ---------------------------------------------------------------- formularios

def _v(form: dict[str, list[str]], name: str) -> str:
    return (form.get(name) or [""])[0].strip()


def parse_item_form(form: dict[str, list[str]]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    data: dict[str, Any] = {}

    raw_date = _v(form, "scheduled_date")
    try:
        data["scheduled_date"] = date.fromisoformat(raw_date)
    except ValueError:
        errors.append("Fecha inválida (usa AAAA-MM-DD).")
        data["scheduled_date"] = None

    raw_time = _v(form, "suggested_time")
    if raw_time and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", raw_time):
        errors.append("Hora inválida (usa HH:MM).")
    data["suggested_time"] = raw_time or None

    data["channel"] = _v(form, "channel")[:120]
    if not data["channel"]:
        errors.append("Falta el canal.")
    community = _v(form, "community_code")
    if community and community not in templates.COMMUNITIES:
        errors.append("Comunidad desconocida.")
    data["community_code"] = community or None

    content_type = _v(form, "content_type").upper()
    if content_type and content_type not in CONTENT_TYPES:
        errors.append("Tipo de contenido desconocido.")
    data["content_type"] = content_type or None
    data["objective"] = _v(form, "objective")[:80] or None

    raw_campaign = _v(form, "campaign_id")
    if raw_campaign:
        if raw_campaign.isdigit():
            data["campaign_id"] = int(raw_campaign)
        else:
            errors.append("Campaña inválida.")
            data["campaign_id"] = None
    else:
        data["campaign_id"] = None

    data["topic"] = _v(form, "topic")[:300]
    if not data["topic"]:
        errors.append("Falta el tema.")
    for name, limit in (("pillar", 120), ("hook", 300), ("cta", 120), ("kpi", 120)):
        data[name] = _v(form, name)[:limit] or None
    data["copy_text"] = _v(form, "copy_text")[:4000] or None

    priority = _v(form, "priority").upper()
    if priority and priority not in PRIORITIES:
        errors.append("Prioridad desconocida.")
    data["priority"] = priority or None

    product = _v(form, "shopify_product_id")
    if product and not re.fullmatch(r"(gid://shopify/Product/)?\d+", product):
        errors.append("ID de producto de Shopify inválido.")
    data["shopify_product_id"] = product or None

    variants = [v.strip() for v in _v(form, "shopify_variant_ids").replace("\n", ",").split(",") if v.strip()]
    if any(not re.fullmatch(r"(gid://shopify/ProductVariant/)?\d+", v) for v in variants):
        errors.append("IDs de variante de Shopify inválidos.")
    data["shopify_variant_ids"] = variants or None
    return data, errors


# ---------------------------------------------------------------- calendario

def list_items(
    conn: Connection,
    start: date,
    end: date,
    filters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    filters = filters or {}
    where = ["i.scheduled_date BETWEEN %s AND %s"]
    params: list[Any] = [start, end]

    platform = PLATFORMS.get(filters.get("plataforma", ""))
    if platform:
        where.append("COALESCE(i.channel, '') ~* %s")
        params.append(platform[1])
    if filters.get("comunidad") in templates.COMMUNITIES:
        where.append("i.community_code = %s")
        params.append(filters["comunidad"])
    if filters.get("tipo") in CONTENT_TYPES:
        where.append("i.content_type = %s")
        params.append(filters["tipo"])
    if (filters.get("campana") or "").isdigit():
        where.append("i.campaign_id = %s")
        params.append(int(filters["campana"]))
    if filters.get("estado") in workflow.STATUSES:
        where.append("i.workflow_status = %s")
        params.append(filters["estado"])
    elif filters.get("estado") == "ABIERTOS":
        where.append("i.workflow_status = ANY(%s)")
        params.append(list(workflow.OPEN))
    if filters.get("objetivo") in OBJECTIVES:
        where.append("i.objective = %s")
        params.append(filters["objetivo"])

    return [dict(r) for r in conn.execute(
        f"""SELECT i.*, c.name AS campaign_name, c.code AS campaign_code
            FROM marketing_calendar_items i
            LEFT JOIN marketing_campaigns c ON c.campaign_id = i.campaign_id
            WHERE {' AND '.join(where)}
            ORDER BY i.scheduled_date, NULLIF(i.suggested_time, '') NULLS LAST,
              CASE i.priority WHEN 'MUY ALTA' THEN 1 WHEN 'ALTA' THEN 2 WHEN 'MEDIA' THEN 3 ELSE 4 END,
              i.calendar_key""",
        params,
    ).fetchall()]


def items_in_review(conn: Connection, limit: int = 50) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT i.*, c.name AS campaign_name FROM marketing_calendar_items i
           LEFT JOIN marketing_campaigns c ON c.campaign_id = i.campaign_id
           WHERE i.workflow_status = 'EN_REVISION'
           ORDER BY i.scheduled_date LIMIT %s""",
        (limit,),
    ).fetchall()]


def get_item(conn: Connection, key: str, *, for_update: bool = False) -> dict[str, Any] | None:
    row = conn.execute(
        f"""SELECT i.*, c.name AS campaign_name, c.code AS campaign_code
            FROM marketing_calendar_items i
            LEFT JOIN marketing_campaigns c ON c.campaign_id = i.campaign_id
            WHERE i.calendar_key = %s {'FOR UPDATE OF i' if for_update else ''}""",
        (key,),
    ).fetchone()
    return dict(row) if row else None


def item_log(conn: Connection, key: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT * FROM marketing_change_log
           WHERE entity_type = 'CALENDARIO' AND entity_key = %s
           ORDER BY changed_at DESC, change_id DESC""",
        (key,),
    ).fetchall()]


def create_item(conn: Connection, data: dict[str, Any], *, actor: str) -> str:
    key = "mi-" + uuid.uuid4().hex[:20]
    values = {name: data.get(name) for name in ITEM_FIELDS}
    day = values["scheduled_date"]
    values["weekday_name"] = templates.WEEKDAYS[day.weekday()] if day else None
    with conn.transaction():
        conn.execute(
            """INSERT INTO marketing_calendar_items(
                 calendar_key, scheduled_date, weekday_name, suggested_time, channel, community_code,
                 content_type, objective, campaign_id, pillar, topic, hook, copy_text, cta, kpi,
                 priority, shopify_product_id, shopify_variant_ids, status, workflow_status,
                 source_name, created_by)
               VALUES (%(key)s, %(scheduled_date)s, %(weekday_name)s, %(suggested_time)s, %(channel)s,
                 %(community_code)s, %(content_type)s, %(objective)s, %(campaign_id)s, %(pillar)s,
                 %(topic)s, %(hook)s, %(copy_text)s, %(cta)s, %(kpi)s, %(priority)s,
                 %(shopify_product_id)s, %(shopify_variant_ids)s, 'PLANIFICADO', 'BORRADOR',
                 'portal_marketing_v80', %(actor)s)""",
            {**values, "key": key, "actor": actor},
        )
        log_change(conn, entity_type="CALENDARIO", entity_key=key, action="crear", actor=actor,
                   to_status="BORRADOR", after=values)
    return key


def update_item(conn: Connection, key: str, data: dict[str, Any], *, actor: str) -> list[str]:
    with conn.transaction():
        item = get_item(conn, key, for_update=True)
        if not item:
            return ["No existe esa publicación."]
        errors = workflow.edit_errors(item)
        if errors:
            return errors
        changed = {k: data.get(k) for k in ITEM_FIELDS if data.get(k) != item.get(k)}
        if not changed:
            return []
        if "scheduled_date" in changed and changed["scheduled_date"]:
            changed["weekday_name"] = templates.WEEKDAYS[changed["scheduled_date"].weekday()]
        sets = ", ".join(f"{k} = %({k})s" for k in changed)
        conn.execute(
            f"UPDATE marketing_calendar_items SET {sets}, updated_at = now() WHERE calendar_key = %(key)s",
            {**changed, "key": key},
        )
        log_change(conn, entity_type="CALENDARIO", entity_key=key, action="editar", actor=actor,
                   before={k: item.get(k) for k in changed}, after=changed)
    return []


def transition_item(
    conn: Connection,
    key: str,
    target: str,
    *,
    actor: str,
    note: str = "",
    published_ref: str = "",
) -> list[str]:
    target = str(target or "").strip().upper()
    with conn.transaction():
        item = get_item(conn, key, for_update=True)
        if not item:
            return ["No existe esa publicación."]
        errors = workflow.transition_errors(item, target, note=note)
        if errors:
            return errors
        current = workflow.normalize_status(item.get("workflow_status"))
        sets = ["workflow_status = %(target)s", "updated_at = now()"]
        if target == "APROBADO" and current == "EN_REVISION":
            sets += ["approved_by = %(actor)s", "approved_at = now()"]
        if target == "BORRADOR":
            sets += ["approved_by = NULL", "approved_at = NULL"]
        if target == "PUBLICADO":
            sets += ["published_at = now()", "published_ref = %(ref)s"]
        if target == "MEDIDO":
            sets += ["measured_at = now()", "result_notes = %(note)s"]
        conn.execute(
            f"UPDATE marketing_calendar_items SET {', '.join(sets)} WHERE calendar_key = %(key)s",
            {"target": target, "actor": actor, "ref": (published_ref or "").strip()[:500] or None,
             "note": (note or "").strip()[:2000], "key": key},
        )
        log_change(conn, entity_type="CALENDARIO", entity_key=key, action="estado", actor=actor,
                   from_status=current, to_status=target, note=note,
                   after={"published_ref": published_ref} if published_ref else None)
    return []


def reschedule_item(
    conn: Connection,
    key: str,
    new_date: date,
    new_time: str | None,
    *,
    actor: str,
) -> list[str]:
    if new_time and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", new_time):
        return ["Hora inválida (usa HH:MM)."]
    with conn.transaction():
        item = get_item(conn, key, for_update=True)
        if not item:
            return ["No existe esa publicación."]
        errors = workflow.reschedule_errors(item)
        if errors:
            return errors
        before = {"scheduled_date": item["scheduled_date"], "suggested_time": item.get("suggested_time")}
        after = {"scheduled_date": new_date, "suggested_time": new_time or item.get("suggested_time")}
        conn.execute(
            """UPDATE marketing_calendar_items
               SET scheduled_date = %s, weekday_name = %s, suggested_time = %s, updated_at = now()
               WHERE calendar_key = %s""",
            (new_date, templates.WEEKDAYS[new_date.weekday()], after["suggested_time"], key),
        )
        log_change(conn, entity_type="CALENDARIO", entity_key=key, action="reprogramar", actor=actor,
                   before=before, after=after,
                   note="La aprobación se conserva." if item.get("approved_at") else None)
    return []


# ---------------------------------------------------------------- campañas

def list_campaigns(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT c.*,
                  COUNT(i.calendar_key) AS items,
                  COUNT(i.calendar_key) FILTER (WHERE i.workflow_status = 'BORRADOR') AS borradores,
                  COUNT(i.calendar_key) FILTER (WHERE i.workflow_status = 'EN_REVISION') AS en_revision,
                  COUNT(i.calendar_key) FILTER (WHERE i.workflow_status IN ('APROBADO', 'PROGRAMADO')) AS aprobados,
                  COUNT(i.calendar_key) FILTER (WHERE i.workflow_status IN ('PUBLICADO', 'MEDIDO')) AS publicados
           FROM marketing_campaigns c
           LEFT JOIN marketing_calendar_items i ON i.campaign_id = c.campaign_id
           GROUP BY c.campaign_id
           ORDER BY c.starts_on, c.campaign_id"""
    ).fetchall()]


def get_campaign(conn: Connection, campaign_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM marketing_campaigns WHERE campaign_id = %s", (campaign_id,)).fetchone()
    return dict(row) if row else None


def campaigns_on(conn: Connection, day: date) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT * FROM marketing_campaigns
           WHERE %s BETWEEN starts_on AND ends_on AND status IN ('PLANEADA', 'ACTIVA')
           ORDER BY starts_on""",
        (day,),
    ).fetchall()]


def parse_campaign_form(form: dict[str, list[str]]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    data: dict[str, Any] = {
        "code": _v(form, "code").upper()[:60],
        "name": _v(form, "name")[:160],
        "objective": _v(form, "objective")[:200] or None,
        "theme": _v(form, "theme")[:300] or None,
        "status": (_v(form, "status") or "PLANEADA").upper(),
        "notes": _v(form, "notes")[:2000] or None,
    }
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{2,59}", data["code"] or ""):
        errors.append("Código inválido (letras, números y guiones; ej. 2027-01-REYES).")
    if not data["name"]:
        errors.append("Falta el nombre.")
    if data["status"] not in {"PLANEADA", "ACTIVA", "CERRADA", "CANCELADA"}:
        errors.append("Estado de campaña desconocido.")
    for name in ("starts_on", "ends_on"):
        try:
            data[name] = date.fromisoformat(_v(form, name))
        except ValueError:
            data[name] = None
            errors.append("Fechas inválidas (usa AAAA-MM-DD).")
    if data.get("starts_on") and data.get("ends_on") and data["ends_on"] < data["starts_on"]:
        errors.append("La campaña termina antes de empezar.")
    for name, label in (("budget_mxn", "presupuesto"), ("sales_goal_mxn", "meta de ventas")):
        raw = _v(form, name).replace("$", "").replace(",", "")
        if not raw:
            data[name] = None
            continue
        try:
            value = Decimal(raw)
            if value < 0:
                raise ValueError
            data[name] = value
        except Exception:
            data[name] = None
            errors.append(f"{label.capitalize()} inválido.")
    return data, list(dict.fromkeys(errors))


def save_campaign(
    conn: Connection,
    data: dict[str, Any],
    *,
    actor: str,
    campaign_id: int | None = None,
) -> tuple[int | None, list[str]]:
    fields = ("code", "name", "objective", "theme", "starts_on", "ends_on", "status",
              "budget_mxn", "sales_goal_mxn", "notes")
    with conn.transaction():
        clash = conn.execute(
            "SELECT campaign_id FROM marketing_campaigns WHERE code = %s AND campaign_id <> COALESCE(%s, -1)",
            (data["code"], campaign_id),
        ).fetchone()
        if clash:
            return None, ["Ya existe una campaña con ese código."]
        if campaign_id is None:
            row = conn.execute(
                f"""INSERT INTO marketing_campaigns({', '.join(fields)}, created_by)
                    VALUES ({', '.join('%(' + f + ')s' for f in fields)}, %(actor)s)
                    RETURNING campaign_id""",
                {**{f: data.get(f) for f in fields}, "actor": actor},
            ).fetchone()
            new_id = int(row["campaign_id"])
            log_change(conn, entity_type="CAMPANA", entity_key=str(new_id), action="crear", actor=actor,
                       after={f: data.get(f) for f in fields})
            return new_id, []
        before = get_campaign(conn, campaign_id)
        if not before:
            return None, ["No existe esa campaña."]
        changed = {f: data.get(f) for f in fields if data.get(f) != before.get(f)}
        if changed:
            sets = ", ".join(f"{k} = %({k})s" for k in changed)
            conn.execute(
                f"UPDATE marketing_campaigns SET {sets}, updated_at = now() WHERE campaign_id = %(id)s",
                {**changed, "id": campaign_id},
            )
            log_change(conn, entity_type="CAMPANA", entity_key=str(campaign_id), action="editar",
                       actor=actor, before={k: before.get(k) for k in changed}, after=changed)
        return campaign_id, []


def generate_campaign_drafts(
    conn: Connection,
    campaign_id: int,
    communities: list[str],
    *,
    actor: str,
) -> tuple[int, int, list[str]]:
    """Crea los borradores de la semana tipo. Nunca sobrescribe lo ya creado o editado."""
    communities = [c for c in communities if c in templates.WEEK_TEMPLATES]
    if not communities:
        return 0, 0, ["Elige al menos una comunidad."]
    campaign = get_campaign(conn, campaign_id)
    if not campaign:
        return 0, 0, ["No existe esa campaña."]
    drafts = templates.build_drafts(campaign, communities)
    inserted = 0
    with conn.transaction():
        for d in drafts:
            row = conn.execute(
                """INSERT INTO marketing_calendar_items(
                     calendar_key, scheduled_date, weekday_name, pillar, channel, community_code,
                     content_type, objective, topic, cta, priority, campaign_id, status,
                     workflow_status, source_name, created_by)
                   VALUES (%(calendar_key)s, %(scheduled_date)s, %(weekday_name)s, %(pillar)s,
                     %(channel)s, %(community_code)s, %(content_type)s, %(objective)s, %(topic)s,
                     %(cta)s, %(priority)s, %(campaign_id)s, 'PLANIFICADO', 'BORRADOR',
                     'semana_tipo_v80', %(actor)s)
                   ON CONFLICT (calendar_key) DO NOTHING
                   RETURNING calendar_key""",
                {**d, "actor": actor},
            ).fetchone()
            if row:
                inserted += 1
        if inserted:
            log_change(conn, entity_type="CAMPANA", entity_key=str(campaign_id), action="generar_borradores",
                       actor=actor, after={"comunidades": communities, "creados": inserted,
                                           "ya_existian": len(drafts) - inserted})
    return inserted, len(drafts) - inserted, []


def same_month_last_year(conn: Connection, day: date) -> Decimal | None:
    try:
        with conn.transaction():
            row = conn.execute(
                "SELECT total_mxn FROM finance_monthly_sales WHERE year = %s AND month = %s",
                (day.year - 1, day.month),
            ).fetchone()
    except Exception:
        return None
    return row["total_mxn"] if row else None


# ---------------------------------------------------------------- encuestas

def list_polls(conn: Connection) -> list[dict[str, Any]]:
    polls = [dict(r) for r in conn.execute(
        """SELECT p.*, c.name AS campaign_name FROM marketing_polls p
           LEFT JOIN marketing_campaigns c ON c.campaign_id = p.follow_up_campaign_id
           ORDER BY p.asked_on DESC NULLS LAST, p.poll_id DESC"""
    ).fetchall()]
    options = [dict(r) for r in conn.execute(
        "SELECT * FROM marketing_poll_options ORDER BY poll_id, position"
    ).fetchall()]
    by_poll: dict[int, list[dict[str, Any]]] = {}
    for o in options:
        by_poll.setdefault(o["poll_id"], []).append(o)
    for p in polls:
        p["options"] = by_poll.get(p["poll_id"], [])
    return polls


def parse_poll_form(form: dict[str, list[str]]) -> tuple[dict[str, Any], list[str]]:
    from smart_marketing.polls import parse_option_rows

    errors: list[str] = []
    data: dict[str, Any] = {
        "question": _v(form, "question")[:300],
        "category": (_v(form, "category") or "OTRO").upper(),
        "community_code": _v(form, "community_code") or None,
        "channel": _v(form, "channel")[:80] or None,
        "multi_select": _v(form, "multi_select") in {"1", "on", "true", "si", "sí"},
        "evidence_ref": _v(form, "evidence_ref")[:500] or None,
        "related_brand": _v(form, "related_brand")[:80] or None,
        "related_product": _v(form, "related_product")[:160] or None,
        "conclusion": _v(form, "conclusion")[:2000] or None,
        "confidence": _v(form, "confidence").upper() or None,
        "outcome_notes": _v(form, "outcome_notes")[:2000] or None,
    }
    if not data["question"]:
        errors.append("Falta la pregunta.")
    if data["category"] not in {"PRECIO", "COMODIDAD", "MARCA", "MODELO", "TALLA", "ESTILO", "USO", "OTRO"}:
        errors.append("Categoría desconocida.")
    if data["community_code"] and data["community_code"] not in templates.COMMUNITIES:
        errors.append("Comunidad desconocida.")
    if data["confidence"] and data["confidence"] not in {"ALTA", "MEDIA", "BAJA"}:
        errors.append("Confianza desconocida.")
    raw_date = _v(form, "asked_on")
    try:
        data["asked_on"] = date.fromisoformat(raw_date) if raw_date else None
    except ValueError:
        data["asked_on"] = None
        errors.append("Fecha inválida (usa AAAA-MM-DD).")
    raw_voters = _v(form, "unique_voters")
    if raw_voters:
        if raw_voters.isdigit():
            data["unique_voters"] = int(raw_voters)
        else:
            data["unique_voters"] = None
            errors.append("Votantes únicos debe ser un número entero (o déjalo vacío si no lo sabes).")
    else:
        data["unique_voters"] = None
    raw_campaign = _v(form, "follow_up_campaign_id")
    data["follow_up_campaign_id"] = int(raw_campaign) if raw_campaign.isdigit() else None
    options, option_errors = parse_option_rows(form)
    return {**data, "options": options}, errors + option_errors


def save_poll(conn: Connection, data: dict[str, Any], *, actor: str) -> int:
    fields = ("question", "category", "community_code", "channel", "multi_select", "asked_on",
              "unique_voters", "evidence_ref", "related_brand", "related_product", "conclusion",
              "confidence", "follow_up_campaign_id", "outcome_notes")
    with conn.transaction():
        row = conn.execute(
            f"""INSERT INTO marketing_polls({', '.join(fields)}, created_by)
                VALUES ({', '.join('%(' + f + ')s' for f in fields)}, %(actor)s)
                RETURNING poll_id""",
            {**{f: data.get(f) for f in fields}, "actor": actor},
        ).fetchone()
        poll_id = int(row["poll_id"])
        for o in data["options"]:
            conn.execute(
                """INSERT INTO marketing_poll_options(poll_id, position, label, price_min_mxn, price_max_mxn, selections)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (poll_id, o["position"], o["label"], o["price_min_mxn"], o["price_max_mxn"], o["selections"]),
            )
        log_change(conn, entity_type="ENCUESTA", entity_key=str(poll_id), action="crear", actor=actor,
                   after={**{f: data.get(f) for f in fields}, "opciones": data["options"]})
    return poll_id


# ---------------------------------------------------------------- biblioteca

ASSET_KINDS = {"FOTO": "Foto", "VIDEO": "Video", "CREATIVO": "Creativo", "COPY": "Copy", "OTRO": "Otro"}


def list_assets(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT a.*, COUNT(ia.calendar_key) AS uses
           FROM marketing_assets a
           LEFT JOIN marketing_item_assets ia ON ia.asset_id = a.asset_id
           GROUP BY a.asset_id ORDER BY a.created_at DESC, a.asset_id DESC"""
    ).fetchall()]


def parse_asset_form(form: dict[str, list[str]]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    data = {
        "title": _v(form, "title")[:200],
        "kind": (_v(form, "kind") or "FOTO").upper(),
        "location_url": _v(form, "location_url")[:1000] or None,
        "shopify_product_id": _v(form, "shopify_product_id")[:80] or None,
        "brand": _v(form, "brand")[:80] or None,
        "notes": _v(form, "notes")[:2000] or None,
    }
    if not data["title"]:
        errors.append("Falta el título.")
    if data["kind"] not in ASSET_KINDS:
        errors.append("Tipo de recurso desconocido.")
    if data["location_url"] and not re.match(r"https?://", data["location_url"]):
        errors.append("La ubicación debe ser un enlace http(s).")
    return data, errors


def save_asset(conn: Connection, data: dict[str, Any], *, actor: str) -> int:
    fields = ("title", "kind", "location_url", "shopify_product_id", "brand", "notes")
    with conn.transaction():
        row = conn.execute(
            f"""INSERT INTO marketing_assets({', '.join(fields)}, created_by)
                VALUES ({', '.join('%(' + f + ')s' for f in fields)}, %(actor)s) RETURNING asset_id""",
            {**{f: data.get(f) for f in fields}, "actor": actor},
        ).fetchone()
        asset_id = int(row["asset_id"])
        log_change(conn, entity_type="RECURSO", entity_key=str(asset_id), action="crear", actor=actor,
                   after={f: data.get(f) for f in fields})
    return asset_id


def item_assets(conn: Connection, key: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        """SELECT a.*, ia.format_note FROM marketing_item_assets ia
           JOIN marketing_assets a ON a.asset_id = ia.asset_id
           WHERE ia.calendar_key = %s ORDER BY a.title""",
        (key,),
    ).fetchall()]


def link_asset(conn: Connection, key: str, asset_id: int, *, actor: str, note: str = "") -> list[str]:
    with conn.transaction():
        if not get_item(conn, key):
            return ["No existe esa publicación."]
        if not conn.execute("SELECT 1 FROM marketing_assets WHERE asset_id = %s", (asset_id,)).fetchone():
            return ["No existe ese recurso."]
        row = conn.execute(
            """INSERT INTO marketing_item_assets(calendar_key, asset_id, format_note) VALUES (%s, %s, %s)
               ON CONFLICT DO NOTHING RETURNING asset_id""",
            (key, asset_id, note.strip()[:300] or None),
        ).fetchone()
        if row:
            log_change(conn, entity_type="CALENDARIO", entity_key=key, action="agregar_recurso", actor=actor,
                       after={"asset_id": asset_id, "formato": note})
    return []
