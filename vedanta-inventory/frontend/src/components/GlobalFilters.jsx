import React, { useContext } from 'react'
import { FilterContext } from '../App'
import { useFilterOptions } from '../hooks/useApi'

const TYPES = ['ZSPR', 'ZSPN']

export default function GlobalFilters() {
  const { filters, setFilters } = useContext(FilterContext)
  const { plants, categories } = useFilterOptions()

  const set = (key) => (e) => setFilters(f => ({ ...f, [key]: e.target.value }))

  const hasFilters = filters.plant || filters.materialType || filters.category ||
    filters.dateFrom || filters.dateTo

  return (
    <div className="bg-vedanta-navy border-b border-vedanta-blue px-6 py-3 flex flex-wrap items-center gap-3">
      <span className="text-xs text-gray-500 uppercase tracking-wider shrink-0">Filters</span>

      {/* Plant */}
      <select
        value={filters.plant}
        onChange={set('plant')}
        className="filter-select"
        aria-label="Plant filter"
      >
        <option value="">All Plants</option>
        {plants.map(p => <option key={p} value={p}>{p}</option>)}
      </select>

      {/* Material Type */}
      <select
        value={filters.materialType}
        onChange={set('materialType')}
        className="filter-select"
        aria-label="Material type filter"
      >
        <option value="">All Types</option>
        {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
      </select>

      {/* Category */}
      <select
        value={filters.category}
        onChange={set('category')}
        className="filter-select"
        aria-label="Category filter"
      >
        <option value="">All Categories</option>
        {categories.map(c => <option key={c} value={c}>{c}</option>)}
      </select>

      {/* Period */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Period</span>
        <input
          type="date"
          value={filters.dateFrom}
          onChange={set('dateFrom')}
          className="filter-select"
          aria-label="Date from"
        />
        <span className="text-gray-600 text-xs">–</span>
        <input
          type="date"
          value={filters.dateTo}
          onChange={set('dateTo')}
          className="filter-select"
          aria-label="Date to"
        />
      </div>

      {hasFilters && (
        <button
          onClick={() => setFilters({ plant: '', materialType: '', category: '', dateFrom: '', dateTo: '' })}
          className="ml-auto text-xs text-gray-500 hover:text-gray-300 underline"
        >
          Clear all
        </button>
      )}

      {/* Active filter chips */}
      {hasFilters && (
        <div className="w-full flex flex-wrap gap-1 mt-1">
          {filters.plant && <Chip label={`Plant: ${filters.plant}`} onRemove={() => setFilters(f => ({ ...f, plant: '' }))} />}
          {filters.materialType && <Chip label={`Type: ${filters.materialType}`} onRemove={() => setFilters(f => ({ ...f, materialType: '' }))} />}
          {filters.category && <Chip label={`Category: ${filters.category}`} onRemove={() => setFilters(f => ({ ...f, category: '' }))} />}
          {filters.dateFrom && <Chip label={`From: ${filters.dateFrom}`} onRemove={() => setFilters(f => ({ ...f, dateFrom: '' }))} />}
          {filters.dateTo && <Chip label={`To: ${filters.dateTo}`} onRemove={() => setFilters(f => ({ ...f, dateTo: '' }))} />}
        </div>
      )}
    </div>
  )
}

function Chip({ label, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-vedanta-accent/20 text-vedanta-accent text-xs border border-vedanta-accent/30">
      {label}
      <button onClick={onRemove} className="hover:text-white ml-0.5">×</button>
    </span>
  )
}
