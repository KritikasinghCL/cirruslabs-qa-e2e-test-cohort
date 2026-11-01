import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import GlobalFilters from './components/GlobalFilters'
import ExecutiveSummary from './pages/ExecutiveSummary'
import InventoryHealth from './pages/InventoryHealth'
import DemandForecast from './pages/DemandForecast'
import StockActions from './pages/StockActions'
import CriticalSpares from './pages/CriticalSpares'
import SlowNonMoving from './pages/SlowNonMoving'
import ForecastQuality from './pages/ForecastQuality'
import DataMethodology from './pages/DataMethodology'
import { Toaster } from 'react-hot-toast'

export const FilterContext = React.createContext({})

export default function App() {
  const [filters, setFilters] = useState({
    plant: '',
    materialType: '',
    category: '',
    dateFrom: '',
    dateTo: '',
  })

  return (
    <BrowserRouter>
      <FilterContext.Provider value={{ filters, setFilters }}>
        <div className="flex h-screen overflow-hidden bg-vedanta-dark">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-hidden">
            <GlobalFilters />
            <main className="flex-1 overflow-y-auto p-6">
              <Routes>
                <Route path="/" element={<Navigate to="/executive-summary" replace />} />
                <Route path="/executive-summary" element={<ExecutiveSummary />} />
                <Route path="/inventory-health" element={<InventoryHealth />} />
                <Route path="/demand-forecast" element={<DemandForecast />} />
                <Route path="/stock-actions" element={<StockActions />} />
                <Route path="/critical-spares" element={<CriticalSpares />} />
                <Route path="/slow-non-moving" element={<SlowNonMoving />} />
                <Route path="/forecast-quality" element={<ForecastQuality />} />
                <Route path="/data-methodology" element={<DataMethodology />} />
              </Routes>
            </main>
          </div>
        </div>
        <Toaster position="top-right" toastOptions={{ style: { background: '#16213E', color: '#fff' } }} />
      </FilterContext.Provider>
    </BrowserRouter>
  )
}
