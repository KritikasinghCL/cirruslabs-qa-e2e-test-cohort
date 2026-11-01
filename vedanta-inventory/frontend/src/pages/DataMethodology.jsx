import React from 'react'
import { useDataGaps } from '../hooks/useApi'
import { exportPDF } from '../utils/export'

// All 14 metrics from data_contract_v1.yaml §3
const FORMULAS = [
  {
    name: 'Days of Inventory (DOH)',
    formula: 'DOH = Current Stock ÷ Avg Daily Usage (365d)',
    detail: 'STOCK_ON_HAND = SUM(MARD.LABST) · AVG_DAILY_CONS = SUM(qty, last 365d) ÷ 365',
    source: 'MARD (stock) + MSEG (consumption)',
    status: 'Real data',
    target: 'Reduce NOM by 1–7 days',
    gaps: [],
  },
  {
    name: 'Inventory Value',
    formula: 'INV_VALUE = SUM(LABST × VERPR)',
    detail: 'Price cascade: VERPR → STPRS → LAEPR → 0 with price_missing flag',
    source: 'MARD.LABST + MBEW.VERPR/STPRS/LAEPR',
    status: 'Real data',
    target: 'Gross reduction ≥10% (quarterly/yearly vs lowest of past FY)',
    gaps: ['G-09: VERPR may be zero for non-valuated materials'],
  },
  {
    name: 'Inventory Turnover',
    formula: 'TURNOVER = COGS_365D ÷ AVG_INV_VALUE',
    detail: 'COGS_365D = SUM(qty × unit_price, last 365d) · AVG_INV_VALUE = current stock × price (G-03 fallback)',
    source: 'MSEG + MARD + MBEW',
    status: 'Real data',
    target: 'Increase YOY',
    gaps: ['G-03: using point-in-time stock as AVG_INV_VALUE (monthly snapshots not yet confirmed)'],
  },
  {
    name: 'Safety Stock',
    formula: 'SS = (Max Daily Usage × Max Lead Time) − (Avg Daily Usage × Avg Lead Time)',
    detail: 'Max/Avg daily usage and lead time from ContextFlow MCP forecast output',
    source: 'ContextFlow MCP',
    status: 'BLOCKED',
    target: 'N/A (input to ROP)',
    gaps: ['G-05: ContextFlow MCP endpoint not yet configured'],
  },
  {
    name: 'Reorder Point (ROP)',
    formula: 'ROP = (Avg Daily Usage × Lead Time) + Safety Stock',
    detail: 'Avg Daily Usage and Lead Time from ContextFlow MCP',
    source: 'ContextFlow MCP',
    status: 'BLOCKED',
    target: 'Real-time MRP/ROP adjustment 100%',
    gaps: ['G-05: ContextFlow MCP endpoint not yet configured'],
  },
  {
    name: 'Overstock Flag',
    formula: 'OVERSTOCK = Current Stock > (Forecast_3mo + Safety Stock) × 1.25',
    detail: 'OVERSTOCK_MARGIN_FACTOR = 1.25 (configurable)',
    source: 'ContextFlow MCP forecast + MARD',
    status: 'BLOCKED',
    target: 'Reduce overstock count',
    gaps: ['G-05: ContextFlow MCP endpoint not yet configured'],
  },
  {
    name: 'Understock Flag',
    formula: 'UNDERSTOCK = Current Stock < ROP',
    detail: 'ROP requires ContextFlow MCP',
    source: 'ContextFlow MCP + MARD',
    status: 'BLOCKED',
    target: 'Reduce understock count',
    gaps: ['G-05: ContextFlow MCP endpoint not yet configured'],
  },
  {
    name: 'Non-Moving Inventory (NMI)',
    formula: 'NMI = consumption = 0 for last 6 months AND stock > 0',
    detail: 'NMI_LOOKBACK_MONTHS = 6 (configurable). Scope: ZSPR + ZSPN with LABST > 0.',
    source: 'MSEG (consumption) + MARD (stock)',
    status: 'Real data',
    target: 'Reduce NMI count ≥10% per month',
    gaps: [],
  },
  {
    name: 'Slow-Moving Inventory (SMI)',
    formula: 'SMI = avg daily usage ≤ 20th percentile of population AND NOT NMI',
    detail: 'SMI_USAGE_THRESHOLD_PERCENTILE = 20 (configurable). Population = all ZSPR/ZSPN.',
    source: 'MSEG (consumption)',
    status: 'Real data',
    target: 'Reduce SMI count ≥20% per month',
    gaps: [],
  },
  {
    name: 'Fill Rate',
    formula: 'FILL_RATE = (Demand Met ÷ Total Demand) × 100%',
    detail: 'Demand Met = RESB.ENMNG · Total Demand = RESB.BDMNG',
    source: 'RESB (reservation/dependent requirements)',
    status: 'BLOCKED',
    target: 'N/A',
    gaps: ['G-02: RESB export not yet confirmed in GCS'],
  },
  {
    name: 'Critical Spares Availability',
    formula: 'AVAIL = (Days in Stock ÷ Total Days) × 100%',
    detail: 'Days in Stock = days where LABST > 0 (requires daily stock snapshot)',
    source: 'Daily MARD snapshot (not yet in GCS export)',
    status: 'BLOCKED',
    target: 'Critical spares availability >95%',
    gaps: ['G-01: CRITICAL_FLAG field unconfirmed', 'G-01: Daily stock snapshot not in scope'],
  },
  {
    name: 'Demand Forecast (ContextFlow)',
    formula: 'Forecast_3mo, Forecast_6mo, Forecast_12mo via ContextFlow MCP',
    detail: 'Input: consumption history + shutdown calendar. Output: qty forecast per horizon.',
    source: 'ContextFlow MCP endpoint',
    status: 'BLOCKED',
    target: 'Demand quantity prediction 100%',
    gaps: ['G-05: ContextFlow MCP endpoint not yet configured'],
  },
  {
    name: 'Forecast Accuracy %',
    formula: 'ACCURACY = 100% − MAPE · MAPE = avg(|Actual−Forecast| ÷ Actual) × 100%',
    detail: 'Computed on held-out periods only. Population: all ZSPR/ZSPN with actuals.',
    source: 'ContextFlow MCP post-actuals',
    status: 'PENDING',
    target: 'Inventory forecast accuracy >90%',
    gaps: ['G-06: post-actuals not yet available (first forecast cycle not complete)'],
  },
  {
    name: 'Forecast Bias',
    formula: 'BIAS = avg((Forecast − Actual) ÷ Actual) × 100%',
    detail: 'Positive = over-forecast · Negative = under-forecast. Computed per material.',
    source: 'ContextFlow MCP post-actuals',
    status: 'PENDING',
    target: 'Bias close to 0%',
    gaps: ['G-06: post-actuals not yet available'],
  },
]

const DATA_SOURCES = [
  { name: 'Consumption History', fields: 'MBLNR, ZEILE, BUDAT, MATNR, WERKS, LGORT, BWART, MENGE, DMBTR', origin: 'SAP MSEG / GCS', refresh: 'Daily (T-1 by 06:00 IST)', scope: 'BWART IN (201,261,551,601)' },
  { name: 'Stock / Material Master', fields: 'MATNR, WERKS, LABST, VERPR, STPRS, MATKL, MTART, CRITICAL_FLAG, PLIFZ, WEBAZ', origin: 'SAP MARA/MARC/MARD/MBEW / GCS', refresh: 'Daily', scope: 'MTART IN (ZSPR, ZSPN)' },
  { name: 'PO / PR History', fields: 'EBELN, EBELP, MATNR, WERKS, BEDAT, MENGE, NETPR, BUDAT_GR, MENGE_GR', origin: 'SAP EKKO/EKPO/EKET/EKBE / GCS', refresh: 'Daily', scope: 'All POs for ZSPR/ZSPN' },
  { name: 'Shutdown / Maintenance Calendar', fields: 'AUFNR, AUART, WERKS, GSTRP, GLTRP, ISTAT, SHUTDOWN_FLAG, RESB_MATNR', origin: 'SAP IFLOT/VIAUFKST / GCS', refresh: 'On change', scope: 'PM01/PM02/PM03 orders' },
  { name: 'ContextFlow MCP Forecast', fields: 'forecast_qty (3/6/12mo), avg/max daily usage, avg/max lead time, lower/upper bounds', origin: 'ContextFlow MCP endpoint', refresh: 'Weekly / on demand', scope: 'All ZSPR/ZSPN' },
]

const SCOPE_RULES = [
  'Material types: ZSPR (Spare Parts) and ZSPN (Non-Stock Spare Parts) only. All other types excluded.',
  'Consumption movements: BWART IN (201, 261, 551, 601) — configurable via CONSUMPTION_BWART_LIST env var.',
  'Inventory reduction baseline: lowest inventory value of the past financial year (not last month or plan).',
  'NMI window: 6 months (configurable via NMI_LOOKBACK_MONTHS). SMI threshold: 20th percentile (configurable).',
  'Overstock margin: 1.25× (configurable via OVERSTOCK_MARGIN_FACTOR).',
  'Price cascade: MBEW.VERPR → MBEW.STPRS → MBEW.LAEPR → 0 with price_missing flag.',
  'Drill-down dimensions: material code, plant, SM/NM flag, shutdown material, category.',
  'Forecast accuracy measured on held-out periods only — never on training data.',
  'Customer-side inventory reductions are excluded from incentive reporting.',
]

export default function DataMethodology() {
  const gaps = useDataGaps()

  const handlePDF = () => {
    exportPDF(FORMULAS, [
      { key: 'name', label: 'Metric' },
      { key: 'formula', label: 'Formula' },
      { key: 'source', label: 'Data Source' },
      { key: 'target', label: 'Target' },
      { key: 'status', label: 'Status' },
    ], 'vedanta_data_methodology', 'Data & Methodology')
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="section-title">Data &amp; Methodology</h1>
          <p className="section-sub">Formulas, data sources, refresh schedule, scope rules, and open blockers</p>
        </div>
        <button onClick={handlePDF} className="btn-primary">↓ PDF Report</button>
      </div>

      {/* Material Scope */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">Material Scope &amp; Rules</h2>
        <div className="bg-vedanta-navy border border-vedanta-blue rounded-xl p-5 space-y-2">
          {SCOPE_RULES.map((r, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-gray-300">
              <span className="text-vedanta-accent shrink-0 mt-0.5">▸</span>
              <span>{r}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Orchestration split */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">Orchestration Split</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-vedanta-navy border border-vedanta-blue rounded-xl p-5">
            <div className="text-xs uppercase tracking-wider text-vedanta-accent mb-2">ContextFlow via MCP</div>
            <p className="text-sm text-gray-300">Demand forecasting ONLY: Material Requirement Forecast (3/6/12 months) and derived metrics: Safety Stock, ROP, Overstock/Understock flags.</p>
          </div>
          <div className="bg-vedanta-navy border border-vedanta-blue rounded-xl p-5">
            <div className="text-xs uppercase tracking-wider text-vedanta-gold mb-2">This Team (Data Enablement Squad)</div>
            <p className="text-sm text-gray-300">Data ingestion layer, all real-data metrics (DOI, Inventory Value, Turnover, NMI, SMI, Fill Rate, Critical Availability), dashboard UI, Docker packaging, GCS/SAP connectors, export, gap tracking.</p>
          </div>
        </div>
      </section>

      {/* Metric Formulas */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">Metric Formulas (14 KPIs)</h2>
        <div className="overflow-x-auto rounded-lg border border-vedanta-blue/40">
          <table className="data-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Formula</th>
                <th>Detail</th>
                <th>Data Source</th>
                <th>Target</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {FORMULAS.map(f => (
                <tr key={f.name}>
                  <td className="font-medium text-white whitespace-nowrap">{f.name}</td>
                  <td className="font-mono text-xs text-gray-300 max-w-xs">{f.formula}</td>
                  <td className="text-gray-500 text-xs max-w-xs">{f.detail}</td>
                  <td className="text-gray-400 text-xs whitespace-nowrap">{f.source}</td>
                  <td className="text-gray-400 text-xs max-w-xs">{f.target}</td>
                  <td className="whitespace-nowrap">
                    {f.status === 'Real data'
                      ? <span className="badge-green">Real data</span>
                      : f.status === 'BLOCKED'
                      ? <span className="badge-red">BLOCKED</span>
                      : <span className="badge-amber">PENDING</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Data Sources */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">Data Sources &amp; Refresh Schedule</h2>
        <div className="overflow-x-auto rounded-lg border border-vedanta-blue/40">
          <table className="data-table">
            <thead>
              <tr><th>Source</th><th>Key Fields</th><th>Origin</th><th>Refresh</th><th>Scope Filter</th></tr>
            </thead>
            <tbody>
              {DATA_SOURCES.map(s => (
                <tr key={s.name}>
                  <td className="font-medium text-white whitespace-nowrap">{s.name}</td>
                  <td className="text-xs text-gray-400 font-mono max-w-xs">{s.fields}</td>
                  <td className="text-gray-400 text-xs whitespace-nowrap">{s.origin}</td>
                  <td><span className="badge-gray">{s.refresh}</span></td>
                  <td className="text-gray-500 text-xs">{s.scope}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Gap Register */}
      <section>
        <h2 className="text-sm font-semibold text-gray-300 mb-3 uppercase tracking-wider">
          Open Blockers / Gap Register v2.0.0
        </h2>
        {gaps ? (
          <div className="space-y-2">
            {gaps.gaps.map(g => (
              <div
                key={g.id}
                className={`rounded-lg px-4 py-3 border text-sm flex items-start gap-3 ${
                  g.status === 'BLOCKED'
                    ? 'bg-red-900/20 border-red-700/40 text-red-300'
                    : 'bg-amber-900/20 border-amber-700/40 text-amber-300'
                }`}
              >
                <span className="font-mono text-xs mt-0.5 shrink-0 font-bold">{g.id}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{g.description}</div>
                  <div className="text-xs opacity-70 mt-0.5">Affects: {g.affects.join(', ')}</div>
                </div>
                <span className={`ml-auto shrink-0 text-xs font-medium px-2 py-0.5 rounded ${
                  g.status === 'BLOCKED' ? 'bg-red-900/60 text-red-300' : 'bg-amber-900/60 text-amber-300'
                }`}>
                  {g.status}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-gray-500 text-sm">Loading gap register…</div>
        )}
        <div className="mt-3 text-xs text-gray-600">
          Gap register version: 2.0.0 · Source: vedanta-dashboard/contracts/gap_register_v2.json ·
          No wrong number is shown when data is missing — all blocked metrics render 'Data not available'.
        </div>
      </section>
    </div>
  )
}
