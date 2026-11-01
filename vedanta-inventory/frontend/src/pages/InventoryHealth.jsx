import React, { useMemo } from 'react'
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, BarChart, Bar, Cell,
} from 'recharts'
import DataTable from '../components/DataTable'
import { useInventoryMetricsWithForecast } from '../hooks/useApi'

const fmt = (v, decimals = 2) =>
  v != null ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: decimals }) : null

const DNA = <span className="dna">Data not available</span>

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
  { key: 'category', label: 'Category' },
  {
    key: 'days_of_inventory', label: 'DOH (days)',
    render: v => v != null
      ? <span className={v > 180 ? 'text-amber-400' : v < 30 ? 'text-red-400' : 'text-green-400'}>
          {fmt(v, 1)}
        </span>
      : DNA,
  },
  {
    key: 'inventory_value', label: 'Inv. Value (₹)',
    render: v => v != null ? `₹${fmt(v, 0)}` : DNA,
  },
  {
    key: 'inventory_turnover', label: 'Turnover',
    render: v => v != null ? fmt(v, 3) : DNA,
  },
  {
    key: 'fill_rate_pct', label: 'Fill Rate %',
    render: v => v != null ? `${fmt(v, 1)}%` : DNA,
  },
  {
    key: 'non_moving_flag', label: 'NMI',
    render: v => v === true
      ? <span className="badge-red">NMI</span>
      : v === false
      ? <span className="badge-green">Active</span>
      : DNA,
  },
  {
    key: 'slow_moving_flag', label: 'SMI',
    render: v => v === true
      ? <span className="badge-amber">SMI</span>
      : v === false
      ? <span className="badge-green">OK</span>
      : DNA,
  },
  {
    key: 'overstock_flag', label: 'Overstock',
    render: v => v === true
      ? <span className="badge-amber">Overstock</span>
      : v === false
      ? <span className="badge-green">OK</span>
      : DNA,
  },
  {
    key: 'understock_flag', label: 'Understock',
    render: v => v === true
      ? <span className="badge-red">Understock</span>
      : v === false
      ? <span className="badge-green">OK</span>
      : DNA,
  },
]

// DOH colour by bucket
const DOH_COLORS = ['#27AE60', '#27AE60', '#F39C12', '#E94560', '#6B7280']

export default function InventoryHealth() {
  const { data, loading, error, forecastGap } = useInventoryMetricsWithForecast()

  // Summary KPIs from the data
  const totalValue = useMemo(
    () => data.reduce((s, m) => s + (m.inventory_value || 0), 0),
    [data]
  )
  const avgDoh = useMemo(() => {
    const vals = data.map(m => m.days_of_inventory).filter(v => v != null)
    return vals.length ? (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1) : null
  }, [data])

  // DOH distribution
  const dohBuckets = useMemo(() => {
    const b = { '<30d': 0, '30–90d': 0, '90–180d': 0, '>180d': 0, 'N/A': 0 }
    data.forEach(m => {
      if (m.days_of_inventory == null) { b['N/A']++; return }
      if (m.days_of_inventory < 30) b['<30d']++
      else if (m.days_of_inventory < 90) b['30–90d']++
      else if (m.days_of_inventory < 180) b['90–180d']++
      else b['>180d']++
    })
    return Object.entries(b).map(([name, count], i) => ({ name, count, fill: DOH_COLORS[i] }))
  }, [data])

  // Category breakdown by value
  const categoryBreakdown = useMemo(() => {
    const map = {}
    data.forEach(m => {
      if (!m.category) return
      map[m.category] = (map[m.category] || 0) + (m.inventory_value || 0)
    })
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([name, value]) => ({ name, value: Math.round(value) }))
  }, [data])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Inventory Health</h1>
        <p className="section-sub">
          DOH, Turnover, Fill Rate per material/plant · ZSPR &amp; ZSPN ·{' '}
          <span className="text-gray-600 text-xs">
            Formula: DOH = Current Stock ÷ Avg Daily Usage (365d) · Turnover = Consumption Value ÷ Avg Inventory Value
          </span>
        </p>
      </div>

      {error && (
        <div className="text-amber-400 text-sm bg-amber-900/20 rounded px-4 py-2">{error}</div>
      )}

      {/* Single gap banner — only when ContextFlow is absent */}
      {forecastGap && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠️ <strong>G-05 — ContextFlow MCP not connected:</strong>{' '}
          Overstock/Understock flags, Safety Stock, and ROP require ContextFlow.
          Set <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_MCP_ENDPOINT</code> and{' '}
          <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_API_KEY</code> to enable.
          NMI, SMI, DOH and Turnover are computed from real consumption data and shown now.
        </div>
      )}

      {/* Summary KPI strip */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="kpi-card">
            <div className="kpi-label">Total Materials</div>
            <div className="kpi-value">{data.length}</div>
            <div className="kpi-sub">In current filter</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Total Inventory Value</div>
            <div className="kpi-value text-vedanta-gold text-2xl">
              {totalValue > 0
                ? `₹${totalValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                : <span className="dna text-base">Data not available</span>}
            </div>
            <div className="kpi-sub">LABST × VERPR</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Avg DOH</div>
            <div className="kpi-value">
              {avgDoh != null ? `${avgDoh} days` : <span className="dna text-base">Data not available</span>}
            </div>
            <div className="kpi-sub">365-day lookback</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Fill Rate</div>
            <div className="kpi-value">
              <span className="dna text-base">Data not available</span>
            </div>
            <div className="kpi-sub">RESB export pending (G-02)</div>
          </div>
        </div>
      )}

      {/* Charts */}
      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* DOH Distribution */}
          <div className="chart-container">
            <div className="chart-title">DOH Distribution — Material Count</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={dohBuckets} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  formatter={(v) => [v, 'Materials']}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {dohBuckets.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Category Value Breakdown */}
          <div className="chart-container">
            <div className="chart-title">Inventory Value by Category (Top 8) — ₹</div>
            {categoryBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={categoryBreakdown}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 60, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                  <XAxis
                    type="number"
                    tick={{ fill: '#9CA3AF', fontSize: 10 }}
                    tickFormatter={v => `₹${(v / 1e5).toFixed(0)}L`}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fill: '#9CA3AF', fontSize: 10 }}
                    width={56}
                  />
                  <Tooltip
                    contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                    formatter={(v) => [`₹${v.toLocaleString('en-IN')}`, 'Value']}
                  />
                  <Bar dataKey="value" fill="#E94560" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-600 text-sm italic">
                No category data available
              </div>
            )}
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading…</div>
      ) : (
        <DataTable
          columns={columns}
          data={data}
          exportName="vedanta_inventory_health"
          pageLabel="Inventory Health"
        />
      )}
    </div>
  )
}
