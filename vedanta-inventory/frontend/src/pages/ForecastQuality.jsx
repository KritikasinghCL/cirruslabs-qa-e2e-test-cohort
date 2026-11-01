import React, { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Cell,
} from 'recharts'
import DataTable from '../components/DataTable'
import { useInventoryMetrics } from '../hooks/useApi'

const DNA = <span className="dna">Data not available</span>

const columns = [
  { key: 'material_code', label: 'Material Code' },
  { key: 'plant', label: 'Plant' },
  { key: 'category', label: 'Category' },
  { key: 'material_type', label: 'Type', render: v => <span className="badge-amber">{v}</span> },
  {
    key: 'forecast_accuracy_pct', label: 'Forecast Accuracy %',
    render: v => {
      if (v == null) return DNA
      const n = Number(v)
      return (
        <span className={n >= 90 ? 'text-green-400 font-medium' : n >= 75 ? 'text-amber-400' : 'text-red-400'}>
          {n.toFixed(1)}%
        </span>
      )
    },
  },
  {
    key: 'forecast_bias_pct', label: 'Forecast Bias %',
    render: v => {
      if (v == null) return DNA
      const n = Number(v)
      return (
        <span className={Math.abs(n) < 5 ? 'text-green-400' : Math.abs(n) < 15 ? 'text-amber-400' : 'text-red-400'}>
          {n > 0 ? '+' : ''}{n.toFixed(2)}%
        </span>
      )
    },
  },
  {
    key: 'days_of_inventory', label: 'DOH (days)',
    render: v => v != null
      ? Number(v).toLocaleString('en-IN', { maximumFractionDigits: 1 })
      : DNA,
  },
]

export default function ForecastQuality() {
  const { data, loading, error } = useInventoryMetrics()

  const withAccuracy = useMemo(
    () => data.filter(m => m.forecast_accuracy_pct != null),
    [data]
  )
  const withBias = useMemo(
    () => data.filter(m => m.forecast_bias_pct != null),
    [data]
  )

  const avgAccuracy = useMemo(() => {
    if (!withAccuracy.length) return null
    return (withAccuracy.reduce((s, m) => s + m.forecast_accuracy_pct, 0) / withAccuracy.length).toFixed(1)
  }, [withAccuracy])

  const avgBias = useMemo(() => {
    if (!withBias.length) return null
    return (withBias.reduce((s, m) => s + m.forecast_bias_pct, 0) / withBias.length).toFixed(2)
  }, [withBias])

  // Accuracy distribution buckets
  const accuracyBuckets = useMemo(() => {
    if (!withAccuracy.length) return []
    const b = { '<75%': 0, '75–90%': 0, '≥90% (Target)': 0 }
    withAccuracy.forEach(m => {
      if (m.forecast_accuracy_pct >= 90) b['≥90% (Target)']++
      else if (m.forecast_accuracy_pct >= 75) b['75–90%']++
      else b['<75%']++
    })
    return Object.entries(b).map(([name, count]) => ({ name, count }))
  }, [withAccuracy])

  const BUCKET_COLORS = ['#E94560', '#F39C12', '#27AE60']

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title">Forecast Quality</h1>
        <p className="section-sub">
          Forecast Accuracy % and Forecast Bias per material/period · Post-actuals only ·{' '}
          <span className="text-gray-600 text-xs">
            Accuracy = 100% − MAPE · Bias = avg((F−A)÷A)×100% · Target: Accuracy &gt;90%
          </span>
        </p>
      </div>

      {/* Post-actuals notice */}
      <div className="bg-vedanta-navy border border-vedanta-blue rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="text-4xl shrink-0">🎯</div>
          <div>
            <div className="text-gray-200 font-medium mb-1">Post-Actuals Metric — G-06</div>
            <div className="text-gray-400 text-sm max-w-2xl">
              Forecast Accuracy % and Forecast Bias are computed only once actual consumption data
              is available for a period that was previously forecast by ContextFlow.
              This page will populate automatically once actuals are ingested for a completed forecast period.
            </div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-gray-500">
              <div className="bg-vedanta-blue/30 rounded px-3 py-2">
                <strong className="text-gray-300">Accuracy formula:</strong><br />
                100% − MAPE, where MAPE = avg(|Actual−Forecast| ÷ Actual) × 100%<br />
                Computed on held-out periods only. Population: all ZSPR/ZSPN with actuals.
              </div>
              <div className="bg-vedanta-blue/30 rounded px-3 py-2">
                <strong className="text-gray-300">Bias formula:</strong><br />
                avg((Forecast − Actual) ÷ Actual) × 100%<br />
                Positive = over-forecast · Negative = under-forecast
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="kpi-card">
          <div className="kpi-label">Avg Forecast Accuracy</div>
          <div className={`kpi-value ${avgAccuracy >= 90 ? 'text-green-400' : 'text-gray-500'}`}>
            {avgAccuracy != null ? `${avgAccuracy}%` : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">Target: &gt;90%</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Avg Forecast Bias</div>
          <div className="kpi-value">
            {avgBias != null
              ? <span className={Math.abs(avgBias) < 5 ? 'text-green-400' : 'text-amber-400'}>
                  {avgBias > 0 ? '+' : ''}{avgBias}%
                </span>
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">0% = unbiased</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Materials with Actuals</div>
          <div className="kpi-value">{withAccuracy.length}</div>
          <div className="kpi-sub">of {data.length} total</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Meeting Target (&gt;90%)</div>
          <div className="kpi-value text-green-400">
            {withAccuracy.length > 0
              ? withAccuracy.filter(m => m.forecast_accuracy_pct >= 90).length
              : <span className="dna text-base">Data not available</span>}
          </div>
          <div className="kpi-sub">Post-actuals only</div>
        </div>
      </div>

      {/* Charts */}
      {!loading && withAccuracy.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="chart-container">
            <div className="chart-title">Accuracy Distribution</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={accuracyBuckets} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  formatter={(v) => [v, 'Materials']}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {accuracyBuckets.map((entry, i) => (
                    <Cell key={i} fill={BUCKET_COLORS[i % BUCKET_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-container">
            <div className="chart-title">Accuracy per Material (Top 20)</div>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={withAccuracy.slice(0, 20).map(m => ({
                  name: m.material_code,
                  accuracy: m.forecast_accuracy_pct,
                }))}
                margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#0F3460" />
                <XAxis dataKey="name" tick={{ fill: '#9CA3AF', fontSize: 9 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#9CA3AF', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#16213E', border: '1px solid #0F3460', borderRadius: 8 }}
                  labelStyle={{ color: '#fff' }}
                  formatter={(v) => [`${v}%`, 'Accuracy']}
                />
                <ReferenceLine y={90} stroke="#27AE60" strokeDasharray="4 4" label={{ value: 'Target 90%', fill: '#27AE60', fontSize: 10 }} />
                <Bar dataKey="accuracy" radius={[4, 4, 0, 0]}>
                  {withAccuracy.slice(0, 20).map((m, i) => (
                    <Cell key={i} fill={m.forecast_accuracy_pct >= 90 ? '#27AE60' : m.forecast_accuracy_pct >= 75 ? '#F39C12' : '#E94560'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {error && <div className="text-amber-400 text-sm">{error}</div>}
      {loading ? (
        <div className="text-gray-500 text-sm animate-pulse">Loading…</div>
      ) : (
        <DataTable
          columns={columns}
          data={data}
          exportName="vedanta_forecast_quality"
          pageLabel="Forecast Quality"
        />
      )}
    </div>
  )
}
