import React, { useMemo } from 'react'
import DataTable from '../components/DataTable'
import { useInventoryMetricsWithForecast } from '../hooks/useApi'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts'

const DNA = <span className="dna">Data not available</span>

function ActionBadge({ action }) {
  if (!action) return DNA
  if (action.startsWith('Reduce') || action.startsWith('REDUCE') || action.startsWith('DISPOSE'))
    return <span className="badge-amber">{action}</span>
  if (action.startsWith('Raise') || action.startsWith('REPLENISH') || action.startsWith('ORDER'))
    return <span className="badge-red">{action}</span>
  if (action.startsWith('Monitor') || action.startsWith('MONITOR'))
    return <span className="badge-gray">{action}</span>
  if (action.startsWith('REVIEW'))
    return <span className="badge-amber">{action}</span>
  return <span className="badge-green">{action}</span>
}

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
  { key: 'category', label: 'Category' },
  {
    key: 'inventory_value', label: 'Stock Value (₹)',
    render: v => v != null
      ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
      : DNA,
  },
  {
    key: 'days_of_inventory', label: 'DOH (days)',
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
    key: 'safety_stock', label: 'Safety Stock',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
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
  {
    key: 'recommended_action', label: 'Recommended Action',
    render: (v, row) => {
      const action = v || deriveAction(row)
      return <ActionBadge action={action} />
    },
  },
  {
    key: 'shutdown_flag', label: 'Shutdown Material',
    render: v => v ? <span className="badge-amber">Yes</span> : <span className="badge-gray">No</span>,
  },
]

/** Derive a recommended action from available real-data metrics when
 *  ContextFlow forecast is not yet available. */
function deriveAction(row) {
  if (row.non_moving_flag === true && row.inventory_value > 0)
    return 'REVIEW FOR DISPOSAL — NMI'
  if (row.slow_moving_flag === true)
    return 'MONITOR — SMI'
  if (row.overstock_flag === true)
    return 'Reduce order / defer next PR'
  if (row.understock_flag === true)
    return 'Raise PR immediately'
  if (row.overstock_flag == null && row.understock_flag == null)
    return null  // ContextFlow not available
  return 'OK'
}

export default function StockActions() {
  const { data, loading, error, forecastGap } = useInventoryMetricsWithForecast()

  const actionSummary = useMemo(() => {
    const nmi = data.filter(d => d.non_moving_flag === true).length
    const smi = data.filter(d => d.slow_moving_flag === true).length
    const over = data.filter(d => d.overstock_flag === true).length
    const under = data.filter(d => d.understock_flag === true).length
    return [
      { name: 'NMI — Review Disposal', count: nmi, fill: '#E67E22' },
      { name: 'SMI — Monitor', count: smi, fill: '#F1C40F' },
      { name: 'Overstock — Reduce', count: over, fill: '#F39C12' },
      { name: 'Understock — Replenish', count: under, fill: '#E94560' },
    ]
  }, [data])

  const actionItems = useMemo(
    () => data.filter(d =>
      d.non_moving_flag === true ||
      d.slow_moving_flag === true ||
      d.overstock_flag === true ||
      d.understock_flag === true
    ),
    [data]
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Stock Actions</h1>
        <p className="section-sub">
          Understock / overstock / NMI / SMI items with ROP, safety stock, and recommended action ·{' '}
          <span className="text-gray-600 text-xs">
            ROP = (Avg Daily × LT) + SS · Overstock = Stock &gt; (3mo forecast + SS) × 1.25
          </span>
        </p>
      </div>

      {/* Single gap banner — only when ContextFlow is absent */}
      {forecastGap && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠️ <strong>G-05 — ContextFlow MCP not connected:</strong>{' '}
          Overstock/Understock flags and ROP/Safety Stock require ContextFlow.
          NMI and SMI actions are derived from real consumption data and are shown now.
          Set <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_MCP_ENDPOINT</code> and{' '}
          <code className="text-xs bg-black/30 px-1 rounded">CONTEXTFLOW_API_KEY</code> to enable.
        </div>
      )}

      {/* Action summary chart */}
      {!loading && (
        <div className="chart-container">
          <div className="chart-title">Action Items by Type</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={actionSummary} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
              <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
              <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                labelStyle={{ color: '#fff' }}
                formatter={(v) => [v, 'Materials']}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {actionSummary.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {forecastGap && (
            <div className="text-xs text-gray-600 mt-2">
              ⚠️ Overstock/Understock counts show 0 until ContextFlow MCP is connected (G-05)
            </div>
          )}
        </div>
      )}

      {error && <div className="text-amber-400 text-sm">{error}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading…</div>
      ) : (
        <>
          {/* Action items table (filtered to items needing action) */}
          <div>
            <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
              Items Requiring Action ({actionItems.length})
            </h2>
            <DataTable
              columns={columns}
              data={actionItems}
              exportName="vedanta_stock_actions_flagged"
              pageLabel="Stock Actions — Flagged Items"
            />
          </div>

          {/* Full table */}
          <div>
            <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-3">
              All Materials ({data.length})
            </h2>
            <DataTable
              columns={columns}
              data={data}
              exportName="vedanta_stock_actions_all"
              pageLabel="Stock Actions — All Materials"
            />
          </div>
        </>
      )}
    </div>
  )
}
