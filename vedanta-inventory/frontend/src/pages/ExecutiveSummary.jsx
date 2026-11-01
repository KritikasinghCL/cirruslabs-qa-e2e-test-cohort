import React from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, Legend, CartesianGrid,
} from 'recharts'
import { useInventorySummary, useInventoryMetrics } from '../hooks/useApi'
import { exportPDF } from '../utils/export'

// ─── Sub-components ───────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, accent, target, definition }) {
  return (
    <div className="kpi-card group relative">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${accent || ''}`}>
        {value != null ? value : <span className="dna text-base">Data not available</span>}
      </div>
      {target && <div className="text-xs text-gray-500 mt-1">Target: {target}</div>}
      {sub && <div className="kpi-sub">{sub}</div>}
      {definition && (
        <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-10
                        bg-gray-900 border border-gray-700 rounded px-3 py-2 text-xs text-gray-300
                        max-w-xs shadow-xl">
          {definition}
        </div>
      )}
    </div>
  )
}

function BlockerBanner({ message }) {
  return (
    <div className="bg-amber-900/30 border border-amber-700/50 rounded-lg px-4 py-3 text-amber-300 text-sm flex items-start gap-2">
      <span>⚠️</span>
      <span>{message}</span>
    </div>
  )
}

const CHART_COLORS = {
  overstock: '#F39C12',
  understock: '#E94560',
  nmi: '#E67E22',
  smi: '#F1C40F',
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ExecutiveSummary() {
  const { data: summary, loading: sumLoading, error: sumError } = useInventorySummary()
  const { data: metrics, loading: metricsLoading } = useInventoryMetrics()

  // Action signals bar chart data
  const actionChartData = [
    { name: 'Overstock', count: summary?.overstock_count ?? 0, fill: CHART_COLORS.overstock },
    { name: 'Understock', count: summary?.understock_count ?? 0, fill: CHART_COLORS.understock },
    { name: 'Non-Moving', count: summary?.nmi_count ?? 0, fill: CHART_COLORS.nmi },
    { name: 'Slow-Moving', count: summary?.smi_count ?? 0, fill: CHART_COLORS.smi },
  ]

  // DOH distribution buckets
  const dohBuckets = React.useMemo(() => {
    if (!metrics.length) return []
    const buckets = { '<30d': 0, '30–90d': 0, '90–180d': 0, '>180d': 0, 'N/A': 0 }
    metrics.forEach(m => {
      if (m.days_of_inventory == null) { buckets['N/A']++; return }
      if (m.days_of_inventory < 30) buckets['<30d']++
      else if (m.days_of_inventory < 90) buckets['30–90d']++
      else if (m.days_of_inventory < 180) buckets['90–180d']++
      else buckets['>180d']++
    })
    return Object.entries(buckets).map(([name, count]) => ({ name, count }))
  }, [metrics])

  const handlePDF = () => {
    exportPDF(
      summary ? [summary] : [],
      [
        { key: 'forecast_accuracy_pct', label: 'Forecast Accuracy %' },
        { key: 'avg_days_of_inventory', label: 'Avg DOH (days)' },
        { key: 'total_inventory_value', label: 'Inventory Value (INR)' },
        { key: 'overstock_count', label: 'Overstock' },
        { key: 'understock_count', label: 'Understock' },
        { key: 'nmi_count', label: 'NMI Count' },
        { key: 'smi_count', label: 'SMI Count' },
        { key: 'total_materials', label: 'Total Materials' },
      ],
      'vedanta_executive_summary',
      'Executive Summary'
    )
  }

  const loading = sumLoading || metricsLoading

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="section-title">Executive Summary</h1>
          <p className="section-sub">
            Portfolio-level KPIs · ZSPR &amp; ZSPN materials only ·{' '}
            <span className="text-gray-600 text-xs">
              Hover KPI cards for definitions
            </span>
          </p>
        </div>
        <button onClick={handlePDF} className="btn-primary">↓ PDF Report</button>
      </div>

      {sumError && (
        <BlockerBanner message={`Data source unavailable: ${sumError}`} />
      )}

      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading KPIs…</div>
      ) : (
        <>
          {/* ── KPI Row 1: Forecast Performance ── */}
          <section>
            <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
              Forecast Performance
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <KpiCard
                label="Forecast Accuracy %"
                value={summary?.forecast_accuracy_pct != null
                  ? `${summary.forecast_accuracy_pct}%` : null}
                target=">90%"
                sub="100% − MAPE · Post-actuals only"
                accent="text-vedanta-gold"
                definition="Forecast Accuracy = 100% − MAPE, where MAPE = avg(|Actual−Forecast|÷Actual)×100%. Computed on held-out periods only. Source: ContextFlow MCP post-actuals."
              />
              <KpiCard
                label="Total Materials in Scope"
                value={summary?.total_materials}
                sub="ZSPR + ZSPN only"
                definition="Count of ZSPR (Spare Parts) and ZSPN (Non-Stock Spare Parts) material records in the current filter selection."
              />
              <KpiCard
                label="Open Data Gaps"
                value={summary?.data_gaps?.length ?? '—'}
                sub="Blockers — see Data & Methodology"
                accent="text-amber-400"
                definition="Count of metrics that cannot be computed due to missing data sources. See Data & Methodology page for the full gap register."
              />
            </div>
          </section>

          {/* ── KPI Row 2: Inventory Position ── */}
          <section>
            <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
              Inventory Position
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <KpiCard
                label="Avg Days of Inventory (DOH)"
                value={summary?.avg_days_of_inventory != null
                  ? `${summary.avg_days_of_inventory} days` : null}
                sub="Current stock ÷ avg daily usage (365d)"
                definition="DOH = Current Stock ÷ Average Daily Usage. Average Daily Usage = total consumption in last 365 days ÷ 365. Source: MARD.LABST + MSEG consumption records."
              />
              <KpiCard
                label="Total Inventory Value"
                value={summary?.total_inventory_value != null
                  ? `₹${Number(summary.total_inventory_value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                  : null}
                sub="Current stock × unit price (VERPR → STPRS → LAEPR)"
                definition="Inventory Value = SUM(MARD.LABST × MBEW.VERPR). Price cascade: VERPR → STPRS → LAEPR → 0 with 'Price missing' flag. Scope: ZSPR + ZSPN."
              />
              <KpiCard
                label="Inventory Turnover"
                value={null}
                sub="Requires live consumption data"
                definition="Inventory Turnover = Total Consumption Value ÷ Average Inventory Value. G-03: using point-in-time stock as proxy for average inventory until monthly snapshots are available."
              />
            </div>
          </section>

          {/* ── KPI Row 3: Action Signals ── */}
          <section>
            <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
              Action Signals
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <KpiCard
                label="Overstock Items"
                value={summary?.overstock_count != null ? summary.overstock_count : null}
                sub="Stock > (3mo forecast + SS) × 1.25"
                accent="text-amber-400"
                definition="Overstock Flag = Current Stock > (Forecast_3mo + Safety Stock) × 1.25. Requires ContextFlow MCP forecast. Currently blocked (G-05)."
              />
              <KpiCard
                label="Understock Items"
                value={summary?.understock_count != null ? summary.understock_count : null}
                sub="Stock < Reorder Point"
                accent="text-red-400"
                definition="Understock Flag = Current Stock < ROP. ROP = (Avg Daily Usage × Lead Time) + Safety Stock. Requires ContextFlow MCP forecast. Currently blocked (G-05)."
              />
              <KpiCard
                label="Non-Moving (NMI)"
                value={summary?.nmi_count != null ? summary.nmi_count : null}
                sub="Nil consumption ≥6 months · Target: reduce ≥10%"
                accent="text-orange-400"
                definition="NMI Flag = no consumption in last 6 months AND current stock > 0. Source: MSEG consumption records. Target: reduce NMI count by ≥10% per month."
              />
              <KpiCard
                label="Slow-Moving (SMI)"
                value={summary?.smi_count != null ? summary.smi_count : null}
                sub="Usage below 20th percentile · Target: reduce ≥20%"
                accent="text-yellow-400"
                definition="SMI Flag = avg daily usage ≤ 20th percentile of all materials' avg daily usage AND not NMI. Source: MSEG consumption records. Target: reduce SMI count by ≥20% per month."
              />
            </div>
          </section>

          {/* ── Charts Row ── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Action Signals Bar Chart */}
            <div className="chart-container">
              <div className="chart-title">Action Signals — Material Count</div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={actionChartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                  <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                    itemStyle={{ color: '#9CA3AF' }}
                    formatter={(v) => [v, 'Materials']}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {actionChartData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="text-xs text-gray-600 mt-2">
                ⚠️ Overstock/Understock counts show 0 until ContextFlow MCP is connected (G-05)
              </div>
            </div>

            {/* DOH Distribution */}
            <div className="chart-container">
              <div className="chart-title">Days of Inventory Distribution</div>
              {dohBuckets.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={dohBuckets} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                    <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                      labelStyle={{ color: '#fff' }}
                      itemStyle={{ color: '#9CA3AF' }}
                      formatter={(v) => [v, 'Materials']}
                    />
                    <Bar dataKey="count" fill="#E94560" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-600 text-sm italic">
                  Loading distribution…
                </div>
              )}
              <div className="text-xs text-gray-600 mt-2">
                DOH = Current Stock ÷ Avg Daily Usage (365-day lookback)
              </div>
            </div>
          </div>

          {/* Blocker notice */}
          <BlockerBanner message="Forecast-dependent KPIs (Overstock, Understock, Safety Stock, ROP) show 'Data not available' until ContextFlow MCP endpoint is configured (G-05). Fill Rate blocked pending RESB export (G-02). See Data & Methodology page for full gap register." />
        </>
      )}
    </div>
  )
}
