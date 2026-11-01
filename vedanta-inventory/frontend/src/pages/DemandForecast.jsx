import React, { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts'
import DataTable from '../components/DataTable'
import { useInventoryMetricsWithForecast } from '../hooks/useApi'

const DNA = <span className="dna">Data not available</span>

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'category', label: 'Category' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
  {
    key: 'forecast_3mo', label: 'Forecast 3mo (qty)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'forecast_6mo', label: 'Forecast 6mo (qty)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'forecast_12mo', label: 'Forecast 12mo (qty)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'safety_stock', label: 'Safety Stock',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'reorder_point', label: 'ROP',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'days_of_inventory', label: 'Current DOH (days)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
]

export default function DemandForecast() {
  const { data, loading, error, forecastGap } = useInventoryMetricsWithForecast()

  // Aggregate forecast availability
  const forecastStats = useMemo(() => {
    const total = data.length
    const with3mo = data.filter(m => m.forecast_3mo != null).length
    const with6mo = data.filter(m => m.forecast_6mo != null).length
    const with12mo = data.filter(m => m.forecast_12mo != null).length
    const withSS = data.filter(m => m.safety_stock != null).length
    const withROP = data.filter(m => m.reorder_point != null).length
    return { total, with3mo, with6mo, with12mo, withSS, withROP }
  }, [data])

  // Horizon comparison chart (aggregate totals when available)
  const horizonChart = [
    { name: '3 months', forecast: forecastStats.with3mo > 0
        ? data.reduce((s, m) => s + (m.forecast_3mo || 0), 0) : null },
    { name: '6 months', forecast: forecastStats.with6mo > 0
        ? data.reduce((s, m) => s + (m.forecast_6mo || 0), 0) : null },
    { name: '12 months', forecast: forecastStats.with12mo > 0
        ? data.reduce((s, m) => s + (m.forecast_12mo || 0), 0) : null },
  ]

  const hasForecast = forecastStats.with3mo > 0

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Demand Forecast</h1>
        <p className="section-sub">
          3/6/12-month material requirement forecast via ContextFlow MCP ·{' '}
          <span className="text-gray-600 text-xs">
            Safety Stock = Z × σ(daily cons 90d) × √(Lead Time days) · ROP = (Avg Daily × LT) + SS
          </span>
        </p>
      </div>

      {/* Single gap banner — only shown when ContextFlow is not connected */}
      {forecastGap && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠️ <strong>G-05 — ContextFlow MCP not connected:</strong>{' '}
          Set <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_MCP_ENDPOINT</code> and{' '}
          <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_API_KEY</code> environment
          variables to enable demand forecasting. Forecast quantities, Safety Stock, ROP, Overstock
          and Understock flags will populate automatically once connected.
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        <div className="kpi-card">
          <div className="kpi-label">Materials in Scope</div>
          <div className="kpi-value">{forecastStats.total}</div>
          <div className="kpi-sub">ZSPR + ZSPN</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">With 3mo Forecast</div>
          <div className="kpi-value">
            {hasForecast
              ? forecastStats.with3mo
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">{hasForecast ? 'ContextFlow' : 'G-05 pending'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">With Safety Stock</div>
          <div className="kpi-value">
            {forecastStats.withSS > 0
              ? forecastStats.withSS
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">{forecastStats.withSS > 0 ? 'Z×σ×√LT' : 'Requires ContextFlow'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">With ROP</div>
          <div className="kpi-value">
            {forecastStats.withROP > 0
              ? forecastStats.withROP
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">{forecastStats.withROP > 0 ? 'Avg×LT+SS' : 'Requires ContextFlow'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">With 12mo Forecast</div>
          <div className="kpi-value">
            {forecastStats.with12mo > 0
              ? forecastStats.with12mo
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">{forecastStats.with12mo > 0 ? 'ContextFlow' : 'G-05 pending'}</div>
        </div>
      </div>

      {/* Chart */}
      <div className="chart-container">
        <div className="chart-title">Aggregate Forecast Demand by Horizon</div>
        {hasForecast ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={horizonChart} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
              <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
              <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                labelStyle={{ color: '#fff' }}
                formatter={(v) => [v != null ? v.toLocaleString('en-IN') : 'N/A', 'Forecast Qty']}
              />
              <Bar dataKey="forecast" fill="#E94560" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-48 flex items-center justify-center text-gray-600 text-sm italic">
            Chart will populate once ContextFlow MCP is connected (G-05)
          </div>
        )}
        <div className="text-xs text-gray-600 mt-2">
          Source: ContextFlow MCP · Horizons: 3, 6, 12 months · Demand Quantity Prediction target: 100%
        </div>
      </div>

      {error && <div className="text-amber-400 text-sm">{error}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading…</div>
      ) : (
        <DataTable
          columns={columns}
          data={data}
          exportName="vedanta_demand_forecast"
          pageLabel="Demand Forecast"
        />
      )}
    </div>
  )
}
