import React, { useMemo } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import DataTable from '../components/DataTable'
import { useInventoryMetrics } from '../hooks/useApi'

const DNA = <span className="dna">Data not available</span>

function RagBadge({ pct }) {
  if (pct == null) return DNA
  if (pct >= 95) return <span className="badge-green">🟢 {pct}%</span>
  if (pct >= 80) return <span className="badge-amber">🟡 {pct}%</span>
  return <span className="badge-red">🔴 {pct}%</span>
}

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'category', label: 'Category' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
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
    key: 'critical_spares_availability_pct', label: 'Availability %',
    render: v => <RagBadge pct={v} />,
  },
  {
    key: 'shutdown_flag', label: 'Shutdown Material',
    render: v => v ? <span className="badge-amber">Yes</span> : <span className="badge-gray">No</span>,
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
    key: 'reorder_point', label: 'ROP',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
]

const PIE_COLORS = ['#27AE60', '#F39C12', '#E94560', '#6B7280']

export default function CriticalSpares() {
  const { data, loading, error } = useInventoryMetrics()

  const criticals = useMemo(() => data.filter(d => d.critical_flag), [data])
  const shutdownMaterials = useMemo(() => data.filter(d => d.shutdown_flag), [data])

  // Availability breakdown (when data is available)
  const availabilityBreakdown = useMemo(() => {
    const green = criticals.filter(d => d.critical_spares_availability_pct >= 95).length
    const amber = criticals.filter(d =>
      d.critical_spares_availability_pct != null &&
      d.critical_spares_availability_pct >= 80 &&
      d.critical_spares_availability_pct < 95
    ).length
    const red = criticals.filter(d =>
      d.critical_spares_availability_pct != null &&
      d.critical_spares_availability_pct < 80
    ).length
    const na = criticals.filter(d => d.critical_spares_availability_pct == null).length
    return [
      { name: '≥95% (Target)', value: green },
      { name: '80–95% (Warning)', value: amber },
      { name: '<80% (Critical)', value: red },
      { name: 'Data not available', value: na },
    ].filter(d => d.value > 0)
  }, [criticals])

  const totalCriticalValue = useMemo(
    () => criticals.reduce((s, m) => s + (m.inventory_value || 0), 0),
    [criticals]
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Critical Spares</h1>
        <p className="section-sub">
          RAG availability status for critical / insurance spares · Target: &gt;95% ·{' '}
          <span className="text-gray-600 text-xs">
            Availability = Days in Stock ÷ Total Days × 100% (requires daily snapshot — G-01)
          </span>
        </p>
      </div>

      {/* Gap banners */}
      <div className="space-y-2">
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠️ <strong>G-01:</strong> Critical Spares Availability % requires daily stock snapshot data.
          Shown as 'Data not available' until daily snapshot is confirmed in GCS export.
          Critical flag source (MARC.CRITICAL_FLAG or Z-field) also unconfirmed.
        </div>
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-3 text-amber-300 text-sm">
          ⚠️ <strong>G-04:</strong> Shutdown calendar not available — next shutdown date cannot be shown.
          Shutdown flag is derived from PM order type (PM03) as a fallback.
        </div>
      </div>

      {/* KPI strip */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="kpi-card">
            <div className="kpi-label">Critical Spares</div>
            <div className="kpi-value text-red-400">{criticals.length}</div>
            <div className="kpi-sub">CRITICAL_FLAG = true</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Shutdown Materials</div>
            <div className="kpi-value text-amber-400">{shutdownMaterials.length}</div>
            <div className="kpi-sub">Linked to PM orders</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Critical Stock Value</div>
            <div className="kpi-value text-vedanta-gold text-2xl">
              {totalCriticalValue > 0
                ? `₹${totalCriticalValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                : <span className="dna text-base">Data not available</span>}
            </div>
            <div className="kpi-sub">LABST × VERPR</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Portfolio Availability</div>
            <div className="kpi-value">
              <span className="dna text-base">Data not available</span>
            </div>
            <div className="kpi-sub">Daily snapshot pending (G-01)</div>
          </div>
        </div>
      )}

      {/* Charts */}
      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Availability RAG pie */}
          <div className="chart-container">
            <div className="chart-title">Availability RAG Status</div>
            {availabilityBreakdown.some(d => d.name !== 'Data not available' && d.value > 0) ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={availabilityBreakdown}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}`}
                    labelLine={false}
                  >
                    {availabilityBreakdown.map((entry, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                    formatter={(v, name) => [v, name]}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-48 flex flex-col items-center justify-center gap-3">
                <div className="text-gray-600 text-sm italic">
                  Availability data not available (G-01)
                </div>
                <div className="text-xs text-gray-700">
                  {criticals.length} critical materials identified · availability % blocked pending daily snapshot
                </div>
              </div>
            )}
          </div>

          {/* Shutdown calendar placeholder */}
          <div className="chart-container">
            <div className="chart-title">Shutdown Calendar</div>
            <div className="h-48 flex flex-col items-center justify-center gap-3">
              <div className="text-4xl">🔧</div>
              <div className="text-gray-500 text-sm text-center">
                Shutdown calendar not available (G-04)
              </div>
              <div className="text-xs text-gray-600 text-center max-w-xs">
                Next shutdown date will appear here once the maintenance calendar
                (VIAUFKST / PM order extract) is confirmed in the GCS export.
              </div>
            </div>
          </div>
        </div>
      )}

      {error && <div className="text-amber-400 text-sm">{error}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading…</div>
      ) : (
        <DataTable
          columns={columns}
          data={criticals}
          exportName="vedanta_critical_spares"
          pageLabel="Critical Spares"
        />
      )}
    </div>
  )
}
