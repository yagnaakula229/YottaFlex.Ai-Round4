import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { EmptyState, ErrorState, LoadingState, Pagination, PriorityBadge, StatusBadge } from '../components/Ui.jsx'
import { formatDate } from '../services/format.js'

const pageSize = 25

function Alerts({ refreshKey }) {
  const [page, setPage] = useState({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [priority, setPriority] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = useCallback(async () => {
    try {
      setPage(await api.alerts({ limit: pageSize, offset, priority, status }))
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }, [offset, priority, status])

  useEffect(() => { load() }, [load, refreshKey])

  const openAlert = async (alertId) => {
    setSelected(null)
    setDetailLoading(true)
    try {
      setSelected(await api.alert(alertId))
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="page-stack">
      <section className="panel filter-panel">
        <div className="filter-toolbar">
          <label className="filter-control"><span>Priority</span><select value={priority} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setPriority(event.target.value) }}><option value="">All priorities</option><option value="P1">P1 · Critical</option><option value="P2">P2 · High</option><option value="P3">P3 · Moderate</option><option value="P4">P4 · Low</option></select></label>
          <label className="filter-control"><span>Status</span><select value={status} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setStatus(event.target.value) }}><option value="">All statuses</option><option value="new">New</option><option value="acknowledged">Acknowledged</option><option value="in_review">In review</option><option value="escalated">Escalated</option><option value="resolved">Resolved</option><option value="closed">Closed</option></select></label>
          <span className="filter-hint">Rules and evidence are provided by the risk engine.</span>
        </div>
      </section>

      {error ? <ErrorState error={error} onRetry={() => { setError(''); setLoading(true); load() }} /> : (
        <section className="panel">
          <div className="panel-heading"><div><p className="eyebrow">Rule-generated signals</p><h2>Alert queue</h2></div><span className="record-count">{page.total.toLocaleString()} alerts</span></div>
          {loading ? <LoadingState /> : page.items.length ? (
            <>
              <div className="table-scroll"><table>
                <thead><tr><th>Alert / transaction</th><th>Matched rule</th><th>Priority</th><th>Risk score</th><th>Status</th><th>Detected</th><th /></tr></thead>
                <tbody>{page.items.map((alert) => (
                  <tr key={alert.alert_id}>
                    <td><strong className="mono">{alert.alert_id}</strong><small className="cell-subtitle">{alert.triggering_transaction_id}</small></td>
                    <td><span className="rule-name">{alert.rule_key.replaceAll('_', ' ')}</span><small className="cell-subtitle">Rule v{alert.rule_version}</small></td>
                    <td><PriorityBadge value={alert.priority} /></td>
                    <td><strong>{(alert.aggregate_score_bps / 100).toFixed(0)}</strong><small className="cell-subtitle">basis points</small></td>
                    <td><StatusBadge value={alert.status} /></td>
                    <td>{formatDate(alert.detected_at)}</td>
                    <td><button className="text-button" onClick={() => openAlert(alert.alert_id)}>Evidence</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
              <div className="table-footer"><span className="muted">Ordered by detection time, newest first.</span><Pagination offset={offset} limit={pageSize} total={page.total} onChange={(nextOffset) => { setError(''); setLoading(true); setOffset(nextOffset) }} /></div>
            </>
          ) : <EmptyState title="No alerts match these filters" description="Try a different priority or status." />}
        </section>
      )}

      {(detailLoading || selected) && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="alert-detail-title" onClick={(event) => event.stopPropagation()}>
            <div className="panel-heading"><div><p className="eyebrow">Explainable signal</p><h2 id="alert-detail-title">Alert evidence</h2></div><button className="icon-button" aria-label="Close evidence" onClick={() => setSelected(null)}>×</button></div>
            {detailLoading ? <LoadingState /> : selected && (
              <>
                <div className="detail-id mono">{selected.alert_id}</div>
                <p className="alert-explanation">{selected.explanation}</p>
                <div className="detail-grid">
                  <Detail label="Rule" value={`${selected.rule_key.replaceAll('_', ' ')} · v${selected.rule_version}`} />
                  <Detail label="Priority" value={<PriorityBadge value={selected.priority} />} />
                  <Detail label="Status" value={<StatusBadge value={selected.status} />} />
                  <Detail label="Transaction" value={<span className="mono">{selected.triggering_transaction_id}</span>} />
                  <Detail label="Score contribution" value={`${selected.score_contribution_bps} bps`} />
                  <Detail label="Aggregate risk score" value={`${selected.aggregate_score_bps} bps`} />
                  <Detail label="Detected" value={formatDate(selected.detected_at)} />
                  <Detail label="Evaluated" value={formatDate(selected.evaluated_at)} />
                </div>
                <h3 className="subsection-title">Evidence</h3>
                <pre className="evidence-block">{JSON.stringify(selected.evidence, null, 2)}</pre>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function Detail({ label, value }) {
  return <div className="detail-item"><span>{label}</span><strong>{value}</strong></div>
}

export default Alerts
