import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api.js'
import { EmptyState, ErrorState, LoadingState, Pagination, PriorityBadge, StatusBadge } from '../components/Ui.jsx'
import { formatDate } from '../services/format.js'

const pageSize = 20
const dispositions = [
  ['suspicious', 'Confirmed suspicious'],
  ['false_positive', 'False positive / legitimate'],
  ['inconclusive', 'Inconclusive'],
  ['referred', 'Referred'],
]

function Cases({ refreshKey, onRefresh }) {
  const [page, setPage] = useState({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [disposition, setDisposition] = useState('suspicious')
  const [alertId, setAlertId] = useState('')
  const [note, setNote] = useState('')
  const [resultMessage, setResultMessage] = useState('')

  const load = useCallback(async () => {
    try {
      setPage(await api.cases({ limit: pageSize, offset, status, priority }))
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }, [offset, status, priority])

  useEffect(() => { load() }, [load, refreshKey])

  const openCase = async (caseId) => {
    setSelected(null)
    setDetailLoading(true)
    setResultMessage('')
    try {
      setSelected(await api.case(caseId))
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setDetailLoading(false)
    }
  }

  const refreshSelected = async () => {
    if (!selected) return
    const refreshed = await api.case(selected.case_id)
    setSelected(refreshed)
    await load()
    onRefresh()
  }

  const performAction = async (payload, successMessage) => {
    if (!selected) return
    setBusy(true)
    setResultMessage('')
    try {
      await api.recordCaseAction(selected.case_id, payload)
      setResultMessage(successMessage)
      await refreshSelected()
    } catch (actionError) {
      setResultMessage(actionError.message)
    } finally {
      setBusy(false)
    }
  }

  const submitDisposition = (event) => {
    event.preventDefault()
    performAction({
      action_type: 'disposition_recorded',
      disposition,
      ...(alertId ? { alert_id: alertId } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    }, 'Disposition recorded and case history refreshed.')
    setNote('')
  }

  const submitNote = (event) => {
    event.preventDefault()
    if (!note.trim()) return
    performAction({ action_type: 'note_added', note: note.trim() }, 'Analyst note added.')
    setNote('')
  }

  const groupAlerts = async () => {
    setBusy(true)
    setResultMessage('')
    try {
      const result = await api.groupCases()
      const attached = result.attached_case_ids?.length || 0
      setResultMessage(`Grouping complete: ${result.cases_created} new cases, ${attached} existing cases updated, ${result.alert_count} eligible alerts examined.`)
      await load()
      onRefresh()
      if (selected) await openCase(selected.case_id)
    } catch (actionError) {
      setResultMessage(actionError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page-stack">
      <section className="panel filter-panel">
        <div className="filter-toolbar">
          <label className="filter-control"><span>Case status</span><select value={status} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setStatus(event.target.value) }}><option value="">All statuses</option><option value="open">Open</option><option value="in_review">In review</option><option value="escalated">Escalated</option><option value="resolved">Resolved</option><option value="closed">Closed</option></select></label>
          <label className="filter-control"><span>Priority</span><select value={priority} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setPriority(event.target.value) }}><option value="">All priorities</option><option value="P1">P1 · Critical</option><option value="P2">P2 · High</option><option value="P3">P3 · Moderate</option><option value="P4">P4 · Low</option></select></label>
          <span className="filter-hint">Use the current backend correlation rules to group eligible alerts.</span>
          <button className="button button-primary" disabled={busy} onClick={groupAlerts}>{busy ? 'Working…' : 'Group eligible alerts'}</button>
        </div>
      </section>

      {resultMessage && <div className="notice-banner" role="status">{resultMessage}</div>}
      {error ? <ErrorState error={error} onRetry={() => { setError(''); setLoading(true); load() }} /> : (
        <section className="panel">
          <div className="panel-heading"><div><p className="eyebrow">Investigation queue</p><h2>Case management</h2></div><span className="record-count">{page.total.toLocaleString()} cases</span></div>
          {loading ? <LoadingState /> : page.items.length ? (
            <>
              <div className="table-scroll"><table>
                <thead><tr><th>Case</th><th>Linked alerts</th><th>Priority</th><th>Status</th><th>Last updated</th><th /></tr></thead>
                <tbody>{page.items.map((item) => (
                  <tr key={item.case_id}>
                    <td><strong className="mono">{item.case_id}</strong><small className="cell-subtitle">{item.title}</small></td>
                    <td>{item.alert_count}</td>
                    <td><PriorityBadge value={item.priority} /></td>
                    <td><StatusBadge value={item.status} /></td>
                    <td>{formatDate(item.updated_at)}</td>
                    <td><button className="text-button" onClick={() => openCase(item.case_id)}>Open case</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
              <div className="table-footer"><span className="muted">Ordered by most recently updated.</span><Pagination offset={offset} limit={pageSize} total={page.total} onChange={(nextOffset) => { setError(''); setLoading(true); setOffset(nextOffset) }} /></div>
            </>
          ) : <EmptyState title="No cases match these filters" description="Change the status or priority filters, or group eligible alerts." />}
        </section>
      )}

      {(detailLoading || selected) && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSelected(null)}>
          <section className="detail-modal case-modal" role="dialog" aria-modal="true" aria-labelledby="case-detail-title" onClick={(event) => event.stopPropagation()}>
            <div className="panel-heading">
              <div><p className="eyebrow">Analyst investigation</p><h2 id="case-detail-title">Case details</h2></div>
              <button className="icon-button" aria-label="Close case" onClick={() => setSelected(null)}>×</button>
            </div>
            {detailLoading ? <LoadingState /> : selected && (
              <>
                <div className="case-summary">
                  <div><strong className="detail-id mono">{selected.case_id}</strong><p>{selected.title}</p></div>
                  <div className="case-summary-badges"><PriorityBadge value={selected.priority} /><StatusBadge value={selected.status} /></div>
                </div>
                <div className="case-meta"><span>{selected.alert_count} linked alerts</span><span>Created {formatDate(selected.created_at)}</span><span>Updated {formatDate(selected.updated_at)}</span></div>

                <section className="case-section">
                  <div className="section-heading"><h3>Linked alerts</h3><span>{selected.alerts.length}</span></div>
                  {selected.alerts.length ? <div className="linked-alert-list">{selected.alerts.map((alert) => (
                    <article className="linked-alert" key={alert.alert_id}>
                      <div><strong className="mono">{alert.alert_id}</strong><small>{alert.rule_key.replaceAll('_', ' ')} · {alert.triggering_transaction_id}</small><p>{alert.explanation}</p></div>
                      <div className="linked-alert-meta"><PriorityBadge value={alert.priority} /><StatusBadge value={alert.status} /><small>{alert.aggregate_score_bps} bps</small></div>
                    </article>
                  ))}</div> : <EmptyState title="No linked alerts" description="This case has no linked alert records." />}
                </section>

                <section className="case-section">
                  <div className="section-heading"><h3>Analyst workflow</h3><span>{selected.actions.length} actions</span></div>
                  {selected.status !== 'in_review' ? (
                    <div className="workflow-prompt">
                      <span>{['resolved', 'closed'].includes(selected.status) ? 'Reopen this case to continue the investigation.' : 'Move this case into review before recording a disposition.'}</span>
                      <button
                        className="button button-secondary"
                        disabled={busy}
                        onClick={() => {
                          const reopening = ['resolved', 'closed'].includes(selected.status)
                          performAction(
                            { action_type: reopening ? 'case_reopened' : 'review_started' },
                            reopening ? 'Case reopened for review.' : 'Case moved into review.',
                          )
                        }}
                      >
                        {['resolved', 'closed'].includes(selected.status) ? 'Reopen case' : 'Start review'}
                      </button>
                    </div>
                  ) : (
                    <form className="workflow-form" onSubmit={submitDisposition}>
                      <label className="filter-control"><span>Disposition</span><select value={disposition} onChange={(event) => setDisposition(event.target.value)}>{dispositions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                      <label className="filter-control"><span>Related alert (optional)</span><select value={alertId} onChange={(event) => setAlertId(event.target.value)}><option value="">Entire case</option>{selected.alerts.map((alert) => <option value={alert.alert_id} key={alert.alert_id}>{alert.alert_id}</option>)}</select></label>
                      <label className="filter-control workflow-note"><span>Analyst note (optional)</span><textarea maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add concise rationale for the decision" /></label>
                      <button className="button button-primary" disabled={busy}>{busy ? 'Saving…' : 'Record disposition'}</button>
                    </form>
                  )}
                  {selected.status !== 'in_review' && (
                    <form className="workflow-form note-form" onSubmit={submitNote}>
                      <label className="filter-control workflow-note"><span>Add an analyst note</span><textarea maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Document an observation or handoff" /></label>
                      <button className="button button-secondary" disabled={busy || !note.trim()}>{busy ? 'Saving…' : 'Add note'}</button>
                    </form>
                  )}
                  {resultMessage && <p className="inline-message" role="status">{resultMessage}</p>}
                  <div className="history-list">{selected.actions.slice().reverse().map((action) => (
                    <article className="history-item" key={action.action_id}>
                      <span className="history-marker" />
                      <div><strong>{action.action_type.replaceAll('_', ' ')}{action.disposition ? ` · ${action.disposition.replaceAll('_', ' ')}` : ''}</strong><small>{formatDate(action.action_at)} · {action.actor_id}</small>{action.note && <p>{action.note}</p>}</div>
                    </article>
                  ))}</div>
                  {!selected.actions.length && <p className="muted">No analyst actions recorded yet.</p>}
                </section>

                <section className="case-section">
                  <div className="section-heading"><h3>Audit history</h3><span>{selected.audit_events.length} events</span></div>
                  <div className="audit-list">{selected.audit_events.slice().reverse().map((event) => (
                    <article className="audit-item" key={event.audit_event_id}>
                      <div><strong>{event.event_type.replaceAll('.', ' · ').replaceAll('_', ' ')}</strong><small>{formatDate(event.event_at)} · {event.actor_type}: {event.actor_id}</small></div>
                      <details><summary>Payload</summary><pre className="evidence-block">{JSON.stringify(event.payload_json, null, 2)}</pre></details>
                    </article>
                  ))}</div>
                  {!selected.audit_events.length && <p className="muted">No audit events recorded.</p>}
                </section>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

export default Cases
