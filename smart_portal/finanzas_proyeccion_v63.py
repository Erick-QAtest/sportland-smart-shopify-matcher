from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path
from typing import Any
import json

from smart_portal.portal_v60 import base_page, esc, money, read_json


def _numero(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _buscar_numero(obj: Any, claves: tuple[str, ...]) -> float | None:
    """Busca de forma recursiva un KPI numérico sin depender de una sola versión del snapshot."""
    if isinstance(obj, dict):
        for clave in claves:
            if clave in obj:
                valor = _numero(obj.get(clave))
                if valor is not None:
                    return valor
        for valor in obj.values():
            encontrado = _buscar_numero(valor, claves)
            if encontrado is not None:
                return encontrado
    elif isinstance(obj, list):
        for valor in obj:
            encontrado = _buscar_numero(valor, claves)
            if encontrado is not None:
                return encontrado
    return None


def inferir_finanzas(snapshot: dict[str, Any]) -> dict[str, Any]:
    ventas_30d = _buscar_numero(
        snapshot,
        (
            "sales_30d",
            "ventas_30d",
            "revenue_30d",
            "net_sales_30d",
            "gross_sales_30d",
        ),
    ) or 0.0

    pedidos_30d = _buscar_numero(
        snapshot,
        ("orders_30d", "pedidos_30d", "order_count_30d"),
    ) or 0.0

    inventario = _buscar_numero(
        snapshot,
        (
            "inventory_retail_value",
            "retail_inventory_value",
            "inventory_value",
            "stock_value",
            "inventory_amount",
            "inventory_cost",
            "inventory_value_at_cost",
        ),
    )

    margen = _buscar_numero(
        snapshot,
        (
            "gross_margin_rate",
            "gross_margin_pct",
            "gross_margin",
            "margin_rate",
            "margin_pct",
        ),
    )

    if margen is not None and margen > 1:
        margen = margen / 100.0
    if margen is not None and not (0 <= margen < 1):
        margen = None

    ticket = (ventas_30d / pedidos_30d) if pedidos_30d > 0 else None

    return {
        "ventas_30d": ventas_30d,
        "pedidos_30d": pedidos_30d,
        "inventario": inventario,
        "margen": margen,
        "ticket_promedio": ticket,
    }


DIAS_SERIE = 180


def serie_diaria(snapshot: dict[str, Any], ventas_30d: float, hoy: date, dias: int = DIAS_SERIE) -> tuple[list[float], int]:
    """Venta esperada por día. Con historial usa la proyección por temporada del mes
    (escenario base); sin historial, el ritmo plano de los últimos 30 días."""
    fc = snapshot.get("seasonal_forecast") or {}
    por_mes = {(m["year"], m["month"]): m.get("base") for m in fc.get("months") or []}
    serie, dias_temporada = [], 0
    for d in range(dias):
        dia = hoy + timedelta(days=d)
        base = por_mes.get((dia.year, dia.month))
        if base is None:
            serie.append(round(ventas_30d / 30, 2))
        else:
            serie.append(round(base / monthrange(dia.year, dia.month)[1], 2))
            dias_temporada += 1
    return serie, dias_temporada


def _pct(value: Any) -> str:
    try:
        return f"{float(value):+.0%}"
    except (TypeError, ValueError):
        return "—"


def render_temporada(fc: dict[str, Any]) -> str:
    """Tabla de la proyección por mes contra años anteriores y qué tan confiable es."""
    if not fc or not fc.get("months"):
        return """
  <div class="panel full" id="temporada">
    <h2>Temporada</h2>
    <div class="callout">Todavía no hay historial de ventas por mes. Captúralo en <a href="/finanzas/captura#ventas">Captura de finanzas → Ventas por mes</a>
    o impórtalo de la pestaña Ventas; mientras tanto la proyección usa el ritmo de los últimos 30 días.</div>
  </div>"""
    filas = []
    for m in fc["months"]:
        vs = (m["base"] / m["last_year"] - 1) if m.get("base") and m.get("last_year") else None
        filas.append(f"""<tr>
          <td><b>{esc(str(m['label']).capitalize())}</b></td>
          <td>{money(m['low']) if m.get('low') is not None else '—'}</td>
          <td><b>{money(m['base']) if m.get('base') is not None else '—'}</b></td>
          <td>{money(m['high']) if m.get('high') is not None else '—'}</td>
          <td>{money(m['last_year']) if m.get('last_year') else '—'} <span style="color:#667085">{_pct(vs) if vs is not None else ''}</span></td>
          <td>{money(m['two_years_ago']) if m.get('two_years_ago') else '—'}</td>
          <td>{f"{m['seasonal_index']:.2f}×" if m.get('seasonal_index') else '—'}</td>
        </tr>""")
    trend = fc.get("trend") or {}
    bt = fc.get("backtest") or {}
    avisos = []
    if fc.get("missing_months"):
        avisos.append(f"<b>Faltan las ventas de {esc(', '.join(fc['missing_months']))}.</b> "
                      "La tendencia se calcula con los últimos meses que sí tienen dato; "
                      "<a href='/finanzas/captura#ventas'>captúralos aquí</a> para afinarla.")
    if trend:
        avisos.append(f"Este año va <b>{_pct(trend.get('raw', 1) - 1)}</b> contra el año pasado "
                      f"({esc(', '.join(trend.get('months') or []))}: {money(trend.get('current_total'))} vs {money(trend.get('previous_total'))}).")
    if bt.get("n"):
        avisos.append(
            f"<b>Precisión probada:</b> proyectando cada uno de {bt['n']} meses pasados solo con lo que se sabía antes, "
            f"el error medio fue {bt['mape']:.0%} (noviembre-diciembre {bt['peak_mape']:.0%}). "
            f"El método anterior (ritmo reciente) se equivocaba {bt['naive_mape']:.0%} (noviembre-diciembre {bt['peak_naive_mape']:.0%})."
            + (f" La venta real quedó arriba del escenario conservador en {bt['above_low_pct']:.0%} de los meses." if bt.get("above_low_pct") is not None else ""))
    return f"""
  <div class="panel full" id="temporada">
    <h2>Temporada: próximos meses contra años anteriores</h2>
    <div class="hint">Ventas totales de la tienda (efectivo + tarjeta + plataformas). Historial desde {esc(fc.get('history_from') or '—')}; último mes con dato: {esc(fc.get('last_month_with_data') or '—')}.</div>
    <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px;min-width:640px">
      <thead><tr style="text-align:left;color:#475467"><th>Mes</th><th>Conservador</th><th>Base</th><th>Optimista</th><th>Año pasado</th><th>Hace 2 años</th><th>Peso del mes</th></tr></thead>
      <tbody>{''.join(filas)}</tbody>
    </table></div>
    <div class="callout" style="margin-top:12px">{'<br>'.join(avisos)}<br>
      <span class="fin-note">Base = promedio de dos cálculos: mismo mes del año pasado × tendencia del año, y peso histórico del mes × nivel actual de ventas.
      Conservador y optimista salen de los aciertos y errores reales del modelo en meses pasados. "Peso del mes" 2.0× = ese mes vende el doble de un mes normal.</span>
    </div>
  </div>"""


def _valor_js(value: float | None, fallback: float) -> str:
    return str(round(value if value is not None else fallback, 2))


def render_finanzas_proyeccion(project_root: Path) -> str:
    snapshot = read_json(project_root / "artifacts" / "financial_snapshot.json")
    datos = inferir_finanzas(snapshot)

    ventas_30d = float(datos["ventas_30d"] or 0)
    inventario = datos["inventario"]
    margen = datos["margen"]
    ticket = datos["ticket_promedio"]

    # Si no existe valor monetario de inventario en el snapshot, no se inventa.
    # Se propone una cantidad editable basada únicamente en ventas recientes para que
    # la simulación pueda utilizarse, claramente marcada como valor de trabajo.
    inventario_detectado = inventario is not None and inventario > 0
    inventario_inicial = inventario if inventario_detectado else max(ventas_30d * 1.5, 10000)
    margen_inicial = margen if margen is not None else 0.35

    fuente_inventario = (
        "Detectado en el snapshot financiero actual."
        if inventario_detectado
        else "No detectado en el snapshot; el valor inicial es solo un punto de trabajo editable."
    )

    fuente_margen = (
        f"Margen detectado: {margen * 100:.1f}%."
        if margen is not None
        else "Margen no detectado; la simulación inicia en 35% y puede ajustarse."
    )

    ticket_texto = money(ticket) if ticket is not None else "—"
    fc = snapshot.get("seasonal_forecast") or {}
    serie, dias_temporada = serie_diaria(snapshot, ventas_30d, date.today())
    con_temporada = dias_temporada > 0
    vs_anio = (snapshot.get("kpis") or {}).get("sales_change_vs_last_year")
    como_se_calcula = (
        "demanda probable = venta esperada de cada mes según la temporada (historial de años anteriores) × factor de demanda."
        if con_temporada else
        "demanda probable = ventas 30d × horizonte × factor de demanda (sin historial por mes todavía)."
    )

    contenido = f"""
<style>
.fin-grid{{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}}
.fin-control{{grid-column:span 4;background:#fff;border:1px solid #e4e7ec;border-radius:18px;padding:18px}}
.fin-chart{{grid-column:span 8;background:#fff;border:1px solid #e4e7ec;border-radius:18px;padding:18px;min-height:410px}}
.fin-kpi{{grid-column:span 3;background:#fff;border:1px solid #e4e7ec;border-radius:16px;padding:16px}}
.fin-kpi .et{{font-size:10px;color:#175cd3;font-weight:850;letter-spacing:.05em}}
.fin-kpi .vl{{font-size:26px;font-weight:900;margin-top:7px}}
.fin-kpi .nt{{font-size:11px;color:#667085;margin-top:5px;line-height:1.4}}
.ctrl{{margin:14px 0}}
.ctrl label{{display:flex;justify-content:space-between;gap:10px;font-size:12px;font-weight:800;margin-bottom:7px}}
.ctrl input[type=range]{{width:100%}}
.ctrl select{{width:100%;padding:9px;border:1px solid #d0d5dd;border-radius:10px;background:#fff}}
.scenarios{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:15px}}
.scenario{{border:1px solid #e4e7ec;border-radius:13px;padding:12px;background:#fafcff}}
.scenario b{{font-size:12px}} .scenario .n{{font-size:19px;font-weight:900;margin-top:5px}}
.legend{{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:#667085;margin-top:8px}}
.dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:4px}}
.fin-note{{font-size:11px;color:#667085;line-height:1.5}}
@media(max-width:900px){{.fin-control,.fin-chart{{grid-column:1/-1}}.fin-kpi{{grid-column:span 6}}}}
@media(max-width:620px){{.fin-kpi{{grid-column:1/-1}}.scenarios{{grid-template-columns:1fr}}}}
</style>

<div class="section-title">
  <h2>Proyección dinámica de inventario y ventas</h2>
  <span>Modelo de escenarios · no sustituye ventas reales</span>
</div>

<div class="fin-grid">
  <div class="fin-kpi">
    <div class="et">VENTAS RECIENTES</div>
    <div class="vl">{money(ventas_30d)}</div>
    <div class="nt">Ventas observadas en los últimos 30 días.</div>
  </div>
  <div class="fin-kpi">
    <div class="et">INVENTARIO DE TRABAJO</div>
    <div class="vl" id="kpiInventario">{money(inventario_inicial)}</div>
    <div class="nt">{esc(fuente_inventario)}</div>
  </div>
  <div class="fin-kpi">
    <div class="et">TICKET PROMEDIO</div>
    <div class="vl">{ticket_texto}</div>
    <div class="nt">Calculado con ventas y pedidos de 30 días, cuando ambos están disponibles.</div>
  </div>
  <div class="fin-kpi">
    <div class="et">VS AÑO PASADO</div>
    <div class="vl">{_pct(vs_anio) if vs_anio is not None else "—"}</div>
    <div class="nt">Últimos meses completos contra los mismos meses del año anterior.</div>
  </div>
  <div class="fin-kpi">
    <div class="et">VENTA PROBABLE</div>
    <div class="vl" id="kpiVentaProbable">—</div>
    <div class="nt" id="kpiVentaNota">Escenario base.</div>
  </div>

  <div class="fin-control">
    <h2 style="margin:0 0 4px;font-size:16px">Supuestos editables</h2>
    <div class="fin-note">Mueve los controles y la proyección se recalcula en tiempo real.</div>

    <div class="ctrl">
      <label><span>Monto de inventario</span><span id="inventarioLabel"></span></label>
      <input id="inventario" type="range" min="5000" max="{max(50000, int(inventario_inicial * 4))}" step="1000" value="{int(inventario_inicial)}">
    </div>

    <div class="ctrl">
      <label><span>Horizonte de proyección</span><span id="horizonteLabel">60 días</span></label>
      <input id="horizonte" type="range" min="30" max="180" step="30" value="60">
    </div>

    <div class="ctrl">
      <label><span>Demanda esperada</span><span id="demandaLabel">100%</span></label>
      <input id="demanda" type="range" min="50" max="160" step="5" value="100">
    </div>

    <div class="ctrl">
      <label><span>Margen bruto</span><span id="margenLabel">{margen_inicial*100:.0f}%</span></label>
      <input id="margen" type="range" min="10" max="70" step="1" value="{round(margen_inicial*100)}">
      <div class="fin-note">{esc(fuente_margen)}</div>
    </div>

    <div class="ctrl">
      <label><span>Interpretar inventario como</span></label>
      <select id="tipoInventario">
        <option value="venta">Valor de venta</option>
        <option value="costo">Costo invertido</option>
      </select>
    </div>

    <div class="callout">
      <b>Cómo se calcula:</b><br>
      {como_se_calcula}<br>
      La venta proyectada nunca puede superar la capacidad de venta del inventario.
    </div>
  </div>

  <div class="fin-chart">
    <h2 style="margin:0 0 4px;font-size:16px">Ventas acumuladas probables</h2>
    <div class="hint">La curva se limita por demanda y por inventario disponible.</div>
    <svg id="grafica" viewBox="0 0 820 320" width="100%" height="320" role="img" aria-label="Gráfica de ventas probables">
      <g id="grid"></g>
      <g id="curvas"></g>
      <g id="ejes"></g>
    </svg>
    <div class="legend">
      <span style="color:#667085"><span class="dot"></span>Conservador</span>
      <span style="color:#175cd3"><span class="dot"></span>Base</span>
      <span style="color:#067647"><span class="dot"></span>Optimista</span>
    </div>

    <div class="scenarios">
      <div class="scenario"><b>Conservador</b><div class="n" id="consValor">—</div><div class="fin-note">70% de la demanda elegida</div></div>
      <div class="scenario"><b>Base</b><div class="n" id="baseValor">—</div><div class="fin-note">100% de la demanda elegida</div></div>
      <div class="scenario"><b>Optimista</b><div class="n" id="optValor">—</div><div class="fin-note">120% de la demanda elegida</div></div>
    </div>
  </div>

  {render_temporada(fc)}

  <div class="panel full">
    <h2>Lectura ejecutiva</h2>
    <div id="lectura" class="callout">Calculando escenario...</div>
  </div>

  <div class="panel full">
    <h2>Reporte financiero completo</h2>
    <div class="hint">La proyección es una capa adicional; el dashboard financiero original sigue disponible.</div>
    <a href="/finance/reporte" style="display:inline-block;background:#071b33;color:#fff;padding:10px 14px;border-radius:10px;font-weight:850;font-size:12px">Abrir reporte financiero →</a>
  </div>
</div>

<script>
(() => {{
  const ventas30 = {_valor_js(ventas_30d, 0)};
  const diario = {json.dumps(serie)};
  const conTemporada = {'true' if con_temporada else 'false'};
  const acumulado = [0];
  diario.forEach(v => acumulado.push(acumulado[acumulado.length - 1] + v));
  const demandaHasta = d => acumulado[Math.min(Math.round(d), diario.length)];
  const fmt = new Intl.NumberFormat('es-MX', {{style:'currency', currency:'MXN', maximumFractionDigits:0}});

  const inv = document.getElementById('inventario');
  const hor = document.getElementById('horizonte');
  const dem = document.getElementById('demanda');
  const mar = document.getElementById('margen');
  const tipo = document.getElementById('tipoInventario');

  const $ = id => document.getElementById(id);

  function capacidadVenta() {{
    const inventario = Number(inv.value);
    const margen = Number(mar.value) / 100;
    if (tipo.value === 'costo') {{
      return inventario / Math.max(0.05, 1 - margen);
    }}
    return inventario;
  }}

  function ventasEscenario(mult) {{
    const dias = Number(hor.value);
    const demanda = Number(dem.value) / 100;
    const demandaPeriodo = demandaHasta(dias) * demanda * mult;
    return Math.min(demandaPeriodo, capacidadVenta());
  }}

  function serie(mult) {{
    const dias = Number(hor.value);
    const puntos = [];
    for (let d = 0; d <= dias; d += Math.max(5, dias/12)) {{
      const demanda = demandaHasta(d) * (Number(dem.value)/100) * mult;
      puntos.push([d, Math.min(demanda, capacidadVenta())]);
    }}
    if (puntos[puntos.length-1][0] !== dias) {{
      const demanda = demandaHasta(dias) * (Number(dem.value)/100) * mult;
      puntos.push([dias, Math.min(demanda, capacidadVenta())]);
    }}
    return puntos;
  }}

  function pathFor(points, maxY) {{
    const left=64, top=18, width=720, height=250;
    return points.map((p,i) => {{
      const x = left + (p[0] / Number(hor.value)) * width;
      const y = top + height - (p[1] / maxY) * height;
      return `${{i ? 'L' : 'M'}} ${{x.toFixed(1)}} ${{y.toFixed(1)}}`;
    }}).join(' ');
  }}

  function renderChart() {{
    const cons = serie(.70), base = serie(1), opt = serie(1.20);
    const maxY = Math.max(capacidadVenta(), ...opt.map(p=>p[1]), 1);
    const grid = $('grid');
    const curvas = $('curvas');
    const ejes = $('ejes');

    let gridHtml='';
    for (let i=0;i<=4;i++) {{
      const y=18+(250/4)*i;
      const val=maxY*(1-i/4);
      gridHtml += `<line x1="64" y1="${{y}}" x2="784" y2="${{y}}" stroke="#edf0f4"/>`;
      gridHtml += `<text x="58" y="${{y+4}}" text-anchor="end" font-size="10" fill="#667085">${{Math.round(val/1000)}}k</text>`;
    }}
    grid.innerHTML=gridHtml;

    curvas.innerHTML = `
      <path d="${{pathFor(cons,maxY)}}" fill="none" stroke="#667085" stroke-width="3"/>
      <path d="${{pathFor(base,maxY)}}" fill="none" stroke="#175cd3" stroke-width="4"/>
      <path d="${{pathFor(opt,maxY)}}" fill="none" stroke="#067647" stroke-width="3"/>
      <line x1="64" y1="${{18+250-(capacidadVenta()/maxY)*250}}" x2="784" y2="${{18+250-(capacidadVenta()/maxY)*250}}" stroke="#b54708" stroke-width="2" stroke-dasharray="6 5"/>
    `;

    const dias=Number(hor.value);
    ejes.innerHTML = `
      <line x1="64" y1="268" x2="784" y2="268" stroke="#98a2b3"/>
      <text x="64" y="290" font-size="10" fill="#667085">0 días</text>
      <text x="420" y="290" text-anchor="middle" font-size="10" fill="#667085">${{Math.round(dias/2)}} días</text>
      <text x="784" y="290" text-anchor="end" font-size="10" fill="#667085">${{dias}} días</text>
      <text x="780" y="${{Math.max(14,18+250-(capacidadVenta()/maxY)*250-7)}}" text-anchor="end" font-size="10" fill="#b54708">límite por inventario</text>
    `;
  }}

  function actualizar() {{
    const inventario = Number(inv.value);
    const dias = Number(hor.value);
    const demandaPct = Number(dem.value);
    const margenPct = Number(mar.value);

    $('inventarioLabel').textContent = fmt.format(inventario);
    $('horizonteLabel').textContent = `${{dias}} días`;
    $('demandaLabel').textContent = `${{demandaPct}}%`;
    $('margenLabel').textContent = `${{margenPct}}%`;
    $('kpiInventario').textContent = fmt.format(inventario);

    const c = ventasEscenario(.70);
    const b = ventasEscenario(1);
    const o = ventasEscenario(1.20);

    $('consValor').textContent = fmt.format(c);
    $('baseValor').textContent = fmt.format(b);
    $('optValor').textContent = fmt.format(o);
    $('kpiVentaProbable').textContent = fmt.format(b);
    $('kpiVentaNota').textContent = `Escenario base a ${{dias}} días`;

    const capacidad = capacidadVenta();
    const demandaBase = demandaHasta(dias) * (demandaPct/100);
    const ritmoMensual = dias > 0 ? demandaHasta(dias) / dias * 30 : ventas30;
    const coberturaMeses = ritmoMensual > 0 ? capacidad / ritmoMensual : 0;
    const remanente = Math.max(0, capacidad - b);
    const limitado = demandaBase > capacidad;

    let texto = '';
    if (!conTemporada && ventas30 <= 0) {{
      texto = '<b>No hay ventas de 30 días suficientes para una proyección confiable.</b> Ajusta el modelo solo como simulación.';
    }} else if (limitado) {{
      texto = `<b>El inventario es el límite principal del escenario base.</b> Con los supuestos actuales, la demanda potencial sería ${{fmt.format(demandaBase)}}, pero el inventario permite aproximadamente ${{fmt.format(capacidad)}} en ventas. Cobertura aproximada: ${{coberturaMeses.toFixed(1)}} meses.`;
    }} else {{
      texto = `<b>La demanda es el límite principal del escenario base.</b> La venta probable es ${{fmt.format(b)}} y quedaría capacidad de inventario por aproximadamente ${{fmt.format(remanente)}}. Cobertura aproximada: ${{coberturaMeses.toFixed(1)}} meses.`;
    }}
    $('lectura').innerHTML = texto;

    renderChart();
  }}

  [inv,hor,dem,mar,tipo].forEach(el => el.addEventListener('input',actualizar));
  tipo.addEventListener('change',actualizar);
  actualizar();
}})();
</script>
"""
    return base_page("Finanzas", contenido)
