# RiskTrace AI frontend

The React + Vite analyst workspace reads operational data from the FastAPI backend. It does not connect to SQLite directly and does not display evaluation ground-truth labels.

## Run locally

Start the backend from `backend/`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite proxies `/api` requests to `http://127.0.0.1:8000`. To use another backend, define `VITE_API_BASE_URL` as its API base (for example `https://api.example.test/api`) before starting or building the frontend.

## Available screens

- **Overview:** backend dashboard totals, priority distribution, account risk distribution, recent alerts, and cases.
- **Transactions:** paginated listing, account/status/type filters, current-page ID search, transaction details, and per-transaction risk evaluation for posted transactions.
- **Alerts:** paginated priority/status filters and rule evidence details.
- **Cases:** case listing and filters, eligible-alert grouping, linked alert details, analyst notes, review/disposition workflow, action history, and audit events.

The backend requires a case to be in `in_review` before recording a disposition. Use **Start review** first when that action is available. Search on the transactions screen is limited to the currently loaded page because the API does not expose a free-text search parameter.

## Build and verification

From `frontend/`, run:

```powershell
npm run build
```

The production build has passed. The frontend was also verified against the local FastAPI server through Vite's `/api` proxy: dashboard summary, transaction, alert, and case list requests returned successfully and the corresponding screens displayed backend data. Analyst workflow UI uses the existing API contracts; a live state-mutating analyst workflow against the development database was not part of that read-only integration verification.

The configured Oxlint command exits successfully but reports four `react(set-state-in-effect)` warnings in the four screen components, associated with asynchronous API-load state updates. These have not been refactored. There is no separate frontend unit/E2E test suite configured.

## Scope and limitations

- The API client uses the FastAPI operational API; React never accesses SQLite directly.
- Ground-truth evaluation labels are not part of the analyst UI or operational API data flow.
- Transaction search is limited to the loaded page; the backend has no free-text search endpoint.
- Risk evaluation is available for posted transactions. Case disposition requires the case to be in review.
- The displayed analyst identity is synthetic and unauthenticated. Do not expose the demo application externally without authentication and authorization.
