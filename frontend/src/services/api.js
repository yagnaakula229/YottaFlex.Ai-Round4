const configuredBase = import.meta.env.VITE_API_BASE_URL
const API_BASE = (configuredBase || '/api').replace(/\/+$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })

  const payload = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const message = payload?.error?.message || payload?.detail || `Request failed (${response.status})`
    throw new Error(message)
  }
  return payload
}

function queryString(params) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) query.set(key, value)
  })
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export const api = {
  dashboard: () => request('/dashboard/summary'),
  transactions: (params = {}) => request(`/transactions${queryString(params)}`),
  transaction: (transactionId) => request(`/transactions/${encodeURIComponent(transactionId)}`),
  evaluateTransaction: (transactionId) => request('/risk/evaluate', {
    method: 'POST',
    body: JSON.stringify({ transaction_id: transactionId }),
  }),
  alerts: (params = {}) => request(`/alerts${queryString(params)}`),
  alert: (alertId) => request(`/alerts/${encodeURIComponent(alertId)}`),
  cases: (params = {}) => request(`/cases${queryString(params)}`),
  case: (caseId) => request(`/cases/${encodeURIComponent(caseId)}`),
  groupCases: () => request('/cases/group', { method: 'POST' }),
  recordCaseAction: (caseId, action) => request(`/cases/${encodeURIComponent(caseId)}/actions`, {
    method: 'POST',
    body: JSON.stringify(action),
  }),
}

export { API_BASE }
