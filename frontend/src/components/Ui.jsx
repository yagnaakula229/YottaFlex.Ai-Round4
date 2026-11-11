export function LoadingState({ label = 'Loading live data…' }) {
  return <div className="state-card"><span className="spinner" /><span>{label}</span></div>
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="state-card error-state" role="alert">
      <span className="state-icon">!</span>
      <div><strong>Unable to load data</strong><p>{error}</p></div>
      {onRetry && <button className="button button-secondary" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function EmptyState({ title = 'No records found', description = 'Try changing your filters.' }) {
  return <div className="empty-state"><span className="empty-symbol">⌕</span><strong>{title}</strong><p>{description}</p></div>
}

export function MetricCard({ label, value, detail, icon, tone = 'blue' }) {
  return (
    <article className="metric-card">
      <div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}>{icon}</span></div>
      <strong className="metric-value">{value ?? '—'}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  )
}

export function PriorityBadge({ value }) {
  return <span className={`badge priority-${String(value || '').toLowerCase()}`}>{value || 'Unrated'}</span>
}

export function StatusBadge({ value }) {
  return <span className={`badge status-${String(value || '').toLowerCase()}`}>{(value || 'unknown').replaceAll('_', ' ')}</span>
}

export function Pagination({ offset, limit, total, onChange }) {
  const start = total === 0 ? 0 : offset + 1
  const end = Math.min(offset + limit, total)
  return (
    <div className="pagination">
      <span>{start}–{end} of {total}</span>
      <div>
        <button className="button button-secondary" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
        <button className="button button-secondary" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </div>
  )
}

export function Distribution({ title, data, colors = {} }) {
  const entries = Object.entries(data || {})
  const maximum = Math.max(1, ...entries.map(([, value]) => value))
  return (
    <section className="panel distribution-panel">
      <div className="panel-heading"><div><p className="eyebrow">Portfolio signals</p><h2>{title}</h2></div></div>
      {entries.map(([label, value]) => (
        <div className="distribution-row" key={label}>
          <div className="distribution-meta"><span><i className="legend-dot" style={{ backgroundColor: colors[label] || '#8290a4' }} />{label.replaceAll('_', ' ')}</span><strong>{value}</strong></div>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(value ? 4 : 0, (value / maximum) * 100)}%`, backgroundColor: colors[label] || '#8290a4' }} /></div>
        </div>
      ))}
      {!entries.length && <p className="muted">No distribution data is available.</p>}
    </section>
  )
}
