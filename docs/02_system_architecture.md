# Phase 2: System Architecture

**Project:** RiskTrace AI  
**Status:** Original Phase 2 architecture proposal. The Phase 4 schema and approved defaults are authoritative in [docs/04_database_design.md](04_database_design.md), and the Phase 5 persistence implementation is documented in [docs/05_database_implementation.md](05_database_implementation.md). Business APIs, risk evaluation, and frontend integration remain proposed.

## 1. Architecture goals

- Keep presentation, application logic, and relational persistence in separate tiers.
- Provide deterministic, explainable risk decisions with traceable evidence.
- Preserve relational and temporal integrity.
- Prevent ground-truth labels from entering detector inputs.
- Quarantine deliberately invalid scenarios without weakening operational constraints.
- Support a 100,000-transaction synthetic baseline on SQLite and avoid unnecessary database-specific coupling.

## 2. Three-tier architecture

| Tier | Responsibility | Required technology | Current implementation |
|---|---|---|---|
| Presentation | Analyst alert/case review, evidence, filters, and dispositions | React, Vite, JavaScript, CSS | Generic Vite/React starter screen only; no product UI or API client |
| Application/API | Validation, use cases, rules, case grouping, audit, evaluation orchestration | Python, FastAPI, Pydantic, SQLAlchemy 2.x | Minimal `FastAPI(title="RiskTrace AI")`; framework docs routes only |
| Relational data | Operational entities, constraints, indexes, action/audit history | SQLite for hackathon; PostgreSQL compatibility considered | Phase 5 SQLAlchemy models, SQLite engine/session, Alembic migration, generator, and validator; no domain API integration |

The frontend and backend currently run independently. There is no browser-to-API or API-to-database integration.

## 3. Proposed component architecture

```mermaid
flowchart LR
    Analyst["Analyst / demo user"]
    UI["React + Vite UI<br/>alert queue, case review, actions"]
    API["FastAPI routers<br/>Pydantic request/response contracts"]
    UseCases["Application services<br/>query, review, grouping, metrics"]
    Risk["Deterministic risk engine<br/>versioned rules + evidence"]
    Generator["Synthetic data generator<br/>fixed seed + validators"]
    ORM["SQLAlchemy 2.x repositories"]
    DB[("SQLite operational database")]
    Exceptions["Exception/rejection records<br/>isolated invalid fixtures"]
    Truth["Separate ground-truth files/store"]
    Evaluation["Evaluation service<br/>metrics against truth"]
    Audit["AuditEvent / AnalystAction"]

    Analyst --> UI -->|"HTTP/JSON; proposed /api/v1"| API
    API --> UseCases
    UseCases --> Risk
    UseCases --> ORM --> DB
    Generator --> ORM
    Generator --> Exceptions
    Generator --> Truth
    Risk -. "must not read" .-> Truth
    DB --> Evaluation
    Truth --> Evaluation
    UseCases --> Audit
    Audit --> ORM
```

Ground truth is reachable only by the evaluation path. The detector and operational query path must not read labels, label-derived features, or scenario identifiers that reveal labels.

## 4. ER design (original proposal, refined in Phase 4)

The original conceptual design has been refined into the approved 16-entity Phase 4 schema and implemented in Phase 5. The diagram below reflects that design; field-level constraints and deletion rules in `docs/04_database_design.md` are authoritative.

```mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ACCOUNT : owns
    ACCOUNT ||--o{ CUSTOMER_ACCOUNT : ownership
    CUSTOMER ||--o{ CUSTOMER_DEVICE : uses
    DEVICE ||--o{ CUSTOMER_DEVICE : association
    CUSTOMER ||--o{ KYC_PROFILE : has_versions
    ACCOUNT ||--o{ TRANSACTION : records
    MERCHANT o|--o{ TRANSACTION : counterparty
    DEVICE o|--o{ TRANSACTION : observed_on
    ACCOUNT ||--o{ TRANSFER_LINK : source_account
    ACCOUNT ||--o{ TRANSFER_LINK : destination_account
    TRANSACTION ||--o| TRANSFER_LINK : source_leg
    TRANSACTION ||--o| TRANSFER_LINK : destination_leg
    TRANSACTION o|--o| TRANSACTION : reversal_of
    RISK_RULE ||--o{ ALERT : evaluates
    TRANSACTION ||--o{ ALERT : triggers
    CASE ||--o{ CASE_ALERT : groups
    ALERT ||--o{ CASE_ALERT : associated
    CASE ||--o{ ANALYST_ACTION : action_history
    ALERT o|--o{ ANALYST_ACTION : action_context
    EXCEPTION_RECORD {
        string exception_id PK
        string scenario_code
        string subject_type
        string subject_id "informational; no FK"
    }
    AUDIT_EVENT {
        string audit_event_id PK
        string entity_type
        string entity_id "informational; no FK"
        string event_type
    }
```

`ExceptionRecord` and `AuditEvent` have independent informational polymorphic identifiers and no ER relationship/FK between them. The diagram includes all 16 entities; a transaction reversal is optional one-to-one.

### Relationship intent

- Customer and Account use `CustomerAccount` to represent ownership; joint ownership remains possible.
- Customer and Device use `CustomerDevice` to represent observed association and potential first/last-seen context.
- Account owns transaction activity. Merchant and Device are optional transaction references depending on transaction type.
- `TransferLink` references source/destination accounts and transaction legs; Phase 4 approves same-currency equal debit/credit legs, with no fees, partial transfers, or FX.
- Each Alert references the exact rule version used and source transaction/evidence. A historical rule definition or immutable snapshot is needed to reproduce the decision.
- Case and Alert associate through `CaseAlert`; links preserve association history.
- AnalystAction records append-only time-ordered review/disposition history for a required Case and optional Alert context.
- `ExceptionRecord` stores deliberately invalid/rejected scenarios outside valid operational records. `AuditEvent` captures changes using informational `(entity_type, entity_id)` fields, not polymorphic FKs.
- KYCProfile stores versioned customer records; UTC timestamps, USD-only money, ownership effective dates, and deletion policy are finalized in Phase 4.

## 5. API contract baseline (proposed, not implemented)

### Contract conventions

- Base path proposal: `/api/v1`.
- JSON request/response bodies with Pydantic validation.
- Stable public IDs follow the agreed ID grammar; do not assume the ambiguous example `ACC--01` is final.
- Timestamps should be serialized as ISO 8601 with an explicit UTC offset; the SQLAlchemy UTC type normalizes storage/application round trips.
- Monetary values must use a documented decimal/string representation and currency; do not use binary floating-point for money.
- List responses should use documented pagination (initial proposal: `limit` and opaque `cursor`) and stable ordering. Cursor format and maximum page size are TBD.
- Standard errors should include a stable machine-readable `code`, human-readable `message`, optional field `details`, and request/correlation ID. Avoid exposing stack traces or sensitive fields.
- Authentication/authorization is not specified; the proposed contracts do not imply that endpoints are safe to expose publicly.

### Proposed endpoints

| Method and path | Purpose | Proposed success / errors |
|---|---|---|
| `GET /health` | Process/liveness check; future readiness may check DB separately | `200` with service status; `503` if readiness is requested and dependency is unavailable |
| `GET /api/v1/alerts` | Filter and page prioritized alerts | `200` page with alert summary/evidence pointer; `400` invalid filters; `422` invalid parameter format |
| `GET /api/v1/alerts/{alert_id}` | Retrieve a single alert and its explainability evidence | `200`; `404` unknown ID |
| `GET /api/v1/cases` | Filter/page review cases by lifecycle/priority | `200`; `400` invalid filters |
| `GET /api/v1/cases/{case_id}` | Retrieve case, associated alerts, and action history | `200`; `404` unknown ID |
| `POST /api/v1/cases/{case_id}/actions` | Record an analyst action/disposition | `201` persisted action; `404` unknown case; `409` invalid state/chronology conflict; `422` invalid body |
| `GET /api/v1/rules` | Read active/versioned rule metadata for explainability | `200`; `404` if a specific version is not found |
| `GET /api/v1/metrics` | Retrieve a documented evaluation/operational report | `200`; `409` if evaluation inputs/ground truth are unavailable or mismatched |

These endpoints are an initial contract proposal, not current routes. Finalize naming, auth, filtering, pagination, case/action state, and error semantics before implementation. Synthetic generation is initially better specified as a reproducible command/service than an unprotected public endpoint; whether an admin API is needed is TBD.

### Proposed payload shapes

Examples show field intent only; they are not approved Pydantic schemas.

Alert summary:

```json
{
  "alert_id": "ALT-2026-000001",
  "priority": "TBD",
  "score": "TBD",
  "triggered_rule": {
    "rule_id": "TBD",
    "version": "TBD"
  },
  "triggering_transaction_id": "TXN-2026-00000001",
  "detected_at": "2026-01-01T12:00:00Z",
  "evidence": [],
  "case_ids": []
}
```

Analyst action request:

```json
{
  "disposition": "TBD",
  "note": "Optional analyst rationale",
  "actor_id": "TBD"
}
```

The disposition vocabulary, actor identity/auth model, score scale, evidence schema, and exact requirement for a note must be resolved. Do not use these examples to seed production values.

## 6. Data flow

1. Read seed/config version and generate master records (customers, merchants, devices, accounts, KYC, ownership associations).
2. Generate transaction activity and paired transfer links using valid foreign keys.
3. Derive account balances/statuses from source activity under approved ledger and lifecycle semantics.
4. Validate IDs, references, transaction state, balances, transfer reconciliation, and counts.
5. Route intentionally invalid scenarios to a separate rejection/exception path; do not insert them into valid operational tables.
6. Generate/maintain ground-truth labels in a separate artifact/store, inaccessible to detector data access.
7. Run versioned risk rules only against permitted operational data/features.
8. Persist alert evidence, score contributions, rule version, trigger transaction, detection timestamp, and priority.
9. Group related alerts into cases under a documented deterministic linkage policy.
10. Let analysts retrieve evidence and append actions/dispositions and audit events through the API.
11. Evaluate outputs against the separate ground truth and emit a report with defined unit, formulas, and thresholds.

## 7. Risk-engine workflow

```mermaid
flowchart TD
    Txns["Validated operational transactions"]
    Features["Build allowed rule features<br/>velocity, value, device, dormancy, transfer graph"]
    Evaluate["Evaluate deterministic active rule versions"]
    Evidence["Capture rule/version, triggering txn,<br/>evidence and score contribution"]
    Aggregate["Aggregate contributions using approved score policy"]
    Prioritize["Map score/evidence to approved priority"]
    Persist["Persist explainable Alert"]
    Group["Group related alerts into Case"]
    Review["Analyst reviews and records action"]
    Audit["Append AuditEvent"]
    Truth["Ground truth isolated from detector"]
    Metrics["Offline evaluation report"]

    Txns --> Features --> Evaluate --> Evidence --> Aggregate --> Prioritize --> Persist --> Group --> Review --> Audit
    Persist -. "evaluation only" .-> Metrics
    Truth --> Metrics
```

Initial rules: transaction velocity spike, high-value transaction, new-device activity, dormant-account reactivation, and circular transfers. The approved demo policy uses a 0–10,000 bps scale, sums/caps contributions per transaction, and assigns P1/P2/P3/P4 at >=7,500 / >=5,000 / >=2,500 / below 2,500. Phase 5 seed configuration contains fixed per-rule contributions, but no detector, rule evaluation, or metrics implementation exists. Detection must be deterministic and explainable; ground truth must not be used to calculate detection features or determine alerts.

## 8. Exception and invalid-scenario workflow

```mermaid
flowchart LR
    Scenario["Generated scenario / input"]
    Validate["Validate references, lifecycle,<br/>balance, transfer and chronology"]
    Valid{"Valid operational record?"}
    Operational["Persist valid operational data"]
    Quarantine["Reject or quarantine separately"]
    Record["ExceptionRecord with scenario,<br/>validation reason and outcome"]
    Metrics["Exception/validation report"]

    Scenario --> Validate --> Valid
    Valid -->|yes| Operational
    Valid -->|no, intentional fixture| Quarantine --> Record --> Metrics
```

Required exception cases:

1. Transaction references a closed account.
2. Negative balance exists without overdraft.
3. Transfer legs do not reconcile.
4. Alert has no triggering transaction.
5. Case disposition precedes its alert.

For each, retain the input/scenario identifier, validation rule, reason, and reject/quarantine outcome. The Phase 5 seed stores all five scenarios as quarantined `ExceptionRecord` payloads and keeps invalid rows out of operational tables. Preserve strict foreign-key and chronology constraints for valid records.

## 9. Cross-cutting requirements

- **Auditability:** keep analyst actions and material changes time ordered; define correction/undo semantics.
- **Security/privacy:** synthetic-only data; authentication and authorization are open requirements; do not expose admin/generation behavior without a policy.
- **Reliability:** explicit validation and errors; avoid success-shaped fallbacks.
- **Performance:** measure generation, indexing, alert queries, and case loading on the 100,000-transaction baseline before claiming capacity.
- **Portability:** SQLite is the hackathon database; PostgreSQL compatibility is a future consideration and should be tested if treated as a delivery requirement.
- **Testing:** pytest/HTTPX API and data-integrity tests, frontend build verification, and later end-to-end coverage. Phase 6 adds isolated backend tests; dedicated expanded backend hardening and end-to-end coverage remain pending.

## 10. Current versus proposed status

| Capability | Current evidence | Proposed target |
|---|---|---|
| Frontend | Vite/React starter counter/tutorial | Analyst alert and case workflow |
| API | FastAPI transaction, alert, case/action, risk evaluation, account-link, dashboard, and evaluation routes under `/api`; `/docs` and health route | Frontend integration, authentication, deployment hardening, and any additional contract changes |
| Database | Phase 5 SQLite schema plus additive Phase 6 migration `a61c9f3d10b2`; development DB retains its seeded rows | PostgreSQL portability validation and full target-size benchmark |
| Data generation | Small deterministic 50/70/500 seed baseline, validation, separate truth JSONL | Full target-size generation and benchmark; preserve detector/evaluator separation |
| Risk rules | Six versioned rule keys, deterministic evaluation, evidence snapshots, score cap, priority assignment | Calibrate/validate demo rule parameters against representative data |
| Cases/actions/audit | Case grouping, lifecycle validation, analyst action endpoint, append-only action and audit history | Authenticated analyst identities and integrated product workflows |
| Exceptions | Five quarantined seed ExceptionRecords | API-level exception reporting and operational error handling |
| Evaluation | Separate transaction-level ground-truth JSONL and isolated precision/recall/F1/FPR/top-100 evaluation endpoint | Larger-scale evaluation and validated scoring methodology |

Phase 4 design and Phase 5 database implementation are complete for the small baseline. Phase 6 backend functionality is implemented and tested within the documented local-demo scope. The React starter remains independent and is not connected to these APIs; do not infer frontend or production readiness from backend completion.
