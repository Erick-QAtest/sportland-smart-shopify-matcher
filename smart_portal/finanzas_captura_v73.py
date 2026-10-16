"""Captura de finanzas (v7.3): caja, pagos programados y deudas, directo en el portal.

Sustituye las pestañas Caja externa, Próximos pagos y Deudas de la hoja de finanzas.
Cada sección se guarda completa o no se guarda (para corregir sin perder lo escrito) y
cada cambio queda en finance_change_log con el antes y el después.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Callable
from zoneinfo import ZoneInfo

from smart_finance.db_source import load_v2_inputs
from smart_portal.portal_v60 import base_page, esc, money

TZ = ZoneInfo("America/Mexico_City")
NEW_ROWS = {"caja": 2, "pagos": 6, "deudas": 3}
PAYMENT_STATUSES = ["pendiente", "por confirmar", "pagado", "cancelado"]
DEBT_STATUSES = ["activa", "liquidada"]
CASH_TYPES = ["Efectivo", "Cuenta"]


@dataclass
class SectionResult:
    errors: dict[int, list[str]] = field(default_factory=dict)
    inserted: int = 0
    updated: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _today() -> date:
    return datetime.now(TZ).date()


def _form_rows(form: dict[str, list[str]], prefix: str, names: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        count = min(int((form.get(f"{prefix}_n") or ["0"])[0]), 300)
    except ValueError:
        count = 0
    rows = []
    for i in range(count):
        rows.append({name: (form.get(f"{prefix}_{name}_{i}") or [""])[0].strip() for name in names} | {"_i": str(i)})
    return rows


def _money(raw: str, errors: list[str], *, label: str, allow_negative: bool = False, required: bool = True) -> Decimal | None:
    if not raw:
        if required:
            errors.append(f"Falta {label}.")
        return None
    try:
        value = Decimal(raw.replace(",", "").replace("$", "").replace(" ", ""))
    except InvalidOperation:
        errors.append(f"{label.capitalize()} inválido.")
        return None
    if value < 0 and not allow_negative:
        errors.append(f"{label.capitalize()} no puede ser negativo.")
    return value


def _date(raw: str, errors: list[str], *, label: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(f"{label.capitalize()} inválida.")
        return None


def _jsonable(row: dict[str, Any]) -> str:
    return json.dumps({k: (str(v) if v is not None else None) for k, v in row.items()}, ensure_ascii=False)


def _save(
    conn,
    *,
    table: str,
    key: str,
    columns: tuple[str, ...],
    rows: list[tuple[int | None, dict[str, Any]]],
    actor: str,
    result: SectionResult,
) -> None:
    """Inserta filas nuevas y actualiza solo las que cambiaron, con bitácora."""
    for record_id, values in rows:
        if record_id is None:
            cols = ", ".join(columns + ("updated_by",))
            marks = ", ".join(["%s"] * (len(columns) + 1))
            new_id = conn.execute(
                f"INSERT INTO {table}({cols}) VALUES ({marks}) RETURNING {key}",
                [values[c] for c in columns] + [actor],
            ).fetchone()[key]
            conn.execute(
                "INSERT INTO finance_change_log(table_name, record_id, action, after_data, actor) VALUES (%s, %s, 'insert', %s::jsonb, %s)",
                (table, new_id, _jsonable(values), actor),
            )
            result.inserted += 1
            continue
        before = conn.execute(f"SELECT {', '.join(columns)} FROM {table} WHERE {key} = %s", (record_id,)).fetchone()
        if before is None:
            continue
        if all(_same(before[c], values[c]) for c in columns):
            continue
        sets = ", ".join(f"{c} = %s" for c in columns)
        conn.execute(
            f"UPDATE {table} SET {sets}, updated_by = %s, updated_at = now() WHERE {key} = %s",
            [values[c] for c in columns] + [actor, record_id],
        )
        conn.execute(
            "INSERT INTO finance_change_log(table_name, record_id, action, before_data, after_data, actor) VALUES (%s, %s, 'update', %s::jsonb, %s::jsonb, %s)",
            (table, record_id, _jsonable(dict(before)), _jsonable(values), actor),
        )
        result.updated += 1


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, Decimal) or isinstance(b, Decimal):
        return a is not None and b is not None and Decimal(str(a)) == Decimal(str(b))
    return (a or None) == (b or None)


def _record_id(raw: str) -> int | None:
    return int(raw) if raw.isdigit() else None


def guardar_caja(conn, form: dict[str, list[str]], *, actor: str) -> SectionResult:
    result = SectionResult()
    parsed = []
    for row in _form_rows(form, "caja", ("id", "nombre", "tipo", "saldo", "disponible")):
        rid = _record_id(row["id"])
        if rid is None and not (row["nombre"] or row["saldo"]):
            continue
        errors: list[str] = []
        if not row["nombre"]:
            errors.append("Falta el nombre de la cuenta.")
        balance = _money(row["saldo"], errors, label="el saldo", allow_negative=True)
        if errors:
            result.errors[int(row["_i"])] = errors
            continue
        parsed.append((rid, {
            "account_name": row["nombre"],
            # Se respeta el tipo tal como venía de la hoja (p. ej. "Cuenta bancaria").
            "account_type": row["tipo"] or "Cuenta",
            "balance_mxn": balance,
            "available": row["disponible"] == "si",
            "cut_date": _today(),
        }))
    if result.ok:
        with conn.transaction():
            # La fecha de corte solo cambia si cambió algo más de la cuenta.
            for rid, values in parsed:
                if rid is not None:
                    prev = conn.execute("SELECT cut_date FROM finance_cash_balances WHERE account_id = %s", (rid,)).fetchone()
                    current = conn.execute(
                        "SELECT account_name, account_type, balance_mxn, available FROM finance_cash_balances WHERE account_id = %s",
                        (rid,),
                    ).fetchone()
                    if prev and current and all(_same(current[c], values[c]) for c in current.keys()):
                        values["cut_date"] = prev["cut_date"]
            _save(conn, table="finance_cash_balances", key="account_id",
                  columns=("account_name", "account_type", "balance_mxn", "available", "cut_date"),
                  rows=parsed, actor=actor, result=result)
    return result


def guardar_pagos(conn, form: dict[str, list[str]], *, actor: str) -> SectionResult:
    result = SectionResult()
    parsed = []
    for row in _form_rows(form, "pagos", ("id", "fecha", "concepto", "acreedor", "monto", "estado", "cuenta", "categoria")):
        rid = _record_id(row["id"])
        if rid is None and not (row["acreedor"] or row["monto"] or row["concepto"]):
            continue
        errors: list[str] = []
        due = _date(row["fecha"], errors, label="la fecha")
        # Como en la hoja, el acreedor puede faltar si el concepto dice qué es.
        if not row["acreedor"] and not row["concepto"]:
            errors.append("Escribe el acreedor o el concepto.")
        amount = _money(row["monto"], errors, label="el monto")
        if amount is not None and amount <= 0:
            errors.append("El monto debe ser mayor a cero.")
        if errors:
            result.errors[int(row["_i"])] = errors
            continue
        parsed.append((rid, {
            "due_date": due,
            "concept": row["concepto"],
            "creditor": row["acreedor"],
            "amount_mxn": amount,
            "status": row["estado"] if row["estado"] in PAYMENT_STATUSES else "pendiente",
            "account_ref": row["cuenta"] or None,
            "category": row["categoria"] or None,
        }))
    if result.ok:
        with conn.transaction():
            _save(conn, table="finance_scheduled_payments", key="payment_id",
                  columns=("due_date", "concept", "creditor", "amount_mxn", "status", "account_ref", "category"),
                  rows=parsed, actor=actor, result=result)
    return result


def guardar_deudas(conn, form: dict[str, list[str]], *, actor: str) -> SectionResult:
    result = SectionResult()
    parsed = []
    for row in _form_rows(form, "deudas", ("id", "acreedor", "saldo", "estado")):
        rid = _record_id(row["id"])
        if rid is None and not (row["acreedor"] or row["saldo"]):
            continue
        errors: list[str] = []
        if not row["acreedor"]:
            errors.append("Falta el acreedor.")
        balance = _money(row["saldo"], errors, label="el saldo")
        if errors:
            result.errors[int(row["_i"])] = errors
            continue
        parsed.append((rid, {
            "creditor": row["acreedor"],
            "balance_mxn": balance,
            "status": row["estado"] if row["estado"] in DEBT_STATUSES else "activa",
        }))
    if result.ok:
        with conn.transaction():
            _save(conn, table="finance_debts", key="debt_id",
                  columns=("creditor", "balance_mxn", "status"), rows=parsed, actor=actor, result=result)
    return result


SAVERS: dict[str, Callable[..., SectionResult]] = {"caja": guardar_caja, "pagos": guardar_pagos, "deudas": guardar_deudas}


# ---------- Render ----------

CSS = """
<style>
.fc-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0 22px}
.fc-kpi{background:#fff;border:1px solid #dbe7f5;border-radius:14px;padding:14px 16px}
.fc-kpi .k{color:#667085;font-size:12px;font-weight:600;letter-spacing:.04em}
.fc-kpi .v{font-size:26px;font-weight:700;color:#101828;margin-top:4px}
.fc-kpi .n{color:#667085;font-size:13px}
.fc-wrap{overflow-x:auto;border:1px solid #dbe7f5;border-radius:14px;background:#fff}
.fc-table{border-collapse:collapse;width:100%;min-width:900px;font-size:14px}
.fc-table th{background:#f6f9fd;color:#475467;text-align:left;padding:8px;font-weight:600;white-space:nowrap}
.fc-table td{padding:4px;border-top:1px solid #eef2f6;vertical-align:top}
.fc-table input,.fc-table select{width:100%;min-height:36px;padding:6px 8px;border:1px solid #d0d5dd;border-radius:8px;font:inherit;box-sizing:border-box}
.fc-table input[type=checkbox]{width:20px;min-height:20px}
.fc-table tr.fc-new td{background:#fbfcfe}
.fc-table tr.fc-error td{background:#fff5f4}
.fc-err{margin:4px 0 0;color:#b42318;font-size:12px}
.fc-actions{display:flex;gap:12px;align-items:center;margin:12px 0 30px}
.fc-actions button{min-height:42px;padding:0 20px;border:0;border-radius:10px;background:#1d4ed8;color:#fff;font-weight:600;cursor:pointer}
.fc-msg{padding:12px 14px;border-radius:12px;margin:12px 0}
.fc-ok{background:#ecfdf3;color:#05603a}.fc-bad{background:#fef3f2;color:#b42318}
.fc-nav{display:flex;gap:10px;margin:0 0 6px}.fc-nav a{color:#1d4ed8;font-weight:600}
</style>
"""


def _input(name: str, value: Any, *, kind: str = "text", attrs: str = "") -> str:
    return f'<input name="{name}" type="{kind}" value="{esc("" if value is None else value)}" {attrs}>'


def _select(name: str, options: list[str], selected: str) -> str:
    if selected and selected not in options:
        options = [selected] + options
    opts = "".join(f"<option value='{esc(o)}'{' selected' if o == selected else ''}>{esc(o.capitalize())}</option>" for o in options)
    return f"<select name='{name}'>{opts}</select>"


def _err_cell(errors: dict[int, list[str]], i: int) -> str:
    return "".join(f"<p class='fc-err'>{esc(e)}</p>" for e in errors.get(i, []))


def _values(form: dict[str, list[str]] | None, prefix: str, field_name: str, i: int, default: Any) -> Any:
    if form is None:
        return default
    return (form.get(f"{prefix}_{field_name}_{i}") or [""])[0]


def render_finanzas_captura(
    conn,
    *,
    csrf_token: str,
    section: str | None = None,
    result: SectionResult | None = None,
    form: dict[str, list[str]] | None = None,
    saved: dict[str, int] | None = None,
    horizon_days: int = 30,
    extra_html: str = "",
) -> str:
    today = _today()
    debts_by_creditor, cash, obligations = load_v2_inputs(conn, as_of=today, horizon_days=horizon_days)
    errors = result.errors if result else {}

    def failed(name: str) -> dict[str, list[str]] | None:
        return form if section == name and result and not result.ok else None

    message = ""
    if result and not result.ok:
        message = f"<div class='fc-msg fc-bad'>No se guardó nada en esa sección: corrige {len(errors)} fila(s) en rojo.</div>"
    elif saved:
        message = f"<div class='fc-msg fc-ok'>Guardado: {saved.get('nuevos', 0)} nuevo(s), {saved.get('cambios', 0)} actualizado(s).</div>"

    # Caja
    accounts = conn.execute(
        "SELECT account_id, account_name, account_type, balance_mxn, available, cut_date FROM finance_cash_balances ORDER BY account_id"
    ).fetchall()
    f = failed("caja")
    caja_rows = []
    for i, a in enumerate(list(accounts) + [None] * NEW_ROWS["caja"]):
        rid = a["account_id"] if a else ""
        avail = _values(f, "caja", "disponible", i, "si" if (a is None or a["available"]) else "") == "si"
        caja_rows.append(f"""
        <tr class="{'fc-error' if f is not None and i in errors else ('fc-new' if a is None else '')}">
          <td><input type="hidden" name="caja_id_{i}" value="{rid}">{_input(f'caja_nombre_{i}', _values(f, 'caja', 'nombre', i, a['account_name'] if a else ''), attrs="placeholder='Ej. BBVA, Caja tienda'")}{_err_cell(errors if f is not None else {}, i)}</td>
          <td>{_select(f'caja_tipo_{i}', CASH_TYPES, _values(f, 'caja', 'tipo', i, a['account_type'] if a else 'Cuenta'))}</td>
          <td>{_input(f'caja_saldo_{i}', _values(f, 'caja', 'saldo', i, a['balance_mxn'] if a else ''), attrs="inputmode='decimal' placeholder='$'")}</td>
          <td style="text-align:center"><input type="checkbox" name="caja_disponible_{i}" value="si"{' checked' if avail else ''}></td>
          <td style="color:#667085;padding:12px 8px">{a['cut_date'].strftime('%d/%m/%Y') if a else '—'}</td>
        </tr>""")

    # Pagos: pendientes desde hace 30 días hasta 90 días adelante
    payments = conn.execute(
        """
        SELECT payment_id, due_date, concept, creditor, amount_mxn, status, account_ref, category
        FROM finance_scheduled_payments
        WHERE status IN ('pendiente', 'por confirmar') AND due_date BETWEEN %s AND %s
        ORDER BY due_date, payment_id
        """,
        (today - timedelta(days=30), today + timedelta(days=90)),
    ).fetchall()
    f = failed("pagos")
    pago_rows = []
    for i, p in enumerate(list(payments) + [None] * NEW_ROWS["pagos"]):
        overdue = p is not None and p["due_date"] < today
        pago_rows.append(f"""
        <tr class="{'fc-error' if f is not None and i in errors else ('fc-new' if p is None else '')}">
          <td><input type="hidden" name="pagos_id_{i}" value="{p['payment_id'] if p else ''}">{_input(f'pagos_fecha_{i}', _values(f, 'pagos', 'fecha', i, p['due_date'].isoformat() if p else today.isoformat()), kind='date')}{"<p class='fc-err'>Vencido</p>" if overdue else ''}{_err_cell(errors if f is not None else {}, i)}</td>
          <td>{_input(f'pagos_concepto_{i}', _values(f, 'pagos', 'concepto', i, p['concept'] if p else ''))}</td>
          <td>{_input(f'pagos_acreedor_{i}', _values(f, 'pagos', 'acreedor', i, p['creditor'] if p else ''), attrs="list='fc-acreedores'")}</td>
          <td>{_input(f'pagos_monto_{i}', _values(f, 'pagos', 'monto', i, p['amount_mxn'] if p else ''), attrs="inputmode='decimal' placeholder='$'")}</td>
          <td>{_select(f'pagos_estado_{i}', PAYMENT_STATUSES, _values(f, 'pagos', 'estado', i, p['status'] if p else 'pendiente'))}</td>
          <td>{_input(f'pagos_cuenta_{i}', _values(f, 'pagos', 'cuenta', i, p['account_ref'] if p else ''))}</td>
          <td>{_input(f'pagos_categoria_{i}', _values(f, 'pagos', 'categoria', i, p['category'] if p else ''))}</td>
        </tr>""")

    # Deudas
    debts = conn.execute(
        "SELECT debt_id, creditor, balance_mxn, status FROM finance_debts ORDER BY status, lower(creditor)"
    ).fetchall()
    f = failed("deudas")
    deuda_rows = []
    for i, d in enumerate(list(debts) + [None] * NEW_ROWS["deudas"]):
        deuda_rows.append(f"""
        <tr class="{'fc-error' if f is not None and i in errors else ('fc-new' if d is None else '')}">
          <td><input type="hidden" name="deudas_id_{i}" value="{d['debt_id'] if d else ''}">{_input(f'deudas_acreedor_{i}', _values(f, 'deudas', 'acreedor', i, d['creditor'] if d else ''), attrs="list='fc-acreedores'")}{_err_cell(errors if f is not None else {}, i)}</td>
          <td>{_input(f'deudas_saldo_{i}', _values(f, 'deudas', 'saldo', i, d['balance_mxn'] if d else ''), attrs="inputmode='decimal' placeholder='$'")}</td>
          <td>{_select(f'deudas_estado_{i}', DEBT_STATUSES, _values(f, 'deudas', 'estado', i, d['status'] if d else 'activa'))}</td>
        </tr>""")

    creditors = sorted({r["creditor"] for r in debts} | {r["creditor"] for r in payments if r["creditor"]})
    datalist = "".join(f"<option value='{esc(c)}'></option>" for c in creditors)

    def form_block(name: str, title: str, hint: str, headers: list[str], rows: list[str], total_rows: int) -> str:
        return f"""
        <div class="section-title" id="{name}" style="margin-top:8px"><h2>{title}</h2><span>{hint}</span></div>
        <form method="post" action="/finanzas/captura/{name}">
          <input type="hidden" name="csrf" value="{esc(csrf_token)}">
          <input type="hidden" name="{name}_n" value="{total_rows}">
          <div class="fc-wrap"><table class="fc-table">
            <thead><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table></div>
          <div class="fc-actions"><button type="submit">Guardar {title.lower()}</button>
          <span style="color:#667085">Las filas vacías se ignoran. Si una fila tiene error no se guarda ninguna de esta sección.</span></div>
        </form>"""

    pending_total = obligations.get("total") or 0
    content = f"""
    {CSS}
    <div class="section-title"><h2>Captura de finanzas</h2><span>Sustituye las pestañas Caja externa, Próximos pagos y Deudas de la hoja.</span></div>
    <div class="fc-nav"><a href="#caja">Caja</a><a href="#pagos">Pagos programados</a><a href="#deudas">Deudas</a><a href="/finance">Ver proyección →</a></div>
    {message}
    <div class="fc-kpis">
      <div class="fc-kpi"><div class="k">CAJA DISPONIBLE</div><div class="v">{money(cash.get('total') or 0)}</div><div class="n">Efectivo {money(cash.get('cash') or 0)} · cuentas {money(cash.get('accounts') or 0)}</div></div>
      <div class="fc-kpi"><div class="k">PAGOS PRÓXIMOS {horizon_days} DÍAS</div><div class="v">{money(pending_total)}</div><div class="n">{len(obligations.get('payments') or [])} pago(s) pendientes o por confirmar</div></div>
      <div class="fc-kpi"><div class="k">DEUDA ACTIVA</div><div class="v">{money(sum(debts_by_creditor.values()))}</div><div class="n">{len(debts_by_creditor)} acreedor(es)</div></div>
      <div class="fc-kpi"><div class="k">CAJA MENOS PAGOS PRÓXIMOS</div><div class="v">{money((cash.get('total') or 0) - pending_total)}</div><div class="n">Antes de ventas futuras</div></div>
    </div>
    <datalist id="fc-acreedores">{datalist}</datalist>
    {form_block('caja', 'Caja', 'Saldos de efectivo y cuentas. Marca "Disponible" solo si ese dinero se puede usar.',
                ['Cuenta', 'Tipo', 'Saldo actual', 'Disponible', 'Corte'], caja_rows, len(caja_rows))}
    {form_block('pagos', 'Pagos programados', 'Pendientes de los últimos 30 días a los próximos 90. Cambia el estado a Pagado al liquidar.',
                ['Fecha', 'Concepto', 'Acreedor', 'Monto', 'Estado', 'Cuenta / referencia', 'Categoría'], pago_rows, len(pago_rows))}
    {form_block('deudas', 'Deudas', 'Saldo vigente por acreedor. Márcala Liquidada cuando ya no se deba nada.',
                ['Acreedor', 'Saldo actual', 'Estado'], deuda_rows, len(deuda_rows))}
    {extra_html}
    """
    return base_page("Captura de finanzas", content)
