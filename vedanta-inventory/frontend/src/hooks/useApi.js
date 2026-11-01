import { useContext, useEffect, useState, useMemo } from 'react'
import { FilterContext } from '../App'
import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE || ''

// ─── Core data hooks ──────────────────────────────────────────────────────────

export function useInventoryMetrics() {
  const { filters } = useContext(FilterContext)
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (filters.plant) params.plant = filters.plant
    if (filters.materialType) params.material_type = filters.materialType
    if (filters.category) params.category = filters.category
    if (filters.dateFrom) params.date_from = filters.dateFrom
    if (filters.dateTo) params.date_to = filters.dateTo

    axios.get(`${BASE}/api/v1/inventory/metrics`, { params })
      .then(r => { setData(r.data); setError(null) })
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false))
  }, [filters.plant, filters.materialType, filters.category, filters.dateFrom, filters.dateTo])

  return { data, loading, error }
}

/**
 * Like useInventoryMetrics but calls the /with-forecast endpoint.
 * When ContextFlow is connected: forecast_3mo/6mo/12mo, safety_stock, rop,
 * overstock_flag, understock_flag are populated from real MCP data.
 * When ContextFlow is NOT connected: those fields are null and each material's
 * data_gaps list contains a single G-05 entry.
 */
export function useInventoryMetricsWithForecast() {
  const { filters } = useContext(FilterContext)
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [forecastGap, setForecastGap] = useState(null)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (filters.plant) params.plant = filters.plant
    if (filters.materialType) params.material_type = filters.materialType
    if (filters.category) params.category = filters.category
    if (filters.dateFrom) params.date_from = filters.dateFrom
    if (filters.dateTo) params.date_to = filters.dateTo

    axios.get(`${BASE}/api/v1/inventory/metrics/with-forecast`, { params })
      .then(r => {
        setData(r.data)
        setError(null)
        // Surface the G-05 gap if present (same message on every material when MCP is absent)
        const firstGap = r.data[0]?.data_gaps?.find(g => g.includes('G-05'))
        setForecastGap(firstGap || null)
      })
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false))
  }, [filters.plant, filters.materialType, filters.category, filters.dateFrom, filters.dateTo])

  return { data, loading, error, forecastGap }
}

export function useInventorySummary() {
  const { filters } = useContext(FilterContext)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    const params = {}
    if (filters.plant) params.plant = filters.plant
    if (filters.materialType) params.material_type = filters.materialType
    if (filters.dateFrom) params.date_from = filters.dateFrom
    if (filters.dateTo) params.date_to = filters.dateTo

    axios.get(`${BASE}/api/v1/inventory/summary/with-forecast`, { params })
      .then(r => { setData(r.data); setError(null) })
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false))
  }, [filters.plant, filters.materialType, filters.dateFrom, filters.dateTo])

  return { data, loading, error }
}

export function useDataGaps() {
  const [data, setData] = useState(null)
  useEffect(() => {
    axios.get(`${BASE}/api/v1/metrics/gaps`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
  }, [])
  return data
}

// ─── Derived filter options from live data ────────────────────────────────────

/**
 * Returns unique plant codes and categories from the full (unfiltered) metrics
 * so the filter dropdowns are always populated from real data.
 */
export function useFilterOptions() {
  const [plants, setPlants] = useState([])
  const [categories, setCategories] = useState([])

  useEffect(() => {
    axios.get(`${BASE}/api/v1/inventory/metrics`)
      .then(r => {
        const rows = r.data
        setPlants([...new Set(rows.map(r => r.plant).filter(Boolean))].sort())
        setCategories([...new Set(rows.map(r => r.category).filter(Boolean))].sort())
      })
      .catch(() => {
        // Fallback to empty — filters still work, just no dynamic options
      })
  }, [])

  return { plants, categories }
}
