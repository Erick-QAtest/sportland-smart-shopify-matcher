"""Registro del día (v7.2): captura de eventos de clientes directo en el portal.

Sustituye la captura en la hoja `eventos_log`: el operador registra en lote al final
del día y cada evento se guarda en `customer_events` con `source = sportland_portal`.
La identidad del cliente se resuelve por teléfono en `customers.phone_e164`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from smart_portal.portal_v60 import base_page, esc, money

CAPTURE_SOURCE = "sportland_portal"
FORM_ROWS = 15
TZ = ZoneInfo("America/Mexico_City")

# Mismas reglas que el Apps Script v5.2 (CFG.EVENTOS_REQUIEREN_TALLA / EVENTOS_ANONIMOS_PERMITIDOS).
EVENTOS_REQUIEREN_TALLA = {
    "PREGUNTA_TALLA_PRECIO", "PRUEBA_MULTIPLES_MODELOS", "APARTADO",
    "ABONO_APARTADO", "LIQUIDACION_APARTADO", "COMPRA",
    "COMPRA_TIENDA_FISICA", "COMPRA_ECOMMERCE", "COMPRA_MARKETPLACE",
}
EVENTOS_ANONIMOS_PERMITIDOS = {
    "LLEGADA_POR_CANAL_FISICO", "OBSERVA_PRODUCTO", "ENTRA_RAPIDO_SIN_DATOS",
    "PREGUNTA_TALLA_PRECIO", "PREGUNTA_SISTEMA_APARTADO",
    "PREGUNTA_MODELO_ESPECIFICO", "PRUEBA_MULTIPLES_MODELOS", "SALE_SIN_COMPRA",
}
EVENTOS_CON_MONTO = {"APARTADO", "ABONO_APARTADO", "LIQUIDACION_APARTADO", "COMPRA",
                     "COMPRA_TIENDA_FISICA", "COMPRA_ECOMMERCE", "COMPRA_MARKETPLACE"}

FIELDS = ("fecha", "hora", "telefono", "tipo", "sku", "talla", "monto", "canal", "detalle")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str) -> tuple[str, str | None]:
    """Teléfono a E.164. A diferencia de la hoja, acepta 10 dígitos de México y les antepone +52."""
    s = re.sub(r"[()\s\-.]", "", raw or "")
    if not s:
        return "", None
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        if re.fullmatch(r"\d{10}", s):
            s = "+52" + s
        elif re.fullmatch(r"52\d{10}", s):
            s = "+" + s
        else:
            return "", "Teléfono inválido: usa 10 dígitos o el formato +52…"
    if not _E164.match(s):
        return "", "Teléfono inválido: usa 10 dígitos o el formato +52…"
    return s, None


def normalize_size(raw: str) -> str:
    """Mismo contrato que normalizeSize_ del Apps Script y smart_normalize_size()."""
    s = re.sub(r"\s+", " ", (raw or "").strip().upper()).replace(",", ".")
    s = re.sub(r"\s*MX\s*$", "", s).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", s) and "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


@dataclass
class RowInput:
    index: int
    values: dict[str, str]

    def get(self, name: str) -> str:
        return (self.values.get(name) or "").strip()

    def is_blank(self) -> bool:
        # La fecha viene precargada: una fila sin nada más se considera vacía.
        return not any(self.get(name) for name in FIELDS if name != "fecha")


@dataclass
class RowResult:
    row: RowInput
    errors: list[str] = field(default_factory=list)
    payload: dict[str, Any] | None = None


def parse_rows(form: dict[str, list[str]], count: int = FORM_ROWS) -> list[RowInput]:
    rows = []
    for index in range(count):
        values = {name: (form.get(f"{name}_{index}") or [""])[0] for name in FIELDS}
        rows.append(RowInput(index=index, values=values))
    return rows


def _parse_occurred_at(row: RowInput, today: date) -> tuple[datetime | None, str | None]:
    try:
        day = date.fromisoformat(row.get("fecha")) if row.get("fecha") else today
    except ValueError:
        return None, "Fecha inválida."
    if day > today:
        return None, "La fecha no puede ser futura."
    clock = time(12, 0)
    if row.get("hora"):
        try:
            clock = time.fromisoformat(row.get("hora"))
        except ValueError:
            return None, "Hora inválida."
    return datetime.combine(day, clock, tzinfo=TZ), None


def validate_row(row: RowInput, catalog: dict[str, int], today: date) -> RowResult:
    result = RowResult(row=row)
    event_name = row.get("tipo").upper()
    if event_name not in catalog:
        result.errors.append("Elige el tipo de evento.")

    phone, phone_error = normalize_phone(row.get("telefono"))
    if phone_error:
        result.errors.append(phone_error)
    elif not phone and event_name and event_name not in EVENTOS_ANONIMOS_PERMITIDOS:
        result.errors.append("Este evento necesita el teléfono del cliente.")

    size = normalize_size(row.get("talla"))
    if event_name in EVENTOS_REQUIEREN_TALLA and not size:
        result.errors.append("Este evento necesita la talla.")

    amount = None
    if row.get("monto"):
        try:
            amount = Decimal(row.get("monto").replace(",", "").replace("$", ""))
        except InvalidOperation:
            result.errors.append("Monto inválido.")
        else:
            if amount < 0:
                result.errors.append("El monto no puede ser negativo.")
    elif event_name in EVENTOS_CON_MONTO:
        result.errors.append("Este evento necesita el monto.")

    occurred_at, date_error = _parse_occurred_at(row, today)
    if date_error:
        result.errors.append(date_error)

    if not result.errors:
        result.payload = {
            "phone_e164": phone or None,
            "event_type_id": catalog[event_name],
            "event_type_name": event_name,
            "occurred_at": occurred_at,
            "sku": row.get("sku") or None,
            "size": size or None,
            "amount": amount,
            "channel": row.get("canal") or None,
            "detail": row.get("detalle") or None,
            "time_given": bool(row.get("hora")),
        }
    return result


def fetch_catalog(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT event_type_name, event_type_id
        FROM event_catalog
        WHERE event_scope IN ('customer', 'both')
        ORDER BY event_type_id
        """
    ).fetchall()
    return {row["event_type_name"]: row["event_type_id"] for row in rows}


class IdentityConflict(ValueError):
    def __init__(self, phone: str, count: int):
        super().__init__(f"Este teléfono aparece en {count} clientes distintos; hay que unificarlos antes de registrar.")
        self.phone = phone


def find_or_create_customer(conn, phone: str, occurred_at: datetime) -> tuple[int, str, bool]:
    """Devuelve (customer_id, client_uuid, creado)."""
    rows = conn.execute(
        "SELECT customer_id, client_uuid FROM customers WHERE phone_e164 = %s ORDER BY customer_id",
        (phone,),
    ).fetchall()
    if len(rows) > 1:
        raise IdentityConflict(phone, len(rows))
    if rows:
        conn.execute(
            """
            UPDATE customers
            SET last_seen_at = GREATEST(COALESCE(last_seen_at, %(at)s), %(at)s),
                first_seen_at = LEAST(COALESCE(first_seen_at, %(at)s), %(at)s),
                updated_at = now()
            WHERE customer_id = %(id)s
            """,
            {"at": occurred_at, "id": rows[0]["customer_id"]},
        )
        return rows[0]["customer_id"], rows[0]["client_uuid"], False
    client_uuid = str(uuid.uuid4())
    row = conn.execute(
        """
        INSERT INTO customers(client_uuid, phone_e164, first_seen_at, last_seen_at, first_channel)
        VALUES (%s, %s, %s, %s, 'portal')
        RETURNING customer_id
        """,
        (client_uuid, phone, occurred_at, occurred_at),
    ).fetchone()
    return row["customer_id"], client_uuid, True


def _is_duplicate(conn, payload: dict[str, Any], client_uuid: str | None) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM customer_events
        WHERE client_uuid IS NOT DISTINCT FROM %(client_uuid)s
          AND event_type_name = %(event_type_name)s
          AND sku IS NOT DISTINCT FROM %(sku)s
          AND size IS NOT DISTINCT FROM %(size)s
          AND amount IS NOT DISTINCT FROM %(amount)s
          AND (occurred_at AT TIME ZONE 'America/Mexico_City')::date
              = (%(occurred_at)s::timestamptz AT TIME ZONE 'America/Mexico_City')::date
        LIMIT 1
        """,
        {**payload, "client_uuid": client_uuid},
    ).fetchone()
    return row is not None


def _event_hash(payload: dict[str, Any], client_uuid: str | None) -> str:
    canonical = json.dumps(
        [client_uuid, payload["event_type_name"], payload["occurred_at"].isoformat(),
         payload["sku"], payload["size"], str(payload["amount"]), payload["channel"], payload["detail"]],
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def guardar_registro(conn, rows: list[RowInput], *, actor: str, today: date | None = None) -> dict[str, Any]:
    """Valida todas las filas; si alguna tiene error no guarda nada, para corregir el lote completo."""
    today = today or datetime.now(TZ).date()
    catalog = fetch_catalog(conn)
    results = [validate_row(row, catalog, today) for row in rows if not row.is_blank()]
    summary: dict[str, Any] = {"results": results, "saved": 0, "duplicates": 0, "new_customers": 0}
    if not results or any(result.errors for result in results):
        return summary

    try:
        with conn.transaction():
            for result in results:
                payload = result.payload
                customer_id = client_uuid = None
                if payload["phone_e164"]:
                    customer_id, client_uuid, created = find_or_create_customer(conn, payload["phone_e164"], payload["occurred_at"])
                    summary["new_customers"] += int(created)
                if _is_duplicate(conn, payload, client_uuid):
                    summary["duplicates"] += 1
                    continue
                event_uuid = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO customer_events(
                        event_uuid, event_hash, source, source_row_hash, customer_id, client_uuid,
                        event_type_id, event_type_name, detail, occurred_at, logged_at,
                        sku, size, amount, channel, currency, actor, device, origin, metadata, raw_status
                    ) VALUES (
                        %(event_uuid)s, %(event_hash)s, %(source)s, %(event_uuid)s, %(customer_id)s, %(client_uuid)s,
                        %(event_type_id)s, %(event_type_name)s, %(detail)s, %(occurred_at)s, now(),
                        %(sku)s, %(size)s, %(amount)s, %(channel)s, 'MXN', %(actor)s, 'portal', 'registro_del_dia',
                        %(metadata)s::jsonb, 'LOGGED'
                    )
                    """,
                    {
                        **payload,
                        "event_uuid": event_uuid,
                        "event_hash": _event_hash(payload, client_uuid),
                        "source": CAPTURE_SOURCE,
                        "customer_id": customer_id,
                        "client_uuid": client_uuid,
                        "actor": actor,
                        # Sin hora se guarda a las 12:00 para no mover el día; se marca para no mostrarla.
                        "metadata": json.dumps({"capture": "registro_v72", "time_given": payload["time_given"]}),
                    },
                )
                summary["saved"] += 1
    except IdentityConflict as exc:
        # La transacción ya se revirtió: se marca cada fila con ese teléfono y no se guarda nada.
        for result in results:
            if result.payload and result.payload["phone_e164"] == exc.phone:
                result.errors.append(str(exc))
        summary.update(saved=0, duplicates=0, new_customers=0)
    return summary


def _options(conn) -> dict[str, list[tuple[str, str]]]:
    skus = conn.execute(
        """
        SELECT DISTINCT ON (shopify_variant_id)
               sku, metadata->>'product_title' AS title, metadata->>'size' AS size
        FROM inventory_snapshots
        WHERE sku IS NOT NULL AND sku <> ''
        ORDER BY shopify_variant_id, captured_at DESC
        LIMIT 4000
        """
    ).fetchall()
    channels = conn.execute(
        """
        SELECT channel FROM customer_events
        WHERE channel IS NOT NULL AND channel <> ''
        GROUP BY channel ORDER BY count(*) DESC LIMIT 20
        """
    ).fetchall()
    return {
        "skus": [(row["sku"], " · ".join(filter(None, [row["title"], f"talla {row['size']}" if row["size"] else ""]))) for row in skus],
        "channels": [(row["channel"], "") for row in channels],
    }


def _today_events(conn, today: date) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT e.occurred_at, COALESCE((e.metadata->>'time_given')::boolean, true) AS time_given, e.event_type_name, e.sku, e.size, e.amount, e.channel, e.detail, e.actor,
               right(c.phone_e164, 4) AS phone_tail
        FROM customer_events e
        LEFT JOIN customers c ON c.customer_id = e.customer_id
        WHERE e.source = %s
          AND (e.logged_at AT TIME ZONE 'America/Mexico_City')::date = %s
        ORDER BY e.logged_at DESC, e.event_id DESC
        LIMIT 200
        """,
        (CAPTURE_SOURCE, today),
    ).fetchall()


REGISTRO_CSS = """
<style>
.reg-wrap{overflow-x:auto;border:1px solid #dbe7f5;border-radius:14px;background:#fff}
.reg-table{border-collapse:collapse;width:100%;min-width:1180px;font-size:14px}
.reg-table th{background:#f6f9fd;color:#475467;text-align:left;padding:8px;font-weight:600;white-space:nowrap}
.reg-table td{padding:4px;border-top:1px solid #eef2f6;vertical-align:top}
.reg-table input,.reg-table select{width:100%;min-height:36px;padding:6px 8px;border:1px solid #d0d5dd;border-radius:8px;font:inherit;box-sizing:border-box}
.reg-table tr.reg-error td{background:#fff5f4}
.reg-errors{margin:4px 0 0;color:#b42318;font-size:12px}
.reg-actions{display:flex;gap:12px;align-items:center;margin:14px 0}
.reg-actions button{min-height:42px;padding:0 20px;border:0;border-radius:10px;background:#1d4ed8;color:#fff;font-weight:600;cursor:pointer}
.reg-msg{padding:12px 14px;border-radius:12px;margin:12px 0}
.reg-ok{background:#ecfdf3;color:#05603a}
.reg-bad{background:#fef3f2;color:#b42318}
</style>
"""


def _cell(name: str, index: int, value: str, *, kind: str = "text", attrs: str = "") -> str:
    return f'<input name="{name}_{index}" type="{kind}" value="{esc(value)}" {attrs}>'


def render_registro(
    conn,
    *,
    csrf_token: str,
    results: list[RowResult] | None = None,
    rows: list[RowInput] | None = None,
    saved: int | None = None,
    duplicates: int = 0,
    new_customers: int = 0,
    today: date | None = None,
) -> str:
    today = today or datetime.now(TZ).date()
    catalog = fetch_catalog(conn)
    options = _options(conn)
    errors_by_index = {result.row.index: result.errors for result in (results or []) if result.errors}
    rows = rows or [RowInput(index=i, values={"fecha": today.isoformat()}) for i in range(FORM_ROWS)]

    body_rows = []
    for row in rows:
        selected = row.get("tipo").upper()
        choices = "".join(
            f"<option value='{esc(name)}'{' selected' if name == selected else ''}>{esc(name.replace('_', ' ').capitalize())}</option>"
            for name in catalog
        )
        select = f"<select name='tipo_{row.index}'><option value=''>—</option>{choices}</select>"
        errs = errors_by_index.get(row.index)
        body_rows.append(
            f"""
            <tr class="{'reg-error' if errs else ''}">
              <td>{_cell('fecha', row.index, row.get('fecha') or today.isoformat(), kind='date', attrs=f"max='{today.isoformat()}'")}</td>
              <td>{_cell('hora', row.index, row.get('hora'), kind='time')}</td>
              <td>{_cell('telefono', row.index, row.get('telefono'), kind='tel', attrs="placeholder='33 1234 5678' autocomplete='off'")}
                  {''.join(f"<p class='reg-errors'>{esc(e)}</p>" for e in errs) if errs else ''}</td>
              <td>{select}</td>
              <td>{_cell('sku', row.index, row.get('sku'), attrs="list='reg-skus' autocomplete='off'")}</td>
              <td>{_cell('talla', row.index, row.get('talla'), attrs="inputmode='decimal' style='max-width:80px'")}</td>
              <td>{_cell('monto', row.index, row.get('monto'), attrs="inputmode='decimal' placeholder='$'")}</td>
              <td>{_cell('canal', row.index, row.get('canal'), attrs="list='reg-canales' autocomplete='off'")}</td>
              <td>{_cell('detalle', row.index, row.get('detalle'), attrs="maxlength='300'")}</td>
            </tr>
            """
        )

    sku_list = "".join(f"<option value='{esc(v)}'>{esc(label)}</option>" for v, label in options["skus"])
    channel_list = "".join(f"<option value='{esc(v)}'></option>" for v, _ in options["channels"])

    message = ""
    if errors_by_index:
        message = f"<div class='reg-msg reg-bad'>No se guardó nada: corrige {len(errors_by_index)} fila(s) marcada(s) en rojo y vuelve a guardar.</div>"
    elif saved is not None:
        extra = []
        if duplicates:
            extra.append(f"{duplicates} ya existían y se omitieron")
        if new_customers:
            extra.append(f"{new_customers} cliente(s) nuevo(s)")
        message = f"<div class='reg-msg reg-ok'>Guardados {saved} evento(s){': ' + ', '.join(extra) if extra else ''}.</div>"

    today_rows = "".join(
        f"""<tr><td>{esc(r['occurred_at'].astimezone(TZ).strftime('%d/%m %H:%M' if r['time_given'] else '%d/%m'))}</td>
        <td>{esc(r['event_type_name'])}</td><td>{'···' + esc(r['phone_tail']) if r['phone_tail'] else '—'}</td>
        <td>{esc(r['sku'] or '')} {esc(r['size'] or '')}</td><td>{money(r['amount']) if r['amount'] is not None else ''}</td>
        <td>{esc(r['channel'] or '')}</td><td>{esc(r['detail'] or '')}</td><td>{esc(r['actor'] or '')}</td></tr>"""
        for r in _today_events(conn, today)
    ) or "<tr><td colspan='8'>Todavía no hay eventos registrados hoy desde el portal.</td></tr>"

    content = f"""
    {REGISTRO_CSS}
    <div class="section-title">
      <h2>Registro del día</h2>
      <span>Captura los eventos de clientes de hoy. Sustituye la hoja de eventos.</span>
    </div>
    {message}
    <form method="post" action="/registro">
      <input type="hidden" name="csrf" value="{esc(csrf_token)}">
      <div class="reg-wrap">
        <table class="reg-table">
          <thead><tr><th>Fecha</th><th>Hora</th><th>Teléfono</th><th>Evento</th><th>SKU</th><th>Talla</th><th>Monto</th><th>Canal</th><th>Detalle</th></tr></thead>
          <tbody>{''.join(body_rows)}</tbody>
        </table>
      </div>
      <datalist id="reg-skus">{sku_list}</datalist>
      <datalist id="reg-canales">{channel_list}</datalist>
      <div class="reg-actions">
        <button type="submit">Guardar eventos</button>
        <span style="color:#667085">Las filas vacías se ignoran. Si alguna fila tiene un error no se guarda ninguna, para que corrijas sin perder lo escrito.</span>
      </div>
    </form>

    <div class="section-title" style="margin-top:24px"><h2>Registrado hoy</h2><span>Desde el portal</span></div>
    <div class="reg-wrap">
      <table class="reg-table">
        <thead><tr><th>Cuándo</th><th>Evento</th><th>Teléfono</th><th>Producto</th><th>Monto</th><th>Canal</th><th>Detalle</th><th>Registró</th></tr></thead>
        <tbody>{today_rows}</tbody>
      </table>
    </div>
    """
    return base_page("Registro del día", content)
