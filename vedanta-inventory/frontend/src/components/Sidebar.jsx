import React from 'react'
import { NavLink } from 'react-router-dom'

const nav = [
  { path: '/executive-summary',  label: 'Executive Summary',       icon: '📊' },
  { path: '/inventory-health',   label: 'Inventory Health',        icon: '🏥' },
  { path: '/demand-forecast',    label: 'Demand Forecast',         icon: '📈' },
  { path: '/stock-actions',      label: 'Stock Actions',           icon: '⚡' },
  { path: '/critical-spares',    label: 'Critical Spares',         icon: '🔴' },
  { path: '/slow-non-moving',    label: 'Slow & Non-Moving',       icon: '🐢' },
  { path: '/forecast-quality',   label: 'Forecast Quality',        icon: '🎯' },
  { path: '/data-methodology',   label: 'Data & Methodology',      icon: '📋' },
]

export default function Sidebar() {
  return (
    <aside className="w-64 bg-vedanta-navy border-r border-vedanta-blue flex flex-col shrink-0">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-vedanta-blue">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-vedanta-accent flex items-center justify-center font-bold text-white text-sm">V</div>
          <div>
            <div className="text-white font-semibold text-sm leading-tight">Vedanta</div>
            <div className="text-gray-400 text-xs">Inventory Intelligence</div>
          </div>
        </div>
      </div>

      {/* Material scope badge */}
      <div className="px-4 py-3 border-b border-vedanta-blue/50">
        <span className="text-xs text-gray-500 uppercase tracking-wider">Scope</span>
        <div className="flex gap-2 mt-1">
          <span className="badge-amber">ZSPR</span>
          <span className="badge-amber">ZSPN</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {nav.map(({ path, label, icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-vedanta-accent/20 text-vedanta-accent font-medium border border-vedanta-accent/30'
                  : 'text-gray-400 hover:bg-vedanta-blue/30 hover:text-white'
              }`
            }
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-vedanta-blue/50 text-xs text-gray-600">
        Data Enablement Squad · v1.0
      </div>
    </aside>
  )
}
