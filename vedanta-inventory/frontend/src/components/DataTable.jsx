import React, { useState, useMemo } from 'react'
import { exportCSV, exportExcel, exportPDF } from '../utils/export'

export default function DataTable({ columns, data, exportName = 'vedanta_export', pageLabel = '' }) {
  const [search, setSearch] = useState('')
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState('asc')
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 20

  const filtered = useMemo(() => {
    if (!search) return data
    const q = search.toLowerCase()
    return data.filter(row =>
      columns.some(col => String(row[col.key] ?? '').toLowerCase().includes(q))
    )
  }, [data, search, columns])

  const sorted = useMemo(() => {
    if (!sortCol) return filtered
    return [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? ''
      const bv = b[sortCol] ?? ''
      const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortCol, sortDir])

  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)

  const handleSort = (key) => {
    if (sortCol === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(key); setSortDir('asc') }
  }

  return (
    <div className="space-y-3">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={search} onChange={e => { setSearch(e.target.value); setPage(0) }}
          placeholder="Search…"
          className="bg-vedanta-blue text-gray-200 text-sm rounded px-3 py-1.5 border border-vedanta-blue/60 focus:outline-none focus:ring-1 focus:ring-vedanta-accent w-64"
        />
        <span className="text-xs text-gray-500 ml-auto">{sorted.length} rows</span>
        <button onClick={() => exportCSV(sorted, columns, exportName)} className="btn-secondary text-xs">↓ CSV</button>
        <button onClick={() => exportExcel(sorted, columns, exportName)} className="btn-secondary text-xs">↓ Excel</button>
        <button onClick={() => exportPDF(sorted, columns, exportName, pageLabel)} className="btn-primary text-xs">↓ PDF Report</button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-vedanta-blue/40">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col.key} onClick={() => handleSort(col.key)} className="whitespace-nowrap">
                  {col.label}
                  {sortCol === col.key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 ? (
              <tr><td colSpan={columns.length} className="text-center py-8 dna">No data available</td></tr>
            ) : paged.map((row, i) => (
              <tr key={i}>
                {columns.map(col => (
                  <td key={col.key} className="whitespace-nowrap">
                    {col.render ? col.render(row[col.key], row) : (row[col.key] ?? <span className="dna">Data not available</span>)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="px-2 py-1 rounded bg-vedanta-blue disabled:opacity-30">←</button>
          <span>Page {page + 1} of {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} className="px-2 py-1 rounded bg-vedanta-blue disabled:opacity-30">→</button>
        </div>
      )}
    </div>
  )
}
