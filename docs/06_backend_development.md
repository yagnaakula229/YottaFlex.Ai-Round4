# Phase 6: Backend Development

**Status:** Implemented and verified against the small SQLite demo database. This phase adds backend services and APIs on the Phase 5 schema; it does not add frontend functionality or verify full-scale performance.

## 1. Architecture

FastAPI routers are registered under `/api` in `backend/app/main.py`. Route handlers validate inputs, obtain a SQLAlchemy session through the shared database dependency, call service functions, and return Pydantic response models. Shared HTTP error handling is registered centrally.

| Responsibility | Location |
|---|---|
| Application and router registration | `backend/app/main.py`, `backend/app/api/` |
| Configuration and error mapping | `backend/app/core/` |
| Request/response validation and pagination | `backend/app/schemas/` |
| ORM/database session and SQLite constraints | `backend/app/database/`, `backend/app/models/` |
| Transaction reads | `backend/app/services/transaction_service.py` |
| Rule predicates and scoring | `backend/app/services/risk_engine.py` |
| Rule loading, evaluation context, alert persistence | `backend/app/services/risk_service.py` |
| Explainable account relationships | `backend/app/services/link_analysis.py` |
| Case grouping, lifecycle, actions, audit history | `backend/app/services/case_service.py` |
| Dashboard and separate ground-truth metrics | `backend/app/services/analytics_service.py`, `evaluation_service.py` |

The database dependency uses the existing SQLite configuration and foreign-key enforcement. The application does not automatically load `.env`; configure supported variables in the process environment. `/health`, `/docs`, and `/openapi.json` are available.

## 2. HTTP API

All business endpoints are under `/api`. Paginated list responses use `items`, `total`, `limit`, and `offset`; request schemas and response models are documented by OpenAPI.

| Method and path | Behavior |
|---|---|
| `GET /api/transactions` | Paginated transaction listing; optional account, type, status, time-window filters; allowlisted sort field and direction. |
| `GET /api/transactions/{transaction_id}` | Transaction detail; 404 if missing. |
| `GET /api/accounts/{account_id}/transactions` | Paginated account ledger; 404 if account is missing. |
| `GET /api/accounts/{account_id}/links` | Explainable account relationships within a bounded lookback window; 404 if account is missing. |
| `GET /api/alerts` | Paginated alert listing with priority, status, rule, and triggering-transaction filters. |
| `GET /api/alerts/{alert_id}` | Alert detail including rule version, score, explanation, and evidence; 404 if missing. |
| `GET /api/cases` | Paginated case listing with status and priority filters. |
| `GET /api/cases/{case_id}` | Case, linked alerts, append-only analyst actions, and relevant audit events; 404 if missing. |
| `POST /api/cases/group` | Group eligible related alerts into new cases or attach a related singleton alert to an active case; bounded `limit` query parameter. |
| `POST /api/cases/{case_id}/actions` | Record a validated analyst action; creates an append-only action and audit record. |
| `POST /api/risk/evaluate` | Evaluate one posted transaction or a bounded keyset-paginated batch; creates/idempotently updates risk-engine alerts. |
| `GET /api/dashboard/summary` | Return operational counts, priority distribution, open cases, account risk distribution, and dispositions. |
| `GET /api/analytics/evaluation` | Separately compare risk-engine transaction predictions with the ground-truth JSONL labels. |

Invalid query/body values return 422 validation responses. Missing resources return 404; invalid state or chronology conflicts return 409. Operational evaluation does not return truth labels. The case action endpoint uses the synthetic identity `analyst-demo-001`; authentication and authorization are not implemented, so this is for a local synthetic-data demo only.

## 3. Deterministic risk evaluation

Only posted transactions are evaluated. The engine is rule-based, uses transaction/account history and versioned active `RiskRule` rows, and does not import or query the ground-truth dataset.

| Rule key | Condition and evidence |
|---|---|
| `velocity_spike` | Posted transaction count in the configured trailing window (default 60 minutes) meets the configured minimum (default 5). Evidence records the count and window. |
| `new_device` | Device is present and this is its first observed use for the account. Evidence includes account/device identifiers and first-use status. |
| `circular_transfer` | A reconciled transfer path that includes the transaction forms a cycle meeting the configured minimum account count; search is bounded by the configured hop limit. Evidence contains the account path and transfer IDs. |
| `dormant_reactivation` | Account was dormant at posting, or the gap since prior activity meets the configured dormant period (default 90 days). |
| `high_value` | Debit or credit amount meets the configured unusual-amount threshold (default 250,000 USD minor units). The database key remains `high_value`; the user-facing rule is unusual transaction amount. |
| `linked_suspicious` | A related transaction has an existing risk-engine alert within the configured lookback (default 30 days). Evidence records the related alert references. |

Each finding snapshots rule ID/key/version, triggering transaction ID, UTC evaluation time, score contribution, evidence, and a human-readable explanation. No random values or LLM decisions are used. A posted transaction can trigger multiple rules.

## 4. Scoring and alert creation

Contributions are stored in basis points. The demo defaults are velocity 2,500; unusual amount 3,000; new device 2,500; dormant reactivation 3,500; circular transfers 5,000; and linked suspicious 3,000 bps. These are demonstration policy values, not calibrated risk estimates. The transaction score is the sum of its risk-engine alert contributions, capped at 10,000 bps:

| Priority | Aggregate score |
|---|---:|
| P1 | 7,500–10,000 bps |
| P2 | 5,000–7,499 bps |
| P3 | 2,500–4,999 bps |
| P4 | 0–2,499 bps |

An alert is persisted only for a valid transaction and rule, with `source = risk_engine` and a snapshot of the triggering rule evidence. The unique rule/transaction constraint and source-aware logic prevent duplicate detector alerts while keeping the Phase 5 representative seed alerts distinct from detector output. Priority is updated consistently for all risk-engine alerts on that transaction; priority changes are audited.

## 5. Linked accounts and case grouping

Account-link responses describe evidence, not suspicion. Implemented reasons include effective-dated shared customers, active shared devices, reconciled transfers in the lookback window, and related transactions using a shared device (including a short-interval pattern). Results include the accounts and relationship-specific identifiers/timing/amount evidence.

The grouping service considers eligible active alerts and excludes alerts already linked to an active case. Two or more unlinked eligible alerts continue to be grouped into connected components, creating new cases when alerts share an account or have a supported relationship. For exactly one unlinked eligible alert, the service checks linked alerts in active cases using the same account-link analysis; a match attaches the alert to the oldest qualifying case by `(created_at, case_id)`. An unrelated singleton remains ungrouped. Attachment recalculates priority from all linked alerts, updates the case timestamp, and records a `case.alert_attached` audit event in the same transaction. The response keeps `case_ids` for newly created cases and reports attachments separately in `attached_case_ids`. The `CaseAlert` case/alert uniqueness constraint prevents duplicate pairs, while the active-link check makes repeated sequential grouping idempotent. Concurrent grouping calls are not serialized by a database-level unique constraint on an alert's active association.

Case state transitions are validated in the service. Analyst actions support review start, notes, disposition, status change, escalation, close, and reopen operations. Dispositions use the stored enum values `suspicious`, `false_positive`, `inconclusive`, and `referred`; API aliases include `CONFIRMED_SUSPICIOUS`, `FALSE_POSITIVE`/`LEGITIMATE`, `NEEDS_MORE_INFORMATION`, and `ESCALATED` as an action type. Actions require a valid case chronology and lifecycle; invalid operations are rejected and audited. Successful actions are append-only, use the synthetic analyst ID, and preserve notes (up to 500 characters), timestamps, and details. Idempotency keys are supported.

## 6. Dashboard and ground-truth evaluation

Dashboard values are database-derived, not placeholders:

- `total_transactions` and `total_alerts` count operational rows, including representative seed alerts.
- `alerts_by_priority` counts alerts by stored priority.
- `open_cases` counts cases in `open`, `in_review`, or `escalated`.
- `account_risk_distribution` assigns each account its highest-priority linked alert, or `UNASSESSED` when it has none.
- `suspicious_transactions` counts distinct transactions whose latest per-alert disposition is `suspicious`.
- `analyst_dispositions` counts recorded disposition actions by stored enum value.

Only `evaluation_service.py` reads `ground_truth/generated/truth_2026.jsonl`. It validates records, rejects duplicate transaction labels, excludes `ambiguous` labels from binary metrics, and calculates transaction-level TP/FP/TN/FN, precision, recall, F1, false-positive rate, and precision among the top 100 risk-engine predictions. Ties are ordered by transaction ID. Seed/example alerts do not count as detector predictions. Zero-denominator metrics are returned as `0.0`. No label is copied into operational alerts, risk scores, or analyst decisions.

## 7. Migration, verification, and test commands

Phase 6 adds an Alembic migration after the original Phase 5 schema to permit the sixth `linked_suspicious` rule key and inserts its active version. The original migration is unchanged. The existing development database was upgraded in place without reseeding or deleting records.

Run from `backend/` in the project virtual environment:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
python -m pytest -q
python -m compileall -q app migrations tests
python -m pip check
```

Final verification results:

| Check | Result |
|---|---|
| `python -m pytest -q` | 19 passed; one Starlette deprecation warning about HTTPX/TestClient. |
| `python -m compileall -q app migrations tests` | Passed. |
| `python -m pip check` | Passed; no broken requirements. |
| `python -m alembic current` | `a61c9f3d10b2 (head)`. |
| Existing database after migration | 500 transactions, 6 rules, 10 alerts, 1 case, 1 analyst action, 2 audit events; no SQLite foreign-key violations. |
| SQLite rule immutability triggers | Both `prevent_active_risk_rule_update` and `prevent_risk_rule_id_update` remain present. |
| Isolation in tests | API/risk/case/evaluator and migration tests use temporary SQLite databases; the suite does not reset the development database. |

The tests cover all six predicates, no-trigger/multiple-trigger behavior, deterministic scoring/capping/priority, alert idempotency and constraints, list/detail APIs, keyset evaluation, relationship evidence, case grouping and action chronology, dashboard/evaluator behavior, ground-truth isolation, and populated Phase 5 migration preservation.

## 8. Limitations and next work

- The 100,000-transaction target has not been generated, benchmarked, or profiled; bounded batch evaluation and existing indexes are not a performance guarantee.
- SQLite is the only database verified. PostgreSQL compatibility, production migrations, and dialect-specific trigger equivalents are unverified.
- Authentication, authorization, analyst identity selection, rate limiting, and deployment security are not implemented. Do not expose the demo action endpoint externally.
- Rule parameters/contributions and thresholds are demo policy; detection quality has not been calibrated. Metrics describe the current synthetic labels and detector output, not real-world effectiveness.
- The frontend remains the Vite starter and is not connected to these APIs. No browser/E2E or cross-tier integration tests have been run.
- A Starlette deprecation warning recommends `httpx2` for `TestClient`; dependency replacement was not made as part of this phase.

Phase 6 backend implementation is complete for the verified local demo scope. The next task is **Phase 7 — Backend Testing**, focused on expanding/hardening automated backend coverage and addressing the warning without overstating scale or production readiness.
