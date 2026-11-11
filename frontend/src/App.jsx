import { useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import Transactions from './pages/Transactions.jsx'
import Alerts from './pages/Alerts.jsx'
import Cases from './pages/Cases.jsx'
import './App.css'

const navigation = [
  { id: 'dashboard', label: 'Overview', icon: '◫' },
  { id: 'transactions', label: 'Transactions', icon: '↔' },
  { id: 'alerts', label: 'Alerts', icon: '⌁' },
  { id: 'cases', label: 'Cases', icon: '▤' },
]

const pageTitles = {
  dashboard: ['Risk operations', 'Analyst overview'],
  transactions: ['Investigation', 'Transactions'],
  alerts: ['Risk signals', 'Alerts'],
  cases: ['Analyst workspace', 'Cases'],
}

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [refreshKey, setRefreshKey] = useState(0)
  const [lastUpdated, setLastUpdated] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = (message = '') => {
    setNotice(message)
    setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
    setRefreshKey((key) => key + 1)
  }

  const [eyebrow, title] = pageTitles[activePage]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setActivePage('dashboard') }}>
          <span className="brand-mark">R</span>
          <span>
            <strong>RiskTrace</strong>
            <small>INTELLIGENCE</small>
          </span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <button
              className={`nav-item ${activePage === item.id ? 'active' : ''}`}
              key={item.id}
              onClick={() => { setActivePage(item.id); setNotice('') }}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span>{item.label}</span>
              {item.id === 'alerts' && <span className="nav-live-dot" aria-label="Live data" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-card">
            <span className="connection-indicator" />
            <div><strong>API connection</strong><small>Live backend data</small></div>
          </div>
          <div className="analyst-profile">
            <span className="avatar">SA</span>
            <span><strong>Risk analyst</strong><small>Workspace session</small></span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>RiskTrace AI</span><span className="crumb-slash">/</span><strong>{title}</strong></div>
          <div className="topbar-actions">
            <span className="updated-label">{lastUpdated ? `Updated ${lastUpdated}` : 'Live data'}</span>
            <button className="icon-button" type="button" aria-label="Refresh current page" title="Refresh" onClick={() => refresh()}>
              ↻
            </button>
            <span className="avatar top-avatar">RA</span>
          </div>
        </header>
        <div className="content-area">
          <div className="page-heading">
            <div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>
            <div className="api-status"><span className="connection-indicator" />Connected to operational API</div>
          </div>
          {notice && <div className="notice-banner" role="status">{notice}</div>}
          {activePage === 'dashboard' && <Dashboard refreshKey={refreshKey} onNavigate={setActivePage} />}
          {activePage === 'transactions' && <Transactions refreshKey={refreshKey} onRefresh={refresh} />}
          {activePage === 'alerts' && <Alerts refreshKey={refreshKey} />}
          {activePage === 'cases' && <Cases refreshKey={refreshKey} onRefresh={refresh} />}
        </div>
        <footer className="app-footer">
          <span>RiskTrace AI <span className="footer-divider">·</span> Explainable transaction monitoring</span>
          <span>Operational data only <span className="footer-divider">·</span> Ground truth isolated</span>
        </footer>
      </main>
    </div>
  )
}

export default App
