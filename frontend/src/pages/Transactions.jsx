import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../services/api.js'
import { EmptyState, ErrorState, LoadingState, Pagination, StatusBadge } from '../components/Ui.jsx'
import { formatDate, formatMoney } from '../services/format.js'

const pageSize = 25

function Transactions({ refreshKey, onRefresh }) {
  const [page, setPage] = useState({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const [type, setType] = useState('')
  const [accountId, setAccountId] = useState('')
  const [accountFilter, setAccountFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    try {
      const result = await api.transactions({
        limit: pageSize,
        offset,
        status,
        transaction_type: type,
        account_id: accountFilter,
      })
      setPage(result)
    } catch (loadError) {
      setError(loadError.message)
    } finally {
      setLoading(false)
    }
  }, [offset, status, type, accountFilter])

  useEffect(() => { load() }, [load, refreshKey])

  const visibleRows = useMemo(() => page.items.filter((transaction) => {
    const term = search.trim().toLowerCase()
    return !term || transaction.transaction_id.toLowerCase().includes(term) || transaction.account_id.toLowerCase().includes(term)
  }), [page.items, search])

  const selectTransaction = async (transactionId) => {
    setSelected(null)
    setDetailLoading(true)
    setMessage('')
    try {
      setSelected(await api.transaction(transactionId))
    } catch (detailError) {
      setMessage(detailError.message)
    } finally {
      setDetailLoading(false)
    }
  }

  const evaluate = async () => {
    if (!selected) return
    setActionLoading(true)
    setMessage('')
    try {
      const result = await api.evaluateTransaction(selected.transaction_id)
      const created = result.alerts_created
      setMessage(`Risk evaluation completed for ${selected.transaction_id}${created === undefined ? '.' : `; ${created} new alert${created === 1 ? '' : 's'} created.`}`)
      onRefresh()
    } catch (actionError) {
      setMessage(actionError.message)
    } finally {
      setActionLoading(false)
    }
  }

  const applyAccountFilter = (event) => {
    event.preventDefault()
    setError('')
    setLoading(true)
    setOffset(0)
    setAccountFilter(accountId.trim())
  }

  return (
    <div className="page-stack">
      <section className="panel filter-panel">
        <form className="filter-toolbar" onSubmit={applyAccountFilter}>
          <label className="search-field"><span aria-hidden="true">⌕</span><input aria-label="Search transaction or account ID on this page" placeholder="Search IDs on this page" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
          <label className="filter-control"><span>Status</span><select value={status} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setStatus(event.target.value) }}><option value="">All statuses</option><option value="posted">Posted</option><option value="pending">Pending</option><option value="declined">Declined</option><option value="voided">Voided</option></select></label>
          <label className="filter-control"><span>Type</span><select value={type} onChange={(event) => { setError(''); setLoading(true); setOffset(0); setType(event.target.value) }}><option value="">All types</option><option value="purchase">Purchase</option><option value="cash_withdrawal">Cash withdrawal</option><option value="deposit">Deposit</option><option value="transfer">Transfer</option><option value="fee">Fee</option><option value="refund">Refund</option><option value="adjustment">Adjustment</option></select></label>
          <label className="filter-control account-filter"><span>Account ID</span><input value={accountId} onChange={(event) => setAccountId(event.target.value)} placeholder="e.g. ACC-00001" /></label>
          <button className="button button-primary" type="submit">Apply</button>
          {accountFilter && <button className="button button-quiet" type="button" onClick={() => { setError(''); setLoading(true); setAccountId(''); setAccountFilter(''); setOffset(0) }}>Clear</button>}
        </form>
      </section>

      {error ? <ErrorState error={error} onRetry={() => { setError(''); setLoading(true); load() }} /> : (
        <section className="panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Operational ledger</p><h2>Transaction activity</h2></div>
            <span className="record-count">{page.total.toLocaleString()} records</span>
          </div>
          {loading ? <LoadingState /> : visibleRows.length ? (
            <>
              <div className="table-scroll"><table>
                <thead><tr><th>Transaction</th><th>Account</th><th>Time</th><th>Type</th><th>Amount</th><th>Status</th><th /></tr></thead>
                <tbody>{visibleRows.map((transaction) => (
                  <tr key={transaction.transaction_id}>
                    <td><strong className="mono">{transaction.transaction_id}</strong></td>
                    <td className="mono">{transaction.account_id}</td>
                    <td>{formatDate(transaction.transaction_at)}</td>
                    <td>{transaction.transaction_type.replaceAll('_', ' ')}</td>
                    <td>{formatMoney(transaction.debit_minor || transaction.credit_minor, transaction.currency)}</td>
                    <td><StatusBadge value={transaction.status} /></td>
                    <td><button className="text-button" onClick={() => selectTransaction(transaction.transaction_id)}>Details</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
              <div className="table-footer"><span className="muted">{search ? `Search is limited to this ${page.items.length}-record page.` : 'Sorted by transaction time, newest first.'}</span><Pagination offset={offset} limit={pageSize} total={page.total} onChange={(nextOffset) => { setError(''); setLoading(true); setOffset(nextOffset) }} /></div>
            </>
          ) : <EmptyState title={search ? 'No matching transactions on this page' : 'No transactions found'} description={search ? 'Try another ID or move to another page.' : 'Adjust the filters or clear the account filter.'} />}
        </section>
      )}

      {(detailLoading || selected) && (
        <div className="modal-backdrop" role="presentation" onClick={() => { setSelected(null); setMessage('') }}>
          <section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="transaction-detail-title" onClick={(event) => event.stopPropagation()}>
            <div className="panel-heading">
              <div><p className="eyebrow">Transaction record</p><h2 id="transaction-detail-title">Transaction details</h2></div>
              <button className="icon-button" aria-label="Close details" onClick={() => { setSelected(null); setMessage('') }}>×</button>
            </div>
            {detailLoading ? <LoadingState /> : selected && (
              <>
                <div className="detail-id mono">{selected.transaction_id}</div>
                <div className="detail-grid">
                  <Detail label="Account" value={selected.account_id} />
                  <Detail label="Status" value={<StatusBadge value={selected.status} />} />
                  <Detail label="Transaction time" value={formatDate(selected.transaction_at)} />
                  <Detail label="Posted time" value={formatDate(selected.posted_at)} />
                  <Detail label="Type" value={selected.transaction_type.replaceAll('_', ' ')} />
                  <Detail label="Amount" value={formatMoney(selected.debit_minor || selected.credit_minor, selected.currency)} />
                  <Detail label="Merchant" value={selected.merchant_id || '—'} />
                  <Detail label="Device" value={selected.device_id || '—'} />
                </div>
                <div className="modal-actions">
                  <button className="button button-primary" disabled={selected.status !== 'posted' || actionLoading} onClick={evaluate}>{actionLoading ? 'Evaluating…' : 'Run risk evaluation'}</button>
                  {selected.status !== 'posted' && <span className="muted">Only posted transactions can be evaluated.</span>}
                </div>
                {message && <p className="inline-message" role="status">{message}</p>}
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

export default Transactions
