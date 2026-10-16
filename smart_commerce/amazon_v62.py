from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from smart_portal.portal_v60 import base_page, esc, money


ALIASES = {
    "fecha": {"fecha","date","metric_date","día","dia"},
    "tracking_id": {"tracking_id","tracking id","id_de_seguimiento","id seguimiento","trackingid"},
    "link_id": {"link_id","link id","id_de_enlace","id enlace","subtag","sub_tag","linkid"},
    "titulo_contenido": {"titulo_contenido","título contenido","titulo contenido","content_title","title"},
    "url_contenido": {"url_contenido","url de contenido","content_url","page_url","source_url"},
    "canal": {"canal","channel","source","fuente"},
    "clics": {"clics","clicks","click","click_count"},
    "productos_pedidos": {"productos_pedidos","productos pedidos","ordered_items","ordered items","items_ordered"},
    "productos_enviados": {"productos_enviados","productos enviados","shipped_items","shipped items","items_shipped"},
    "ventas_atribuidas": {"ventas_atribuidas","ventas atribuidas","ordered_revenue","ordered revenue","revenue","sales","ordered_sales"},
    "comisiones": {"comisiones","comision","comisión","earnings","advertising_fees","fees"},
    "moneda": {"moneda","currency","currency_code"},
}


def _norm(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.replace("-", "_")
    return re.sub(r"\s+", " ", raw)


def _canon(header: Any) -> str | None:
    h = _norm(header)
    for key, aliases in ALIASES.items():
        if h in {_norm(a) for a in aliases}:
            return key
    return None


def _decimal(value: Any) -> Decimal | None:
    raw = str(value or "").strip().replace("\u00a0", " ")
    raw = re.sub(r"[A-Za-z$€£¥%]", "", raw).strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        tail = raw.split(",")[-1]
        raw = raw.replace(".", "").replace(",", ".") if len(tail) in {1,2} else raw.replace(",", "")
    raw = raw.replace(" ", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _entero(value: Any) -> int:
    v = _decimal(value)
    return max(0, int(v)) if v is not None else 0


def _fecha(value: Any, fallback: date) -> date:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return fallback


def _leer_csv(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig","utf-8","latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                sample = f.read(8192)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                return [dict(x) for x in csv.DictReader(f, dialect=dialect)]
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"No se pudo leer {path.name}")


def _normalizar(raw: dict[str, Any]) -> dict[str, Any]:
    row = {}
    for key, value in raw.items():
        c = _canon(key)
        if c and c not in row:
            row[c] = value
    return row


def _hash(payload: dict[str, Any]) -> str:
    stable = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def cargar_mapeo(path: Path | None) -> list[dict[str, str | None]]:
    if not path or not path.exists():
        return []
    out = []
    for raw in _leer_csv(path):
        row = _normalizar(raw)
        tracking = str(row.get("tracking_id") or "").strip() or None
        link = str(row.get("link_id") or "").strip() or None
        if tracking or link:
            out.append({
                "tracking_id": tracking,
                "link_id": link,
                "titulo_contenido": str(row.get("titulo_contenido") or "").strip() or None,
                "url_contenido": str(row.get("url_contenido") or "").strip() or None,
                "canal": str(row.get("canal") or "").strip() or None,
            })
    return out


def _encontrar_mapeo(tracking: str | None, link: str | None, maps: list[dict[str, Any]]):
    exact = [m for m in maps if m.get("tracking_id")==tracking and m.get("link_id")==link and (tracking or link)]
    if len(exact) == 1:
        return exact[0]
    if link:
        by_link = [m for m in maps if m.get("link_id")==link]
        if len(by_link) == 1:
            return by_link[0]
    if tracking:
        by_tracking = [m for m in maps if m.get("tracking_id")==tracking]
        if len(by_tracking) == 1:
            return by_tracking[0]
    return None


def preparar_filas(path: Path, fecha_corte: date, maps: list[dict[str, Any]] | None = None):
    maps = maps or []
    result = []
    for raw in _leer_csv(path):
        row = _normalizar(raw)
        clics = _entero(row.get("clics"))
        pedidos = _entero(row.get("productos_pedidos"))
        enviados = _entero(row.get("productos_enviados"))
        ventas = _decimal(row.get("ventas_atribuidas"))
        comisiones = _decimal(row.get("comisiones"))
        if clics==0 and pedidos==0 and enviados==0 and not ventas and not comisiones:
            continue

        tracking = str(row.get("tracking_id") or "").strip() or None
        link = str(row.get("link_id") or "").strip() or None
        mapped = _encontrar_mapeo(tracking, link, maps)

        titulo = str(row.get("titulo_contenido") or "").strip() or None
        url = str(row.get("url_contenido") or "").strip() or None
        canal = str(row.get("canal") or "").strip() or None
        if mapped:
            titulo = titulo or mapped.get("titulo_contenido")
            url = url or mapped.get("url_contenido")
            canal = canal or mapped.get("canal")

        fecha = _fecha(row.get("fecha"), fecha_corte)
        moneda = str(row.get("moneda") or "").strip().upper() or "MXN"
        conversion = Decimal(pedidos)/Decimal(clics) if clics else None
        epc = comisiones/Decimal(clics) if clics and comisiones is not None else None

        payload = {
            "metric_date": fecha.isoformat(),
            "tracking_id": tracking,
            "link_id": link,
            "content_title": titulo,
            "content_url": url,
            "channel": canal,
            "clicks": clics,
            "ordered_items": pedidos,
            "shipped_items": enviados,
            "ordered_revenue": str(ventas) if ventas is not None else None,
            "earnings": str(comisiones) if comisiones is not None else None,
            "currency": moneda,
        }
        result.append({
            **payload,
            "conversion_rate": conversion,
            "earnings_per_click": epc,
            "source_row_hash": _hash(payload),
        })
    return result


def importar_reportes(conn, files: list[Path], fecha_corte: date, mapping_file: Path | None = None):
    maps = cargar_mapeo(mapping_file)
    started = datetime.now().astimezone()
    run_id = f"amazon-{started.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"

    conn.execute(
        """INSERT INTO amazon_import_runs(import_run_id,started_at,status,source_files,metadata)
           VALUES(%s,%s,'RUNNING',%s,%s)""",
        (run_id, started, len(files), Jsonb({"fecha_corte": fecha_corte.isoformat()})),
    )
    conn.commit()

    stats = {"import_run_id":run_id,"files":len(files),"rows_read":0,"rows_inserted":0,"rows_skipped":0,"mapping_rows":len(maps)}
    try:
        with conn.transaction():
            for m in maps:
                map_key = f"{m.get('tracking_id') or ''}|{m.get('link_id') or ''}"
                conn.execute(
                    """INSERT INTO amazon_content_map(map_key,tracking_id,link_id,content_url,content_title,channel)
                       VALUES(%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(map_key) DO UPDATE SET
                         content_url=COALESCE(EXCLUDED.content_url,amazon_content_map.content_url),
                         content_title=COALESCE(EXCLUDED.content_title,amazon_content_map.content_title),
                         channel=COALESCE(EXCLUDED.channel,amazon_content_map.channel),
                         active=TRUE,updated_at=now()""",
                    (map_key,m.get("tracking_id"),m.get("link_id"),m.get("url_contenido"),m.get("titulo_contenido"),m.get("canal")),
                )

            for file in files:
                rows = preparar_filas(file, fecha_corte, maps)
                stats["rows_read"] += len(rows)
                for r in rows:
                    inserted = conn.execute(
                        """INSERT INTO amazon_attribution_rows(
                             metric_date,tracking_id,link_id,content_url,content_title,channel,
                             clicks,ordered_items,shipped_items,ordered_revenue,earnings,currency,
                             conversion_rate,earnings_per_click,source_file,source_row_hash
                           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT(source_row_hash) DO NOTHING RETURNING amazon_row_id""",
                        (r["metric_date"],r["tracking_id"],r["link_id"],r["content_url"],r["content_title"],r["channel"],
                         r["clicks"],r["ordered_items"],r["shipped_items"],r["ordered_revenue"],r["earnings"],r["currency"],
                         r["conversion_rate"],r["earnings_per_click"],file.name,r["source_row_hash"]),
                    ).fetchone()
                    if inserted:
                        stats["rows_inserted"] += 1
                    else:
                        stats["rows_skipped"] += 1

        conn.execute(
            """UPDATE amazon_import_runs SET finished_at=now(),status='OK',
               rows_read=%s,rows_inserted=%s,rows_skipped=%s
               WHERE import_run_id=%s""",
            (stats["rows_read"],stats["rows_inserted"],stats["rows_skipped"],run_id),
        )
        conn.commit()
        return stats
    except Exception as exc:
        conn.rollback()
        conn.execute(
            """UPDATE amazon_import_runs SET finished_at=now(),status='FAILED',error_message=%s
               WHERE import_run_id=%s""",
            (str(exc)[:2000],run_id),
        )
        conn.commit()
        raise


def resumen_amazon(conn):
    actual = conn.execute(
        """SELECT
             COALESCE(SUM(clicks),0) clicks,
             COALESCE(SUM(ordered_items),0) ordered_items,
             COALESCE(SUM(ordered_revenue),0) ordered_revenue,
             COALESCE(SUM(earnings),0) earnings,
             CASE WHEN SUM(clicks)>0 THEN SUM(ordered_items)::NUMERIC/SUM(clicks) END conversion_rate,
             CASE WHEN SUM(clicks)>0 THEN SUM(COALESCE(earnings,0))::NUMERIC/SUM(clicks) END earnings_per_click
           FROM amazon_attribution_rows
           WHERE metric_date BETWEEN CURRENT_DATE-INTERVAL '29 days' AND CURRENT_DATE"""
    ).fetchone()
    anterior = conn.execute(
        """SELECT
             COALESCE(SUM(clicks),0) clicks,
             COALESCE(SUM(ordered_items),0) ordered_items,
             COALESCE(SUM(ordered_revenue),0) ordered_revenue,
             COALESCE(SUM(earnings),0) earnings,
             CASE WHEN SUM(clicks)>0 THEN SUM(ordered_items)::NUMERIC/SUM(clicks) END conversion_rate,
             CASE WHEN SUM(clicks)>0 THEN SUM(COALESCE(earnings,0))::NUMERIC/SUM(clicks) END earnings_per_click
           FROM amazon_attribution_rows
           WHERE metric_date BETWEEN CURRENT_DATE-INTERVAL '59 days' AND CURRENT_DATE-INTERVAL '30 days'"""
    ).fetchone()
    top = [dict(r) for r in conn.execute(
        """SELECT
             COALESCE(content_title,content_url,tracking_id,link_id,'Sin atribución') content_name,
             MAX(content_url) content_url,MAX(channel) channel,
             SUM(clicks) clicks,SUM(ordered_items) ordered_items,
             SUM(COALESCE(ordered_revenue,0)) ordered_revenue,
             SUM(COALESCE(earnings,0)) earnings,
             CASE WHEN SUM(clicks)>0 THEN SUM(ordered_items)::NUMERIC/SUM(clicks) END conversion_rate,
             CASE WHEN SUM(clicks)>0 THEN SUM(COALESCE(earnings,0))::NUMERIC/SUM(clicks) END earnings_per_click
           FROM amazon_attribution_rows
           WHERE metric_date BETWEEN CURRENT_DATE-INTERVAL '29 days' AND CURRENT_DATE
           GROUP BY COALESCE(content_title,content_url,tracking_id,link_id,'Sin atribución')
           ORDER BY SUM(COALESCE(earnings,0)) DESC,SUM(ordered_items) DESC,SUM(clicks) DESC
           LIMIT 50"""
    ).fetchall()]
    total = conn.execute("SELECT COUNT(*) n FROM amazon_attribution_rows").fetchone()
    return {"actual":dict(actual) if actual else {}, "anterior":dict(anterior) if anterior else {}, "top":top, "total":int(total["n"] if total else 0)}


def _pct(v):
    try: return f"{float(v)*100:.2f}%"
    except (TypeError,ValueError): return "—"


def _delta(a,b):
    try:
        a,b=float(a or 0),float(b or 0)
        if b==0: return "—"
        d=(a-b)/abs(b)*100
        return f"{'+' if d>=0 else ''}{d:.1f}%"
    except Exception:
        return "—"


def render_amazon(conn):
    d = resumen_amazon(conn)
    if d["total"] == 0:
        return base_page("Amazon", """
        <div class="panel full"><h2>Monetización con Amazon</h2>
        <div class="callout"><b>Aún no hay métricas importadas.</b><br><br>
        Coloca el reporte CSV en <code>imports/amazon/reportes/</code> y ejecuta:
        <br><br><code>python run_amazon_import.py</code><br><br>
        El portal calculará clics, productos pedidos, conversión, ventas atribuidas, comisiones e ingreso por clic.</div></div>
        """)

    a,p=d["actual"],d["anterior"]
    cards=[
        ("Clics Amazon",a.get("clicks",0),f"vs periodo anterior {_delta(a.get('clicks'),p.get('clicks'))}","TRÁFICO"),
        ("Productos pedidos",a.get("ordered_items",0),f"vs periodo anterior {_delta(a.get('ordered_items'),p.get('ordered_items'))}","CONVERSIÓN"),
        ("Conversión",_pct(a.get("conversion_rate")),f"antes {_pct(p.get('conversion_rate'))}","TASA"),
        ("Ventas atribuidas",money(a.get("ordered_revenue")),f"vs periodo anterior {_delta(a.get('ordered_revenue'),p.get('ordered_revenue'))}","VENTAS"),
        ("Comisiones",money(a.get("earnings")),f"vs periodo anterior {_delta(a.get('earnings'),p.get('earnings'))}","INGRESOS"),
        ("Ingreso por clic",money(a.get("earnings_per_click")),"comisiones / clics","EFICIENCIA"),
    ]
    card_html="".join(f"<div class='kpi'><div class='tag'>{esc(t)}</div><div class='label'>{esc(l)}</div><div class='value'>{esc(v)}</div><div class='note'>{esc(n)}</div></div>" for l,v,n,t in cards)
    body="".join(
        f"<tr><td><b>{esc(r.get('content_name'))}</b><br><span style='color:#98a2b3'>{esc(r.get('channel') or '')}</span></td>"
        f"<td>{r.get('clicks',0)}</td><td>{r.get('ordered_items',0)}</td><td>{_pct(r.get('conversion_rate'))}</td>"
        f"<td>{money(r.get('ordered_revenue'))}</td><td>{money(r.get('earnings'))}</td><td>{money(r.get('earnings_per_click'))}</td></tr>"
        for r in d["top"]
    ) or "<tr><td colspan='7'>Sin contenido atribuido.</td></tr>"
    return base_page("Amazon",f"""
    <div class="grid">{card_html}</div>
    <div class="panel full" style="margin-top:14px">
      <h2>Rendimiento por contenido</h2>
      <div class="hint">Últimos 30 días. Ordenado por comisiones, pedidos y clics.</div>
      <table><thead><tr><th>Contenido</th><th>Clics</th><th>Pedidos</th><th>Conversión</th><th>Ventas</th><th>Comisiones</th><th>Ingreso/clic</th></tr></thead><tbody>{body}</tbody></table>
    </div>
    """)
