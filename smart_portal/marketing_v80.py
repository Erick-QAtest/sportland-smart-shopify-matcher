"""Marketing Intelligence v8.0 en el portal: calendario con aprobación, campañas,
encuestas y biblioteca.

S-Mart planea y registra; una persona aprueba y publica. Nada aquí publica, envía
WhatsApp ni escribe en Shopify.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from smart_marketing import polls as poll_logic
from smart_marketing import store, templates, workflow
from smart_portal.portal_v60 import base_page, esc, money

SHOPIFY_ADMIN = "https://admin.shopify.com/store/sportland-sales"

GET_ROUTES = {
    "/marketing",
    "/marketing/calendario",
    "/marketing/item",
    "/marketing/nuevo",
    "/marketing/campanas",
    "/marketing/encuestas",
    "/marketing/biblioteca",
}
POST_ROUTES = {
    "/marketing/item/guardar",
    "/marketing/item/estado",
    "/marketing/item/reprogramar",
    "/marketing/item/recurso",
    "/marketing/campanas/guardar",
    "/marketing/campanas/generar",
    "/marketing/encuestas/guardar",
    "/marketing/biblioteca/guardar",
}

MESSAGES = {
    "creado": "Publicación creada como borrador.",
    "guardado": "Cambios guardados.",
    "estado": "Estado actualizado.",
    "reprogramado": "Fecha actualizada. La aprobación, si había, se conserva.",
    "recurso": "Recurso agregado a la publicación.",
    "campana": "Campaña guardada.",
    "generado": "Borradores de la semana tipo creados.",
    "encuesta": "Encuesta registrada.",
    "biblioteca": "Recurso guardado en la biblioteca.",
}

COMMUNITY_SHORT = {"WA_LOCAL": "WA Local", "WA_ONLINE": "WA Online", "WA_SPORTLAND_PUNTO": "WA «Sportland.»"}
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
DOW = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")

MI_CSS = """
<style>
.subnav{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px}
.subnav a{padding:8px 12px;border-radius:10px;font-size:12px;font-weight:800;color:#344054;background:#eef2f6}
.subnav a.on{background:var(--blue);color:#fff}
.chip{display:inline-block;padding:3px 8px;border-radius:999px;font-size:10px;font-weight:850;white-space:nowrap}
.st-BORRADOR{background:#f2f4f7;color:#475467}.st-EN_REVISION{background:#fff7ed;color:#b54708}
.st-APROBADO{background:#eff8ff;color:#175cd3}.st-PROGRAMADO{background:#eef4ff;color:#3538cd}
.st-PUBLICADO{background:#ecfdf3;color:#067647}.st-MEDIDO{background:#dcfae6;color:#05603a}
.st-DESCARTADO{background:#fff1f0;color:#b42318;text-decoration:line-through}
.cal{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
.cal .dow{font-size:10px;font-weight:850;text-transform:uppercase;color:#475467;padding:0 4px}
.day{background:#fff;border:1px solid var(--line);border-radius:12px;padding:8px;min-height:96px}
.day.out{opacity:.45}.day.today{border:2px solid var(--blue)}
.day .num{font-size:12px;font-weight:850;margin-bottom:6px;display:flex;justify-content:space-between}
.card{display:block;border:1px solid #edf0f4;border-left:4px solid #d0d5dd;border-radius:9px;padding:7px;margin-bottom:6px;font-size:11px;line-height:1.35;background:#fcfcfd}
.card:hover{border-color:var(--blue)}
.card.t-PRODUCTO{border-left-color:#175cd3}.card.t-OFERTA{border-left-color:#d92d20}.card.t-ENCUESTA{border-left-color:#7a5af8}
.card.t-EDUCATIVO{border-left-color:#067647}.card.t-PAGOS{border-left-color:#b54708}
.card .meta{color:#667085;font-size:10px}
.mini{display:block;font-size:10px;padding:3px 5px;border-radius:6px;background:#f2f4f7;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:12px}
.filters label{font-size:10px;font-weight:800;color:#475467;display:flex;flex-direction:column;gap:3px}
select,input,textarea{font:inherit;font-size:13px;padding:8px 9px;border:1px solid #d0d5dd;border-radius:9px;background:#fff;max-width:100%}
textarea{width:100%;min-height:90px}
.btn{display:inline-block;border:0;border-radius:10px;padding:9px 13px;font-size:12px;font-weight:850;cursor:pointer;background:var(--navy);color:#fff}
.btn.sec{background:#fff;color:#344054;border:1px solid #d0d5dd}.btn.warn{background:#b42318}
.btn.sm{padding:6px 9px;font-size:11px}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.form-grid label{display:flex;flex-direction:column;gap:4px;font-size:11px;font-weight:800;color:#344054}
.form-grid .wide{grid-column:1/-1}
.navrow{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.navrow h2{margin:0;font-size:17px}
.err{background:#fff1f0;border:1px solid #fecdca;color:#b42318;border-radius:12px;padding:12px;font-size:12px;margin-bottom:12px}
.ok{background:#ecfdf3;border:1px solid #abefc6;color:#067647;border-radius:12px;padding:12px;font-size:12px;margin-bottom:12px}
.copy{white-space:pre-wrap;background:#f9fafb;border:1px solid #eaecf0;border-radius:10px;padding:12px;font-size:13px}
.bar{height:10px;border-radius:999px;background:#eaecf0;overflow:hidden}.bar span{display:block;height:100%;background:var(--blue)}
.actions form{display:inline-block;margin:0 6px 8px 0;vertical-align:top}
.kv{display:grid;grid-template-columns:150px 1fr;gap:6px 12px;font-size:12px}.kv b{color:#475467;font-weight:800}
@media(max-width:620px){
 .cal{grid-template-columns:1fr}.cal .dow,.day.out{display:none}.day{min-height:0}
 .form-grid{grid-template-columns:1fr}.kv{grid-template-columns:1fr}
 .filters label,.filters select{width:100%}
}
</style>
"""


# ---------------------------------------------------------------- piezas

def _q(query: dict[str, list[str]], name: str, default: str = "") -> str:
    return (query.get(name) or [default])[0].strip()


def _parse_day(raw: str, fallback: date) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return fallback


def fmt_range(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS[start.month - 1][:3]} {start.year}"
    return f"{start.day} {MONTHS[start.month - 1][:3]} – {end.day} {MONTHS[end.month - 1][:3]} {end.year}"


def fmt_ts(value: Any) -> str:
    """Fecha y hora en Guadalajara, sin importar la zona horaria del servidor de base de datos."""
    if not value:
        return ""
    if hasattr(value, "astimezone"):
        return value.astimezone(store.TZ).strftime("%Y-%m-%d %H:%M")
    return str(value)


def chip(status: Any) -> str:
    s = workflow.normalize_status(status)
    return f"<span class='chip st-{s}'>{esc(workflow.STATUS_LABELS[s])}</span>"


def subnav(active: str) -> str:
    links = [
        ("/marketing", "Hoy"),
        ("/marketing/calendario", "Calendario"),
        ("/marketing/campanas", "Campañas"),
        ("/marketing/encuestas", "Encuestas"),
        ("/marketing/biblioteca", "Biblioteca"),
        ("/marketing/nuevo", "+ Nueva publicación"),
    ]
    return "<div class='subnav'>" + "".join(
        f"<a href='{href}' class='{'on' if href == active else ''}'>{esc(label)}</a>" for href, label in links
    ) + "</div>"


def page(title: str, active: str, body: str) -> str:
    return base_page(title, MI_CSS + subnav(active) + body)


def flash(query: dict[str, list[str]]) -> str:
    key = _q(query, "msg")
    text = MESSAGES.get(key)
    if not text:
        return ""
    if key == "generado":
        n, m = _q(query, "n", "0"), _q(query, "m", "0")
        text = f"Borradores creados: {esc(n)}. Ya existían y no se tocaron: {esc(m)}."
    return f"<div class='ok'>{esc(text) if key != 'generado' else text}</div>"


def error_box(errors: list[str]) -> str:
    if not errors:
        return ""
    return "<div class='err'><b>No se guardó.</b><br>" + "<br>".join(esc(e) for e in errors) + "</div>"


def options_html(options: list[tuple[str, str]], selected: Any, *, blank: str | None = None) -> str:
    out = [f"<option value=''>{esc(blank)}</option>"] if blank is not None else []
    sel = "" if selected is None else str(selected)
    for value, label in options:
        out.append(f"<option value='{esc(value)}'{' selected' if str(value) == sel else ''}>{esc(label)}</option>")
    return "".join(out)


def item_card(item: dict[str, Any], *, compact: bool = False) -> str:
    href = "/marketing/item?" + urlencode({"key": item["calendar_key"]})
    topic = str(item.get("topic") or "(sin tema)")
    who = COMMUNITY_SHORT.get(item.get("community_code") or "", "")
    if compact:
        return (f"<a class='mini' href='{href}' title='{esc(topic)}'>"
                f"{esc(item.get('suggested_time') or '')} {esc(who or item.get('channel') or '')} · {esc(topic)}</a>")
    return (
        f"<a class='card t-{esc(item.get('content_type') or 'OTRO')}' href='{href}'>"
        f"<div class='meta'>{(esc(item['suggested_time']) + ' · ') if item.get('suggested_time') else ''}{esc(item.get('channel') or '')}"
        f"{(' · ' + esc(who)) if who else ''}</div>"
        f"<div><b>{esc(topic)}</b></div>"
        f"<div style='margin-top:4px'>{chip(item.get('workflow_status'))}"
        f"{(' <span class=meta>' + esc(item.get('campaign_name')) + '</span>') if item.get('campaign_name') else ''}</div>"
        "</a>"
    )


def transition_form(item: dict[str, Any], target: str, csrf: str, *, back: str, compact: bool = False) -> str:
    current = workflow.normalize_status(item.get("workflow_status"))
    label = workflow.ACTION_LABELS.get((current, target), workflow.STATUS_LABELS[target])
    needs_note = (current == "EN_REVISION" and target == "BORRADOR") or target == "MEDIDO"
    css = "btn sm" + (" warn" if target in {"DESCARTADO"} else "") + (" sec" if target in {"BORRADOR"} else "")
    extra = ""
    if not compact:
        if needs_note:
            placeholder = "Qué hay que cambiar" if target == "BORRADOR" else "Resultado: ventas, visitas, respuestas…"
            extra = f"<br><input name='note' required placeholder='{placeholder}' style='margin-top:6px;min-width:240px'>"
        elif target == "PUBLICADO":
            extra = "<br><input name='published_ref' placeholder='Liga de la publicación (opcional)' style='margin-top:6px;min-width:240px'>"
        elif target == "DESCARTADO":
            extra = "<br><input name='note' placeholder='Motivo (opcional)' style='margin-top:6px;min-width:200px'>"
    return (
        "<form method='post' action='/marketing/item/estado'>"
        f"<input type='hidden' name='csrf' value='{esc(csrf)}'>"
        f"<input type='hidden' name='key' value='{esc(item['calendar_key'])}'>"
        f"<input type='hidden' name='to' value='{esc(target)}'>"
        f"<input type='hidden' name='volver' value='{esc(back)}'>"
        f"<button class='{css}'>{esc(label)}</button>{extra}</form>"
    )


# ---------------------------------------------------------------- Hoy

def render_hoy(conn, *, csrf: str, query: dict[str, list[str]] | None = None, today: date | None = None) -> str:
    query = query or {}
    today = today or store.today_mx()
    items_today = store.list_items(conn, today, today)
    week = store.list_items(conn, today + timedelta(days=1), today + timedelta(days=7), {"estado": "ABIERTOS"})
    review = store.items_in_review(conn)
    active = store.campaigns_on(conn, today)
    next_campaigns = [c for c in store.list_campaigns(conn) if c["starts_on"] > today][:2]

    def quick(item: dict[str, Any]) -> str:
        current = workflow.normalize_status(item.get("workflow_status"))
        primary = {"BORRADOR": "EN_REVISION", "EN_REVISION": "APROBADO",
                   "APROBADO": "PUBLICADO", "PROGRAMADO": "PUBLICADO"}.get(current)
        if not primary:
            return ""
        return transition_form(item, primary, csrf, back="/marketing", compact=True)

    today_rows = "".join(
        f"<tr><td>{esc(i.get('suggested_time') or '—')}</td><td>{esc(i.get('channel') or '')}"
        f"<br><span style='color:#667085'>{esc(COMMUNITY_SHORT.get(i.get('community_code') or '', ''))}</span></td>"
        f"<td><a href='/marketing/item?{urlencode({'key': i['calendar_key']})}'><b>{esc(i.get('topic'))}</b></a>"
        f"<br><span style='color:#667085'>{esc(i.get('cta') or '')}</span></td>"
        f"<td>{chip(i.get('workflow_status'))}</td><td class='actions'>{quick(i)}</td></tr>"
        for i in items_today
    ) or "<tr><td colspan='5'>No hay publicaciones para hoy. Silencio también es una decisión válida.</td></tr>"

    review_rows = "".join(
        f"<tr><td>{esc(i['scheduled_date'])}</td><td>{esc(i.get('channel') or '')}</td>"
        f"<td><a href='/marketing/item?{urlencode({'key': i['calendar_key']})}'><b>{esc(i.get('topic'))}</b></a></td>"
        f"<td class='actions'>{transition_form(i, 'APROBADO', csrf, back='/marketing', compact=True)}"
        f"<a class='btn sm sec' href='/marketing/item?{urlencode({'key': i['calendar_key']})}'>Revisar</a></td></tr>"
        for i in review
    ) or "<tr><td colspan='4'>Nada pendiente de aprobar.</td></tr>"

    def campaign_line(c: dict[str, Any]) -> str:
        ly = store.same_month_last_year(conn, c["starts_on"])
        ly_txt = f" · mismo mes del año pasado: {money(ly)}" if ly is not None else ""
        return (f"<div style='margin-bottom:8px;font-size:12px'><b>{esc(c['name'])}</b> "
                f"<span style='color:#667085'>{esc(fmt_range(c['starts_on'], c['ends_on']))}{ly_txt}</span><br>"
                f"{esc(c.get('theme') or '')} · <a style='color:#175cd3;font-weight:800' href='/marketing/calendario?"
                f"{urlencode({'vista': 'semana', 'fecha': c['starts_on'].isoformat(), 'campana': c['campaign_id']})}'>Ver en calendario</a></div>")

    camp_html = "".join(campaign_line(c) for c in active) or "<div style='color:#667085;font-size:12px'>Sin campaña activa hoy.</div>"
    if next_campaigns:
        camp_html += "<div class='hint' style='margin-top:10px'>Próximas:</div>" + "".join(campaign_line(c) for c in next_campaigns)

    week_html = "".join(item_card(i) for i in week[:12]) or "<div style='color:#667085'>Nada abierto en los próximos 7 días.</div>"

    return page("Marketing · Hoy", "/marketing", f"""
      {flash(query)}
      <div class="callout"><b>Regla:</b> S-Mart planea y registra; tú apruebas y publicas.
        Nada se publica ni se envía por WhatsApp desde el portal.</div>
      <div class="grid" style="margin-top:14px">
        <div class="kpi"><div class="tag">Hoy</div><div class="label">Publicaciones</div><div class="value">{len(items_today)}</div><div class="note">{esc(today.isoformat())}</div></div>
        <div class="kpi"><div class="tag">Revisión</div><div class="label">Por aprobar</div><div class="value">{len(review)}</div><div class="note">En revisión</div></div>
        <div class="kpi"><div class="tag">7 días</div><div class="label">Abiertas</div><div class="value">{len(week)}</div><div class="note">Borrador a programado</div></div>
        <div class="kpi"><div class="tag">Campaña</div><div class="label">Activa hoy</div><div class="value">{len(active)}</div><div class="note">{esc(active[0]['name']) if active else '—'}</div></div>
      </div>
      <div class="grid" style="margin-top:14px">
        <div class="panel full"><h2>Qué publicar hoy</h2>
          <div class="hint">El botón mueve la publicación al siguiente estado. Publicar sigue siendo manual.</div>
          <table><thead><tr><th>Hora</th><th>Canal</th><th>Tema</th><th>Estado</th><th>Siguiente paso</th></tr></thead><tbody>{today_rows}</tbody></table></div>
        <div class="panel"><h2>Por aprobar</h2><table><tbody>{review_rows}</tbody></table></div>
        <div class="panel"><h2>Campañas</h2>{camp_html}</div>
        <div class="panel full"><h2>Próximos 7 días</h2><div class="cal" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr))">{week_html}</div></div>
      </div>
    """)


# ---------------------------------------------------------------- calendario

FILTER_KEYS = ("plataforma", "comunidad", "tipo", "campana", "estado", "objetivo")


def _filters(query: dict[str, list[str]]) -> dict[str, str]:
    return {k: _q(query, k) for k in FILTER_KEYS if _q(query, k)}


def _cal_link(vista: str, day: date, filters: dict[str, str]) -> str:
    return "/marketing/calendario?" + urlencode({"vista": vista, "fecha": day.isoformat(), **filters})


def filters_form(conn, vista: str, day: date, filters: dict[str, str]) -> str:
    campaigns = store.list_campaigns(conn)
    return f"""
      <form class="filters" method="get" action="/marketing/calendario">
        <input type="hidden" name="vista" value="{esc(vista)}"><input type="hidden" name="fecha" value="{esc(day.isoformat())}">
        <label>Plataforma<select name="plataforma">{options_html([(k, v[0]) for k, v in store.PLATFORMS.items()], filters.get('plataforma'), blank='Todas')}</select></label>
        <label>Comunidad<select name="comunidad">{options_html(list(COMMUNITY_SHORT.items()), filters.get('comunidad'), blank='Todas')}</select></label>
        <label>Tipo<select name="tipo">{options_html(list(store.CONTENT_TYPES.items()), filters.get('tipo'), blank='Todos')}</select></label>
        <label>Campaña<select name="campana">{options_html([(str(c['campaign_id']), c['name']) for c in campaigns], filters.get('campana'), blank='Todas')}</select></label>
        <label>Estado<select name="estado">{options_html([('ABIERTOS', 'Abiertos')] + [(s, workflow.STATUS_LABELS[s]) for s in workflow.STATUSES], filters.get('estado'), blank='Todos')}</select></label>
        <label>Objetivo<select name="objetivo">{options_html([(o, o) for o in store.OBJECTIVES], filters.get('objetivo'), blank='Todos')}</select></label>
        <button class="btn sm">Filtrar</button>
        <a class="btn sm sec" href="{_cal_link(vista, day, {})}">Limpiar</a>
      </form>"""


def render_calendar(conn, *, query: dict[str, list[str]], csrf: str, today: date | None = None) -> str:
    today = today or store.today_mx()
    vista = _q(query, "vista", "semana")
    if vista not in {"mes", "semana", "dia"}:
        vista = "semana"
    day = _parse_day(_q(query, "fecha"), today)
    filters = _filters(query)

    tabs = " ".join(
        f"<a class='btn sm {'sec' if v != vista else ''}' href='{_cal_link(v, day, filters)}'>{label}</a>"
        for v, label in (("mes", "Mes"), ("semana", "Semana"), ("dia", "Día"))
    )

    if vista == "mes":
        first = day.replace(day=1)
        nxt = (first + timedelta(days=32)).replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        grid_start = first - timedelta(days=first.weekday())
        items = store.list_items(conn, grid_start, grid_start + timedelta(days=41), filters)
        by_day: dict[date, list[dict[str, Any]]] = {}
        for it in items:
            by_day.setdefault(it["scheduled_date"], []).append(it)
        cells = "".join(f"<div class='dow'>{d}</div>" for d in DOW)
        for n in range(42):
            d = grid_start + timedelta(days=n)
            day_items = by_day.get(d, [])
            shown = "".join(item_card(i, compact=True) for i in day_items[:4])
            more = f"<a class='mini' href='{_cal_link('dia', d, filters)}'>+{len(day_items) - 4} más</a>" if len(day_items) > 4 else ""
            cls = "day" + (" out" if d.month != first.month else "") + (" today" if d == today else "")
            cells += (f"<div class='{cls}'><div class='num'><a href='{_cal_link('dia', d, filters)}'>{DOW[d.weekday()]} {d.day}</a>"
                      f"<a href='/marketing/nuevo?{urlencode({'fecha': d.isoformat()})}' title='Nueva publicación'>＋</a></div>{shown}{more}</div>")
        title = f"{MONTHS[first.month - 1].capitalize()} {first.year}"
        nav = (f"<a class='btn sm sec' href='{_cal_link('mes', prev, filters)}'>←</a> "
               f"<a class='btn sm sec' href='{_cal_link('mes', today, filters)}'>Hoy</a> "
               f"<a class='btn sm sec' href='{_cal_link('mes', nxt, filters)}'>→</a>")
        body = f"<div class='cal'>{cells}</div>"
        count = len([i for i in items if i["scheduled_date"].month == first.month])
    elif vista == "semana":
        start = day - timedelta(days=day.weekday())
        items = store.list_items(conn, start, start + timedelta(days=6), filters)
        cols = ""
        for n in range(7):
            d = start + timedelta(days=n)
            day_items = [i for i in items if i["scheduled_date"] == d]
            cls = "day" + (" today" if d == today else "")
            cols += (f"<div class='{cls}'><div class='num'><a href='{_cal_link('dia', d, filters)}'>{DOW[n]} {d.day} {MONTHS[d.month - 1][:3]}</a>"
                     f"<a href='/marketing/nuevo?{urlencode({'fecha': d.isoformat()})}' title='Nueva publicación'>＋</a></div>"
                     + ("".join(item_card(i) for i in day_items) or "<div class='meta' style='color:#98a2b3;font-size:11px'>—</div>")
                     + "</div>")
        title = f"Semana del {start.day} de {MONTHS[start.month - 1]} {start.year}"
        nav = (f"<a class='btn sm sec' href='{_cal_link('semana', start - timedelta(days=7), filters)}'>←</a> "
               f"<a class='btn sm sec' href='{_cal_link('semana', today, filters)}'>Hoy</a> "
               f"<a class='btn sm sec' href='{_cal_link('semana', start + timedelta(days=7), filters)}'>→</a>")
        body = f"<div class='cal'>{cols}</div>"
        count = len(items)
    else:
        items = store.list_items(conn, day, day, filters)
        rows = ""
        for i in items:
            targets = "".join(
                transition_form(i, t, csrf, back=_cal_link("dia", day, filters), compact=True)
                for t in workflow.allowed_targets(i.get("workflow_status"))
                if not ((workflow.normalize_status(i.get("workflow_status")) == "EN_REVISION" and t == "BORRADOR") or t == "MEDIDO")
            )
            rows += (f"<tr><td>{esc(i.get('suggested_time') or '—')}</td>"
                     f"<td>{esc(i.get('channel') or '')}<br><span style='color:#667085'>{esc(COMMUNITY_SHORT.get(i.get('community_code') or '', ''))}</span></td>"
                     f"<td><a href='/marketing/item?{urlencode({'key': i['calendar_key']})}'><b>{esc(i.get('topic'))}</b></a>"
                     f"<br><span style='color:#667085'>{esc(i.get('hook') or '')}</span></td>"
                     f"<td>{esc(store.CONTENT_TYPES.get(i.get('content_type') or '', i.get('format') or ''))}</td>"
                     f"<td>{chip(i.get('workflow_status'))}</td><td class='actions'>{targets}</td></tr>")
        rows = rows or "<tr><td colspan='6'>No hay publicaciones este día.</td></tr>"
        title = f"{DOW[day.weekday()].capitalize()} {day.day} de {MONTHS[day.month - 1]} {day.year}"
        nav = (f"<a class='btn sm sec' href='{_cal_link('dia', day - timedelta(days=1), filters)}'>←</a> "
               f"<a class='btn sm sec' href='{_cal_link('dia', today, filters)}'>Hoy</a> "
               f"<a class='btn sm sec' href='{_cal_link('dia', day + timedelta(days=1), filters)}'>→</a> "
               f"<a class='btn sm' href='/marketing/nuevo?{urlencode({'fecha': day.isoformat()})}'>+ Nueva</a>")
        body = (f"<div class='panel full'><table><thead><tr><th>Hora</th><th>Canal</th><th>Tema</th><th>Tipo</th>"
                f"<th>Estado</th><th>Acciones</th></tr></thead><tbody>{rows}</tbody></table></div>")
        count = len(items)

    return page("Marketing · Calendario", "/marketing/calendario", f"""
      {flash(query)}
      <div class="navrow"><h2>{esc(title)} <span style="font-size:12px;color:#667085;font-weight:600">· {count} publicaciones</span></h2>
        <div>{tabs} &nbsp; {nav}</div></div>
      {filters_form(conn, vista, day, filters)}
      {body}
    """)


# ---------------------------------------------------------------- detalle y formularios

def item_form(conn, *, csrf: str, item: dict[str, Any] | None = None, defaults: dict[str, Any] | None = None,
              errors: list[str] | None = None) -> str:
    v = {**(defaults or {}), **(item or {})}
    campaigns = store.list_campaigns(conn)
    key = (item or {}).get("calendar_key", "")
    variants = v.get("shopify_variant_ids")
    variants_txt = ", ".join(variants) if isinstance(variants, (list, tuple)) else (variants or "")
    channel_opts = [(c, c) for c in store.CHANNELS]
    if v.get("channel") and v["channel"] not in store.CHANNELS:
        channel_opts = [(v["channel"], v["channel"])] + channel_opts
    return f"""
      {error_box(errors or [])}
      <form method="post" action="/marketing/item/guardar">
        <input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="key" value="{esc(key)}">
        <div class="form-grid">
          <label>Fecha<input type="date" name="scheduled_date" required value="{esc(v.get('scheduled_date') or '')}"></label>
          <label>Hora sugerida<input name="suggested_time" placeholder="HH:MM" value="{esc(v.get('suggested_time') or '')}"></label>
          <label>Canal<select name="channel" required>{options_html(channel_opts, v.get('channel'), blank='Elige un canal')}</select></label>
          <label>Comunidad<select name="community_code">{options_html(list(templates.COMMUNITIES.items()), v.get('community_code'), blank='Ninguna')}</select></label>
          <label>Tipo de contenido<select name="content_type">{options_html(list(store.CONTENT_TYPES.items()), v.get('content_type'), blank='—')}</select></label>
          <label>Objetivo<select name="objective">{options_html([(o, o) for o in store.OBJECTIVES], v.get('objective'), blank='—')}</select></label>
          <label>Campaña<select name="campaign_id">{options_html([(str(c['campaign_id']), c['name']) for c in campaigns], v.get('campaign_id'), blank='Sin campaña')}</select></label>
          <label>Prioridad<select name="priority">{options_html([(p, p.capitalize()) for p in store.PRIORITIES], v.get('priority'), blank='—')}</select></label>
          <label class="wide">Tema<input name="topic" required value="{esc(v.get('topic') or '')}"></label>
          <label class="wide">Hook / ángulo<input name="hook" value="{esc(v.get('hook') or '')}"></label>
          <label class="wide">Copy (Beneficio → Producto → Evidencia → Precio → Disponibilidad → CTA)
            <textarea name="copy_text" placeholder="Solo afirmaciones verificables en la ficha del producto.">{esc(v.get('copy_text') or '')}</textarea></label>
          <label>CTA<input name="cta" value="{esc(v.get('cta') or '')}"></label>
          <label>KPI<input name="kpi" value="{esc(v.get('kpi') or '')}"></label>
          <label>Pilar<input name="pillar" value="{esc(v.get('pillar') or '')}"></label>
          <label>Producto Shopify (ID)<input name="shopify_product_id" value="{esc(v.get('shopify_product_id') or '')}"></label>
          <label class="wide">Variantes Shopify (IDs separados por coma)<input name="shopify_variant_ids" value="{esc(variants_txt)}"></label>
        </div>
        <div style="margin-top:12px"><button class="btn">{'Guardar cambios' if key else 'Crear borrador'}</button></div>
      </form>"""


def render_new(conn, *, csrf: str, query: dict[str, list[str]], errors: list[str] | None = None,
               values: dict[str, Any] | None = None, today: date | None = None) -> str:
    today = today or store.today_mx()
    defaults = values or {
        "scheduled_date": _parse_day(_q(query, "fecha"), today).isoformat(),
        "campaign_id": _q(query, "campana") or None,
    }
    return page("Marketing · Nueva publicación", "/marketing/nuevo", f"""
      <div class="panel full"><h2>Nueva publicación</h2>
        <div class="hint">Se crea como borrador. Después se envía a revisión y se aprueba antes de publicar.</div>
        {item_form(conn, csrf=csrf, defaults=defaults, errors=errors)}
      </div>""")


def render_item(conn, key: str, *, csrf: str, query: dict[str, list[str]] | None = None,
                errors: list[str] | None = None, form_values: dict[str, Any] | None = None) -> tuple[int, str]:
    query = query or {}
    item = store.get_item(conn, key)
    if not item:
        return 404, page("Marketing", "/marketing/calendario", "<div class='panel full'><h2>No existe esa publicación.</h2></div>")
    status = workflow.normalize_status(item.get("workflow_status"))
    back = "/marketing/item?" + urlencode({"key": key})

    actions = "".join(transition_form(item, t, csrf, back=back) for t in workflow.allowed_targets(status))
    if not actions:
        actions = "<span style='color:#667085'>Sin acciones: estado final.</span>"

    reschedule = ""
    if not workflow.reschedule_errors(item):
        reschedule = f"""
          <form method="post" action="/marketing/item/reprogramar" class="filters">
            <input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="key" value="{esc(key)}">
            <label>Nueva fecha<input type="date" name="scheduled_date" required value="{esc(item['scheduled_date'])}"></label>
            <label>Hora<input name="suggested_time" placeholder="HH:MM" value="{esc(item.get('suggested_time') or '')}"></label>
            <button class="btn sm sec">Reprogramar</button>
          </form>"""

    edit = ""
    if not workflow.edit_errors(item):
        edit = f"<div class='panel full'><h2>Editar</h2>{item_form(conn, csrf=csrf, item={**item, **(form_values or {})}, errors=errors)}</div>"
    elif errors:
        edit = f"<div class='panel full'>{error_box(errors)}</div>"

    guard = ""
    if item.get("content_type") in {"PRODUCTO", "OFERTA", "PAGOS"}:
        guard = ("<div class='callout' style='margin-top:10px'><b>Antes de aprobar:</b> confirma en Shopify que las tallas "
                 "anunciadas tienen stock, que el precio es el vigente y que la oferta no rompe el piso de margen. "
                 "No uses urgencia ni escasez que no sean reales.</div>")

    product = ""
    if item.get("shopify_product_id"):
        pid = str(item["shopify_product_id"]).rsplit("/", 1)[-1]
        product = f"<a style='color:#175cd3;font-weight:800' href='{SHOPIFY_ADMIN}/products/{esc(pid)}' target='_blank' rel='noopener'>Abrir producto en Shopify</a>"

    assets = store.item_assets(conn, key)
    all_assets = store.list_assets(conn)
    assets_html = "".join(
        f"<li>{esc(store.ASSET_KINDS.get(a['kind'], a['kind']))} · "
        + (f"<a style='color:#175cd3' href='{esc(a['location_url'])}' target='_blank' rel='noopener'>{esc(a['title'])}</a>" if a.get("location_url") else esc(a["title"]))
        + (f" <span style='color:#667085'>({esc(a['format_note'])})</span>" if a.get("format_note") else "") + "</li>"
        for a in assets
    ) or "<li style='color:#667085'>Sin recursos.</li>"
    link_form = ""
    if all_assets:
        link_form = f"""
          <form method="post" action="/marketing/item/recurso" class="filters">
            <input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="key" value="{esc(key)}">
            <label>Recurso<select name="asset_id">{options_html([(str(a['asset_id']), a['title']) for a in all_assets], None)}</select></label>
            <label>Formato / nota<input name="format_note" placeholder="Ej. 9:16 para Stories"></label>
            <button class="btn sm sec">Agregar</button>
          </form>"""

    log_rows = "".join(
        f"<tr><td>{esc(fmt_ts(l['changed_at']))}</td>"
        f"<td>{esc(l.get('actor') or '')}</td><td>{esc(l['action'])}</td>"
        f"<td>{esc(workflow.STATUS_LABELS.get(l.get('from_status') or '', '') )}{' → ' if l.get('to_status') else ''}{esc(workflow.STATUS_LABELS.get(l.get('to_status') or '', ''))}</td>"
        f"<td>{esc(l.get('note') or '')}</td></tr>"
        for l in store.item_log(conn, key)
    ) or "<tr><td colspan='5'>Sin cambios registrados todavía.</td></tr>"

    kv = [
        ("Fecha", f"{item['scheduled_date']} {item.get('suggested_time') or ''}"),
        ("Canal", item.get("channel")),
        ("Comunidad", templates.COMMUNITIES.get(item.get("community_code") or "", "—")),
        ("Segmento", item.get("target_segment")),
        ("Campaña", item.get("campaign_name")),
        ("Tipo", store.CONTENT_TYPES.get(item.get("content_type") or "", item.get("format"))),
        ("Objetivo", item.get("objective")),
        ("Prioridad", item.get("priority")),
        ("Hook", item.get("hook")),
        ("CTA", item.get("cta")),
        ("KPI", item.get("kpi")),
        ("Aprobó", f"{item.get('approved_by') or ''} {fmt_ts(item.get('approved_at'))}".strip()),
        ("Publicado", f"{fmt_ts(item.get('published_at'))} {item.get('published_ref') or ''}".strip()),
        ("Resultado", item.get("result_notes")),
    ]
    kv_html = "".join(f"<b>{esc(k)}</b><div>{esc(v) if v else '—'}</div>" for k, v in kv)
    copy_html = ""
    if item.get("copy_text"):
        copy_html = (f"<div class='copy' id='copytext'>{esc(item['copy_text'])}</div>"
                     "<button class='btn sm sec' style='margin-top:6px' onclick=\"navigator.clipboard.writeText("
                     "document.getElementById('copytext').innerText);this.innerText='Copiado'\">Copiar texto</button>")

    return 200, page("Marketing · Publicación", "/marketing/calendario", f"""
      {flash(query)}
      <div class="navrow"><h2>{esc(item.get('topic') or '(sin tema)')} {chip(status)}</h2>
        <a class="btn sm sec" href="{_cal_link('semana', item['scheduled_date'], {})}">Ver semana</a></div>
      <div class="grid">
        <div class="panel"><h2>Detalle</h2><div class="kv">{kv_html}</div>{('<div style=margin-top:10px>' + product + '</div>') if product else ''}{guard}</div>
        <div class="panel"><h2>Copy</h2>{copy_html or "<div style='color:#667085'>Todavía sin copy.</div>"}
          <h2 style="margin-top:16px">Recursos</h2><ul style="font-size:12px;padding-left:18px">{assets_html}</ul>{link_form}</div>
        <div class="panel full"><h2>Acciones</h2><div class="actions">{actions}</div>{reschedule}</div>
        {edit}
        <div class="panel full"><h2>Bitácora</h2>
          <table><thead><tr><th>Cuándo</th><th>Quién</th><th>Acción</th><th>Estado</th><th>Nota</th></tr></thead><tbody>{log_rows}</tbody></table></div>
      </div>
    """)


# ---------------------------------------------------------------- campañas

def campaign_form(*, csrf: str, values: dict[str, Any] | None = None, campaign_id: int | None = None,
                  errors: list[str] | None = None) -> str:
    v = values or {}
    statuses = [("PLANEADA", "Planeada"), ("ACTIVA", "Activa"), ("CERRADA", "Cerrada"), ("CANCELADA", "Cancelada")]
    return f"""
      {error_box(errors or [])}
      <form method="post" action="/marketing/campanas/guardar">
        <input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="campaign_id" value="{esc(campaign_id or '')}">
        <div class="form-grid">
          <label>Código<input name="code" required placeholder="2027-01-REYES" value="{esc(v.get('code') or '')}"></label>
          <label>Nombre<input name="name" required value="{esc(v.get('name') or '')}"></label>
          <label>Inicia<input type="date" name="starts_on" required value="{esc(v.get('starts_on') or '')}"></label>
          <label>Termina<input type="date" name="ends_on" required value="{esc(v.get('ends_on') or '')}"></label>
          <label class="wide">Tema<input name="theme" value="{esc(v.get('theme') or '')}"></label>
          <label class="wide">Objetivo<input name="objective" value="{esc(v.get('objective') or '')}"></label>
          <label>Presupuesto aprobado (MXN)<input name="budget_mxn" inputmode="decimal" value="{esc(v.get('budget_mxn') if v.get('budget_mxn') is not None else '')}"></label>
          <label>Meta de ventas (MXN)<input name="sales_goal_mxn" inputmode="decimal" value="{esc(v.get('sales_goal_mxn') if v.get('sales_goal_mxn') is not None else '')}"></label>
          <label>Estado<select name="status">{options_html(statuses, v.get('status') or 'PLANEADA')}</select></label>
          <label class="wide">Notas<textarea name="notes">{esc(v.get('notes') or '')}</textarea></label>
        </div>
        <div style="margin-top:12px"><button class="btn">{'Guardar campaña' if campaign_id else 'Crear campaña'}</button></div>
      </form>"""


def render_campaigns(conn, *, csrf: str, query: dict[str, list[str]] | None = None, errors: list[str] | None = None,
                     values: dict[str, Any] | None = None, editing: int | None = None) -> str:
    query = query or {}
    campaigns = store.list_campaigns(conn)
    if editing is None and _q(query, "editar").isdigit():
        editing = int(_q(query, "editar"))
    if editing and values is None:
        values = store.get_campaign(conn, editing)

    rows = ""
    for c in campaigns:
        ly = store.same_month_last_year(conn, c["starts_on"])
        gen = f"""
          <form method="post" action="/marketing/campanas/generar" style="margin-top:6px">
            <input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="campaign_id" value="{c['campaign_id']}">
            <label style="font-size:11px"><input type="checkbox" name="comunidad" value="WA_LOCAL" checked> WA Local</label>
            <label style="font-size:11px"><input type="checkbox" name="comunidad" value="WA_ONLINE" checked> WA Online</label>
            <button class="btn sm sec">Generar semana tipo</button>
          </form>"""
        rows += (
            f"<tr><td><b>{esc(c['name'])}</b><br><span style='color:#667085'>{esc(c['code'])}</span></td>"
            f"<td style='white-space:nowrap'>{esc(fmt_range(c['starts_on'], c['ends_on']))}</td><td>{esc(c.get('theme') or '')}</td>"
            f"<td>{esc(c['status'].capitalize())}</td>"
            f"<td>{c['items']} total<br><span style='color:#667085'>{c['borradores']} borr. · {c['en_revision']} rev. · {c['aprobados']} aprob. · {c['publicados']} publ.</span></td>"
            f"<td>{money(c.get('budget_mxn'))}<br><span style='color:#667085'>meta {money(c.get('sales_goal_mxn'))}</span></td>"
            f"<td>{money(ly) if ly is not None else '—'}</td>"
            f"<td><a class='btn sm sec' href='/marketing/calendario?{urlencode({'vista': 'semana', 'fecha': c['starts_on'].isoformat(), 'campana': c['campaign_id']})}'>Calendario</a> "
            f"<a class='btn sm sec' href='/marketing/campanas?editar={c['campaign_id']}#form'>Editar</a>{gen}</td></tr>"
        )
    rows = rows or "<tr><td colspan='8'>No hay campañas.</td></tr>"
    return page("Marketing · Campañas", "/marketing/campanas", f"""
      {flash(query)}
      <div class="panel full"><h2>Campañas</h2>
        <div class="hint">“Generar semana tipo” crea borradores para WhatsApp Local (3 productos, 1 encuesta, 1 oferta) y Online
          (2 productos, 1 de pagos u oferta) en los días de la campaña. Nunca toca lo que ya existe ni publica nada.</div>
        <table><thead><tr><th>Campaña</th><th>Fechas</th><th>Tema</th><th>Estado</th><th>Publicaciones</th>
          <th>Presupuesto</th><th>Mismo mes año pasado</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
      <div class="panel full" id="form" style="margin-top:14px"><h2>{'Editar campaña' if editing else 'Nueva campaña'}</h2>
        {campaign_form(csrf=csrf, values=values, campaign_id=editing, errors=errors)}</div>
    """)


# ---------------------------------------------------------------- encuestas

def render_polls(conn, *, csrf: str, query: dict[str, list[str]] | None = None, errors: list[str] | None = None,
                 form: dict[str, list[str]] | None = None) -> str:
    query = query or {}
    form = form or {}
    cards = ""
    for p in store.list_polls(conn):
        s = poll_logic.summarize(p, p["options"])
        bars = "".join(
            f"<div style='margin:6px 0'><div style='display:flex;justify-content:space-between;font-size:12px'>"
            f"<span>{esc(o['label'])}</span><span><b>{o['selections']}</b>"
            f"{(' · ' + format(o['share_of_selections'], '.0%') + ' de selecciones') if o['share_of_selections'] is not None else ''}</span></div>"
            f"<div class='bar'><span style='width:{(o['share_of_selections'] or 0) * 100:.0f}%'></span></div></div>"
            for o in s["options"]
        )
        warns = "".join(f"<div style='color:#b54708;font-size:11px'>{esc(w)}</div>" for w in s["warnings"])
        meta = " · ".join(x for x in [
            esc(p.get("category", "").capitalize()),
            "opción múltiple" if p.get("multi_select") else "opción única",
            esc(p["asked_on"]) if p.get("asked_on") else "fecha sin confirmar",
            esc(COMMUNITY_SHORT.get(p.get("community_code") or "", "comunidad sin confirmar")),
            f"{s['voters']} votantes" if s["voters_known"] and s["voters"] is not None else "votantes desconocidos",
        ] if x)
        cards += (f"<div class='panel'><h2>{esc(p['question'])}</h2><div class='hint'>{meta}</div>{bars}{warns}"
                  + (f"<div style='margin-top:8px;font-size:12px'><b>Conclusión:</b> {esc(p['conclusion'])}"
                     f" <span class='chip st-BORRADOR'>confianza {esc((p.get('confidence') or '—').lower())}</span></div>" if p.get("conclusion") else "")
                  + (f"<div style='font-size:12px'><b>Campaña posterior:</b> {esc(p['campaign_name'])}</div>" if p.get("campaign_name") else "")
                  + "</div>")
    cards = cards or "<div class='panel full'>Todavía no hay encuestas.</div>"

    def f(name: str) -> str:
        return esc((form.get(name) or [""])[0])

    option_rows = "".join(
        f"<tr><td>{i + 1}</td><td><input name='opcion_label_{i}' value='{f(f'opcion_label_{i}')}' placeholder='Texto de la opción'></td>"
        f"<td><input name='opcion_sel_{i}' inputmode='numeric' size='5' value='{f(f'opcion_sel_{i}')}'></td>"
        f"<td><input name='opcion_min_{i}' inputmode='decimal' size='7' value='{f(f'opcion_min_{i}')}'></td>"
        f"<td><input name='opcion_max_{i}' inputmode='decimal' size='7' value='{f(f'opcion_max_{i}')}'></td></tr>"
        for i in range(6)
    )
    categories = [(c, c.capitalize()) for c in ("PRECIO", "COMODIDAD", "MARCA", "MODELO", "TALLA", "ESTILO", "USO", "OTRO")]
    campaigns = store.list_campaigns(conn)
    return page("Marketing · Encuestas", "/marketing/encuestas", f"""
      {flash(query)}
      <div class="callout"><b>Lectura honesta:</b> en opción múltiple, las selecciones no son personas.
        Las encuestas son señales de demanda, no disposición real de pago. WhatsApp no da acceso automático a los resultados: se capturan aquí.</div>
      <div class="grid" style="margin-top:14px">{cards}</div>
      <div class="panel full" style="margin-top:14px"><h2>Registrar encuesta</h2>
        {error_box(errors or [])}
        <form method="post" action="/marketing/encuestas/guardar">
          <input type="hidden" name="csrf" value="{esc(csrf)}">
          <div class="form-grid">
            <label class="wide">Pregunta<input name="question" required value="{f('question')}"></label>
            <label>Categoría<select name="category">{options_html(categories, (form.get('category') or ['PRECIO'])[0])}</select></label>
            <label>Comunidad<select name="community_code">{options_html(list(templates.COMMUNITIES.items()), (form.get('community_code') or [''])[0], blank='Sin confirmar')}</select></label>
            <label>Fecha<input type="date" name="asked_on" value="{f('asked_on')}"></label>
            <label>Votantes únicos (solo si lo sabes)<input name="unique_voters" inputmode="numeric" value="{f('unique_voters')}"></label>
            <label style="flex-direction:row;align-items:center;gap:8px"><input type="checkbox" name="multi_select" value="1" {'checked' if form.get('multi_select') else ''}> Permite varias respuestas</label>
            <label>Captura o evidencia (enlace)<input name="evidence_ref" value="{f('evidence_ref')}"></label>
            <label>Marca relacionada<input name="related_brand" value="{f('related_brand')}"></label>
            <label>Producto relacionado<input name="related_product" value="{f('related_product')}"></label>
          </div>
          <table style="margin-top:12px"><thead><tr><th>#</th><th>Opción</th><th>Selecciones</th><th>Precio mín.</th><th>Precio máx.</th></tr></thead><tbody>{option_rows}</tbody></table>
          <div class="form-grid" style="margin-top:12px">
            <label class="wide">Conclusión comercial<textarea name="conclusion">{f('conclusion')}</textarea></label>
            <label>Confianza<select name="confidence">{options_html([('BAJA', 'Baja'), ('MEDIA', 'Media'), ('ALTA', 'Alta')], (form.get('confidence') or ['BAJA'])[0])}</select></label>
            <label>Campaña posterior<select name="follow_up_campaign_id">{options_html([(str(c['campaign_id']), c['name']) for c in campaigns], (form.get('follow_up_campaign_id') or [''])[0], blank='Ninguna')}</select></label>
          </div>
          <div style="margin-top:12px"><button class="btn">Registrar encuesta</button></div>
        </form></div>
    """)


# ---------------------------------------------------------------- biblioteca

def render_assets(conn, *, csrf: str, query: dict[str, list[str]] | None = None, errors: list[str] | None = None,
                  values: dict[str, Any] | None = None) -> str:
    query = query or {}
    v = values or {}

    def open_link(asset: dict[str, Any]) -> str:
        url = asset.get("location_url")
        if not url:
            return "—"
        return f"<a style='color:#175cd3;font-weight:800' href='{esc(url)}' target='_blank' rel='noopener'>Abrir</a>"

    rows = "".join(
        f"<tr><td><b>{esc(a['title'])}</b><br><span style='color:#667085'>{esc(a.get('notes') or '')}</span></td>"
        f"<td>{esc(store.ASSET_KINDS.get(a['kind'], a['kind']))}</td><td>{esc(a.get('brand') or '')}</td>"
        f"<td>{esc(a.get('shopify_product_id') or '')}</td><td>{a['uses']}</td><td>{open_link(a)}</td></tr>"
        for a in store.list_assets(conn)
    ) or "<tr><td colspan='6'>La biblioteca está vacía.</td></tr>"
    return page("Marketing · Biblioteca", "/marketing/biblioteca", f"""
      {flash(query)}
      <div class="panel full"><h2>Biblioteca de contenido</h2>
        <div class="hint">Fotos, videos, creativos y copies que ya viven en Drive, Shopify o redes. Aquí se guarda el enlace,
          el producto y dónde se ha usado; un recurso puede reutilizarse en varias publicaciones.</div>
        <table><thead><tr><th>Recurso</th><th>Tipo</th><th>Marca</th><th>Producto</th><th>Usos</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>
      <div class="panel full" style="margin-top:14px"><h2>Agregar recurso</h2>
        {error_box(errors or [])}
        <form method="post" action="/marketing/biblioteca/guardar">
          <input type="hidden" name="csrf" value="{esc(csrf)}">
          <div class="form-grid">
            <label>Título<input name="title" required value="{esc(v.get('title') or '')}"></label>
            <label>Tipo<select name="kind">{options_html(list(store.ASSET_KINDS.items()), v.get('kind') or 'FOTO')}</select></label>
            <label class="wide">Enlace (Drive, Shopify, Instagram…)<input name="location_url" placeholder="https://" value="{esc(v.get('location_url') or '')}"></label>
            <label>Marca<input name="brand" value="{esc(v.get('brand') or '')}"></label>
            <label>Producto Shopify (ID)<input name="shopify_product_id" value="{esc(v.get('shopify_product_id') or '')}"></label>
            <label class="wide">Notas<textarea name="notes">{esc(v.get('notes') or '')}</textarea></label>
          </div>
          <div style="margin-top:12px"><button class="btn">Guardar recurso</button></div>
        </form></div>
    """)


# ---------------------------------------------------------------- despacho

def handle_get(conn, route: str, query: dict[str, list[str]], *, csrf: str) -> tuple[int, str]:
    if route == "/marketing":
        return 200, render_hoy(conn, csrf=csrf, query=query)
    if route == "/marketing/calendario":
        return 200, render_calendar(conn, query=query, csrf=csrf)
    if route == "/marketing/item":
        return render_item(conn, _q(query, "key"), csrf=csrf, query=query)
    if route == "/marketing/nuevo":
        return 200, render_new(conn, csrf=csrf, query=query)
    if route == "/marketing/campanas":
        return 200, render_campaigns(conn, csrf=csrf, query=query)
    if route == "/marketing/encuestas":
        return 200, render_polls(conn, csrf=csrf, query=query)
    if route == "/marketing/biblioteca":
        return 200, render_assets(conn, csrf=csrf, query=query)
    return 404, page("Marketing", "/marketing", "<div class='panel full'><h2>Ruta no encontrada.</h2></div>")


def _safe_back(raw: str, default: str) -> str:
    return raw if raw.startswith("/marketing") and not raw.startswith("//") else default


def handle_post(conn, route: str, form: dict[str, list[str]], *, actor: str, csrf: str) -> tuple[str, int, str]:
    """Devuelve ('redirect', 303, url) o ('html', status, página con errores)."""
    v = lambda name: (form.get(name) or [""])[0].strip()  # noqa: E731

    if route == "/marketing/item/guardar":
        data, errors = store.parse_item_form(form)
        key = v("key")
        if errors:
            if key:
                status, html = render_item(conn, key, csrf=csrf, errors=errors, form_values=data)
                return "html", 400 if status == 200 else status, html
            return "html", 400, render_new(conn, csrf=csrf, query={}, errors=errors, values=data)
        if key:
            errors = store.update_item(conn, key, data, actor=actor)
            if errors:
                status, html = render_item(conn, key, csrf=csrf, errors=errors, form_values=data)
                return "html", 400, html
            return "redirect", 303, "/marketing/item?" + urlencode({"key": key, "msg": "guardado"})
        new_key = store.create_item(conn, data, actor=actor)
        return "redirect", 303, "/marketing/item?" + urlencode({"key": new_key, "msg": "creado"})

    if route == "/marketing/item/estado":
        key = v("key")
        errors = store.transition_item(conn, key, v("to"), actor=actor, note=v("note"), published_ref=v("published_ref"))
        back = _safe_back(v("volver"), "/marketing/item?" + urlencode({"key": key}))
        if errors:
            status, html = render_item(conn, key, csrf=csrf, errors=errors)
            return "html", 400 if status == 200 else status, html
        sep = "&" if "?" in back else "?"
        return "redirect", 303, f"{back}{sep}msg=estado"

    if route == "/marketing/item/reprogramar":
        key = v("key")
        try:
            new_date = date.fromisoformat(v("scheduled_date"))
        except ValueError:
            status, html = render_item(conn, key, csrf=csrf, errors=["Fecha inválida (usa AAAA-MM-DD)."])
            return "html", 400, html
        errors = store.reschedule_item(conn, key, new_date, v("suggested_time") or None, actor=actor)
        if errors:
            status, html = render_item(conn, key, csrf=csrf, errors=errors)
            return "html", 400, html
        return "redirect", 303, "/marketing/item?" + urlencode({"key": key, "msg": "reprogramado"})

    if route == "/marketing/item/recurso":
        key = v("key")
        raw = v("asset_id")
        errors = ["Elige un recurso."] if not raw.isdigit() else store.link_asset(
            conn, key, int(raw), actor=actor, note=v("format_note"))
        if errors:
            status, html = render_item(conn, key, csrf=csrf, errors=errors)
            return "html", 400, html
        return "redirect", 303, "/marketing/item?" + urlencode({"key": key, "msg": "recurso"})

    if route == "/marketing/campanas/guardar":
        data, errors = store.parse_campaign_form(form)
        raw_id = v("campaign_id")
        campaign_id = int(raw_id) if raw_id.isdigit() else None
        if not errors:
            _, errors = store.save_campaign(conn, data, actor=actor, campaign_id=campaign_id)
        if errors:
            return "html", 400, render_campaigns(conn, csrf=csrf, errors=errors, values=data, editing=campaign_id)
        return "redirect", 303, "/marketing/campanas?msg=campana"

    if route == "/marketing/campanas/generar":
        raw_id = v("campaign_id")
        communities = [c.strip() for c in form.get("comunidad", [])]
        if not raw_id.isdigit():
            return "html", 400, render_campaigns(conn, csrf=csrf, errors=["Campaña inválida."])
        inserted, existing, errors = store.generate_campaign_drafts(conn, int(raw_id), communities, actor=actor)
        if errors:
            return "html", 400, render_campaigns(conn, csrf=csrf, errors=errors)
        return "redirect", 303, f"/marketing/campanas?msg=generado&n={inserted}&m={existing}"

    if route == "/marketing/encuestas/guardar":
        data, errors = store.parse_poll_form(form)
        if errors:
            return "html", 400, render_polls(conn, csrf=csrf, errors=errors, form=form)
        store.save_poll(conn, data, actor=actor)
        return "redirect", 303, "/marketing/encuestas?msg=encuesta"

    if route == "/marketing/biblioteca/guardar":
        data, errors = store.parse_asset_form(form)
        if errors:
            return "html", 400, render_assets(conn, csrf=csrf, errors=errors, values=data)
        store.save_asset(conn, data, actor=actor)
        return "redirect", 303, "/marketing/biblioteca?msg=biblioteca"

    return "html", 404, page("Marketing", "/marketing", "<div class='panel full'><h2>Ruta no encontrada.</h2></div>")
