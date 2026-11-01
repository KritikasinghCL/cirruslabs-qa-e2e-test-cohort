import React, { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, Legend,
} from 'recharts'
import DataTable from '../components/DataTable'
import { useInventoryMetrics } from '../hooks/useApi'

const DNA = <span className="dna">Data not available</span>

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
  { key: 'category', label: 'Category' },
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
    key: 'days_of_inventory', label: 'DOH (days)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
  {
    key: 'last_movement_date', label: 'Last Movement',
    render: v => v ?? DNA,
  },
  {
    key: 'value_at_risk', label: 'Value at Risk (₹)',
    render: v => v != null
      ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
      : DNA,
  },
  {
    key: 'inventory_value', label: 'Total Stock Value (₹)',
    render: v => v != null
      ? `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
      : DNA,
  },
  {
    key: 'shutdown_flag', label: 'Shutdown',
    render: v => v ? <span className="badge-amber">Yes</span> : <span className="badge-gray">No</span>,
  },
]

export default function SlowNonMoving() {
  const { data, loading, error } = useInventoryMetrics()

  const nmiItems = useMemo(() => data.filter(d => d.non_moving_flag === true), [data])
  const smiItems = useMemo(() => data.filter(d => d.slow_moving_flag === true), [data])
  const flagged = useMemo(
    () => data.filter(d => d.non_moving_flag === true || d.slow_moving_flag === true),
    [data]
  )

  const totalValueAtRisk = useMemo(
    () => flagged.reduce((s, d) => s + (d.value_at_risk || d.inventory_value || 0), 0),
    [flagged]
  )

  const nmiValue = useMemo(
    () => nmiItems.reduce((s, d) => s + (d.inventory_value || 0), 0),
    [nmiItems]
  )
  const smiValue = useMemo(
    () => smiItems.reduce((s, d) => s + (d.inventory_value || 0), 0),
    [smiItems]
  )

  // Category breakdown for NMI/SMI
  const categoryBreakdown = useMemo(() => {
    const map = {}
    flagged.forEach(m => {
      if (!m.category) return
      if (!map[m.category]) map[m.category] = { nmi: 0, smi: 0 }
      if (m.non_moving_flag) map[m.category].nmi++
      if (m.slow_moving_flag) map[m.category].smi++
    })
    return Object.entries(map)
      .sort((a, b) => (b[1].nmi + b[1].smi) - (a[1].nmi + a[1].smi))
      .slice(0, 8)
      .map(([name, v]) => ({ name, ...v }))
  }, [flagged])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Slow &amp; Non-Moving Inventory</h1>
        <p className="section-sub">
          NMI and SMI flagged materials · last movement date · value at risk ·{' '}
          <span className="text-gray-600 text-xs">
            NMI = nil consumption ≥6 months · SMI = usage ≤ 20th percentile of population
          </span>
        </p>
      </div>

      {/* KPI strip */}
      {!loading && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="kpi-card">
            <div className="kpi-label">NMI Count</div>
            <div className="kpi-value text-red-400">{nmiItems.length}</div>
            <div className="kpi-sub">Target: reduce ≥10% / month</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">SMI Count</div>
            <div className="kpi-value text-amber-400">{smiItems.length}</div>
            <div className="kpi-sub">Target: reduce ≥20% / month</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">NMI Value at Risk</div>
            <div className="kpi-value text-orange-400 text-2xl">
              {nmiValue > 0
                ? `₹${nmiValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                : <span className="dna text-base">Data not available</span>}
            </div>
            <div className="kpi-sub">NMI stock × unit price</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">SMI Value at Risk</div>
            <div className="kpi-value text-yellow-400 text-2xl">
              {smiValue > 0
                ? `₹${smiValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                : <span className="dna text-base">Data not available</span>}
            </div>
            <div className="kpi-sub">SMI stock × unit price</div>
          </div>
        </div>
      )}

      {/* Charts */}
      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* NMI vs SMI by category */}
          <div className="chart-container">
            <div className="chart-title">NMI &amp; SMI by Category (Top 8)</div>
            {categoryBreakdown.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={categoryBreakdown}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 60, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                  <XAxis type="number" tick={{ fill: '#9CA3AF', fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 10 }} width={56} />
                  <Tooltip
                    contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                    labelStyle={{ color: '#fff' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#9CA3AF' }} />
                  <Bar dataKey="nmi" name="NMI" fill="#E94560" radius={[0, 4, 4, 0]} stackId="a" />
                  <Bar dataKey="smi" name="SMI" fill="#F39C12" radius={[0, 4, 4, 0]} stackId="a" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-600 text-sm italic">
                No NMI/SMI items in current filter
              </div>
            )}
          </div>

          {/* Value at risk summary */}
          <div className="chart-container">
            <div className="chart-title">Value at Risk Summary</div>
            <div className="space-y-4 pt-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">NMI Value at Risk</span>
                <span className="text-red-400 font-semibold">
                  {nmiValue > 0
                    ? `₹${nmiValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                    : 'Data not available'}
                </span>
              </div>
              <div className="w-full bg-vedanta-blue rounded-full h-2">
                <div
                  className="bg-red-500 h-2 rounded-full"
                  style={{ width: totalValueAtRisk > 0 ? `${(nmiValue / totalValueAtRisk) * 100}%` : '0%' }}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">SMI Value at Risk</span>
                <span className="text-amber-400 font-semibold">
                  {smiValue > 0
                    ? `₹${smiValue.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                    : 'Data not available'}
                </span>
              </div>
              <div className="w-full bg-vedanta-blue rounded-full h-2">
                <div
                  className="bg-amber-500 h-2 rounded-full"
                  style={{ width: totalValueAtRisk > 0 ? `${(smiValue / totalValueAtRisk) * 100}%` : '0%' }}
                />
              </div>
              <div className="border-t border-vedanta-blue pt-3 flex items-center justify-between">
                <span className="text-sm text-gray-300 font-medium">Total Value at Risk</span>
                <span className="text-orange-400 font-bold">
                  {totalValueAtRisk > 0
                    ? `₹${totalValueAtRisk.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                    : 'Data not available'}
                </span>
              </div>
              <div className="text-xs text-gray-600">
                Baseline: lowest inventory value in past FY · Target: reduce NMI ≥10%, SMI ≥20% per month
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
          data={flagged}
          exportName="vedanta_slow_nonmoving"
          pageLabel="Slow & Non-Moving"
        />
      )}
    </div>
  )
}
