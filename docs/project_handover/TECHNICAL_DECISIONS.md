# RiskTrace AI: Technical Decisions and Open Questions

**Snapshot:** 2026-11-11 (final completion sprint)
**Repository evidence:** `9fb2c99` adds the Phase 3 scaffold; `68994b0` adds Phase 1/2 documentation and the original handover package. Phase 4–6 implementation and documentation remain uncommitted; no commit or push was made. No formal ADR files exist. This log separates project requirements, approved decisions, implementation evidence, and remaining work.

## Phase-by-phase decision/change evidence

| Phase | Evidence in repository | Technical decisions actually made |
|---|---|---|
| 1 — Problem Analysis | `docs/01_problem_analysis.md` was added in commit `68994b0` from the supplied hackathon statement. | Records requirements, acceptance criteria, assumptions, and unresolved questions. Inferred personas are explicitly not confirmed stakeholder decisions. |
| 2 — System Architecture | `docs/02_system_architecture.md` was added in commit `68994b0`; Phase 6 backend details are in `docs/06_backend_development.md`. | The architecture/API contracts began as proposals. Phase 4 approved the database design and Phase 6 implemented documented `/api` endpoints, risk behavior, and workflows; authentication, deployment, and frontend integration remain open. |
| 3 — Project Setup | Commit `9fb2c99` adds the app scaffold, dependency manifests, `.env.example`, `.gitignore`, and setup documentation. | Chose/created the required React/Vite/JavaScript and Python/FastAPI scaffolds, declared SQLAlchemy 2.x/Pydantic/pytest/HTTPX, and reserved SQLite configuration. Phase 6 later extended FastAPI with domain services and routes. |
| 4 — Database Design and Data Dictionary | `docs/04_database_design.md`. | Encodes the nine approved defaults, all 16 entity dictionaries and relationships, all five exceptions, ground-truth isolation, lifecycle, financial integrity, indexes, and trade-offs. Mermaid names all 16 entities; reversal is optional one-to-one; polymorphic audit/exception references have no FK edge. |
| 5 — Database Implementation and Seed Data | `backend/app/models/entities.py`, database/session modules, `backend/migrations/`, `backend/app/services/`, tests, and `docs/05_database_implementation.md`. | Implemented 16 SQLAlchemy entities, SQLite constraints/foreign keys, migrations, deterministic generation, quarantined exceptions, and separate truth JSONL. The 100,000-transaction generator was measured using an isolated temporary database. |
| 6 — Backend Development | `backend/app/api/`, schemas, services, migrations, tests, and `docs/06_backend_development.md`. | Implemented `/api` endpoints, six deterministic rules, basis-point scoring, alert persistence, explainable account links, case/actions/audit, dashboard, and isolated evaluation. Singleton alerts attach to the oldest related active case with priority recalculation and audit; no schema migration was needed. |
| 7 — Backend Testing | Backend tests for fixture isolation, API validation, ordering, pagination, references, workflows, and ground-truth isolation. | Completed; full pytest suite has 65 passing tests. One Starlette/TestClient deprecation warning remains. Concurrent grouping calls are not fully serialized. |
| 8 — Frontend Development and Integration | `frontend/src/`, Vite proxy, central API client, and frontend README. | Implemented Overview, Transactions, Alerts, and Cases screens backed by the FastAPI operational API. React does not access SQLite or evaluation labels. Live reads through the Vite proxy were verified. |
| 9 — Performance Benchmark (final completion sprint) | Temporary isolated SQLite benchmark; detailed results in root `README.md` and `PROJECT_PROGRESS.md`. | Generated 100,000 transactions in 60.222 seconds. Evaluated only the first 1,000 in 33.874 seconds (29.52 transactions/second). This does not establish full-dataset evaluation throughput. |
| 10 — Documentation (final completion sprint) | Root/frontend READMEs and four handover files. | Updated architecture, actual screen/API scope, benchmark methodology/results, verification evidence, limitations, and handoff. |
| Follow-up — Frontend/E2E verification | No automated frontend behavior/E2E test suite is configured. | Production build and API read integration are verified; a full state-mutating browser workflow against the development DB is not. |

This table describes repository evidence; it does not claim that no discussion happened outside the repository.

## Decisions/constraints from the project brief

| Topic | Decision/constraint | Status and rationale |
|---|---|---|
| Frontend | React, Vite, JavaScript, CSS | Required; JavaScript (not TypeScript) is an explicit constraint. Scaffold exists. |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Pydantic | Required stack; Phase 6 implements modular APIs, schemas, services, risk evaluation, and workflows. The exact implemented surface is in `docs/06_backend_development.md`. |
| Database | SQLite for hackathon; PostgreSQL migration compatibility as a future consideration | SQLite schema, engine/session, and Alembic migrations through `a61c9f3d10b2` are implemented. PostgreSQL compatibility is not verified. |
| Testing | pytest, HTTPX, API integration tests, frontend build verification | Full backend suite: 65 passed, with one Starlette TestClient deprecation warning. The backend verification also included Alembic check, compileall, pip check, and diff check. Frontend production build passed. |
| Synthetic data | Fixed seed `20261022`, specified target counts, deterministic identifiers and relational integrity | Small baseline and separate truth file are implemented. A temporary 100k dataset was generated and validated; risk evaluation was measured only for 1,000 transactions. |
| Detection | Deterministic, explainable risk rules; preserve per-alert evidence and rule version | Implemented in Phase 6. Six rule keys, rule/version snapshots, evidence, basis-point aggregation and priority thresholds are tested. Contributions remain demo values, not calibrated risk estimates. |
| Ground truth | Keep evaluation labels separate from detection inputs | Transaction-level JSONL remains outside operational tables. Phase 6 evaluator alone reads labels and calculates metrics; tests cover operational isolation. |
| Git/secrets | Keep local secrets and generated/runtime directories out of commits | `.gitignore` exists. |

## Choices observed in the repository

- The frontend uses the Vite React JavaScript template, `@vitejs/plugin-react`, and Oxlint; React, Vite, and build dependencies are captured in `frontend/package.json`/lockfile.
- The backend uses a top-level `app` package under `backend/`; startup target is `app.main:app`.
- The current app title is `RiskTrace AI`.
- `.env.example` provides `APP_NAME`, `DATABASE_URL`, `RANDOM_SEED`, `API_HOST`, and `API_PORT`, but the application does not load or consume these values yet.
- Backend dependency ranges use minimum/maximum version constraints rather than a lock file; an environment was verified at the versions recorded in `SETUP_AND_EXECUTION.md`.
- Alembic is now declared in `backend/requirements.txt`; the local environment used Alembic 1.20.1 during Phase 5 verification.
- The frontend now has product-specific analyst screens and API integration; `frontend/package-lock.json` records its npm dependency resolution.
- The setup verification on this workstation used Python 3.13.2, FastAPI 0.162.4, Uvicorn 0.54.0, SQLAlchemy 2.1.8, Pydantic 2.14.3, pytest 8.4.2, HTTPX 0.28.1, Node.js 26.13.0, and npm 11.20.0. These are observed local versions, not a promise that every environment resolves to the same patch versions.
- Node.js was installed as a portable per-user runtime outside the repository after the MSI required an administrator prompt. It is not a project dependency artifact and must be installed separately on another machine.
- Setup notes record that the Windows `py` launcher was absent (`python` was used) and that an initial absolute-path Vite scaffold invocation produced a misplaced folder; it was moved into `frontend/` and verified there. These are setup resolutions, not product design decisions.

## Approved Phase 4 design and Phase 5 implementation baseline

- Use text application-generated immutable public IDs; account IDs use literal `ACC--` followed by a positive ordinal with minimum width two, so `ACC--01` is the first and the value expands beyond two digits.
- Use portable SQLAlchemy types where practical: integer minor units for monetary values, UTC instants at application boundaries, JSON abstraction for non-query-critical evidence, and explicit SQLite foreign-key enforcement.
- Derive balances from account opening balance and ordered posted ledger entries; keep transaction opening/closing snapshots only for reconciliation. Model reversals as compensating posted transactions rather than edits/deletions.
- The approved synthetic baseline is USD-only (minor-unit exponent 2); cross-currency/FX behavior is excluded.
- The approved demo priority bands are P1 >= 7,500, P2 >= 5,000, P3 >= 2,500, otherwise P4, with per-transaction contributions summed and capped at 10,000 bps. This is demo policy, not validated risk calibration.
- Use reproducible event times in a fixed 2026 UTC window; reserve the `2026` ID namespace for this baseline and inject the clock for runtime-created actions/tests.
- Operational alerts require a triggering posted transaction and immutable rule version. Invalid/orphan records are quarantined in `ExceptionRecord`; ground truth is a separate versioned JSONL/CSV artifact, not an operational table.
- Use restrictive physical deletion and lifecycle states; `AnalystAction` and `AuditEvent` are append-only.
- Add indexes for time-ordered account transactions, alert priority/status, case status, rule, FK joins, action history, exceptions, and audit lookup.
- Phase 5 implements the design in SQLAlchemy/Alembic. SQLite triggers and ORM guards protect append-only analyst/audit rows and immutable primary keys; active or referenced rule versions cannot be edited.

## Phase 4 review decisions approved by the user

The following recommendations were approved in the decision-review exchange on 2026-11-11, incorporated into the authoritative Phase 4 design, and implemented where applicable in Phase 5:

1. **Currency:** USD-only for the synthetic baseline, exponent 2; reject other currencies in this dataset.
2. **Ownership:** Keep many-to-many and allow joint owners; leave ownership shares null for the demo; close an association and add a new effective-dated row rather than rewriting history.
3. **Transfers:** No fees, partial transfers, or FX. Require one same-currency debit leg and one equal credit leg.
4. **Scoring/priorities:** One alert per rule-version/transaction; sum contributions per transaction, cap at 10,000 bps; priority bands P1 >= 7,500, P2 >= 5,000, P3 >= 2,500, otherwise P4. Copy the transaction priority to its alerts; case priority is the highest member-alert priority. No DetectionRun in the demo; use rule/transaction idempotency.
5. **Case/actions:** Use the listed case/alert transitions and dispositions; reopening requires an audited action. Use one synthetic demo analyst ID without authentication; limit notes to 500 characters.
6. **Ground truth/metrics:** Separate versioned JSONL; evaluate at transaction level; labels `suspicious`/`legitimate`, exclude `ambiguous` from binary metrics; no train/validation split. Report precision, recall, F1, and precision among the top 100 alerts, clearly identified as demo metrics.
7. **Transfer mismatch:** Keep invalid candidates/payloads only in `ExceptionRecord`; do not create an operational `TransferLink` for the mismatch fixture.
8. **Time/IDs:** Use reproducible event times in a fixed 2026 UTC window; reserve the `2026` ID namespace for this baseline and require an explicit new namespace for later datasets. Inject the clock for runtime-created actions/tests.
9. **Migrations/retention:** Use Alembic with an initial migration. Retain synthetic analyst/audit history for the demo; reset generated data only through an explicit local reset. Do not add PII.

The approved decisions are encoded in `docs/04_database_design.md` and implemented where Phase 5/6 covers them. Fixed rule contributions are explicit configuration (2,500 / 3,000 / 2,500 / 3,500 / 5,000 / 3,000 bps for velocity / unusual amount / new-device / dormant-reactivation / circular-transfer / linked-suspicious). The aggregate is derived from risk-engine alert contributions, capped at 10,000 bps, and priority is assigned using the approved bands. These are demo policy values, not calibrated risk estimates.

## Current implementation notes and follow-up policy

### Database baseline and remaining validation

- The small SQLite schema and initial migration are implemented and tested. PostgreSQL DDL/behavior has not been tested; SQLite append-only, immutable-ID, and active-rule triggers are dialect-specific.
- The schema/generator validates ledger continuity, ownership intervals, transfers, alert/case priority, and action chronology for generated datasets. A 100,000-transaction generation was measured in isolated storage; the benchmark evaluated only a 1,000-transaction sample. Do not claim full-dataset evaluation performance or PostgreSQL support without evidence.

### Risk scoring

- Phase 6 implements six deterministic rules and per-alert evidence/contribution snapshots. The original seed alerts remain representative examples and are not detector output.
- Rule contributions and thresholds are demo policy; calibrate/validate them only with separately documented evaluation, never by leaking ground-truth labels into operational detection.

### Synthetic data generation

- A deterministic generator is implemented with seed `20261022`, fixed UTC timestamps, deterministic IDs, master-before-dependent insertion, paired transfer legs, and batched transaction writes.
- The validated demo baseline is 50 customers, 70 accounts, 20 merchants, 30 devices, 500 transactions, 25 reconciled transfers, and 500 separate transaction-level ground-truth records. The 5,000/7,000/100,000/1,000 target configuration was generated in temporary storage; full-dataset risk evaluation was not measured.
- The five invalid scenarios are quarantined in ExceptionRecord JSON payloads; invalid candidates are not inserted into operational tables. Operational risk detection does not read ground-truth labels; the separate Phase 6 evaluator is the only service that reads the truth JSONL.
- Public IDs use the approved formats; account IDs use `ACC--` plus an ordinal, and the `2026` namespace is reserved for this baseline.

### Error handling and security

- Phase 6 adds Pydantic validation, shared error handling, and explicit validation/not-found/conflict responses. Production logging/monitoring policy remains unverified.
- No auth, role model, transport security, deployment boundary, or secret-management implementation exists. The demo uses a synthetic analyst ID without authentication; production/external exposure requires a separate security decision.
- Use synthetic-only data; never add real personal/financial data or credentials to fixtures, docs, or commits.

### Performance and auditability

- Indexes cover ledger account/time scans, timestamp scans, customer/account/device relationships, alert priority/rule/transaction lookup, case queues, action history, transfers, exceptions, and audit history.
- Seed generation and truth JSONL are reproducible for a fixed seed; the default truth SHA-256 is recorded in `docs/05_database_implementation.md`. Generation at 100k transactions was measured; full-dataset risk evaluation was not.
- AnalystAction and AuditEvent rows are append-only and history is protected from the explicit reset command. No API authorization or production retention/redaction implementation exists.

## Trade-offs

- SQLite minimizes local setup and is suitable for the hackathon baseline, while PostgreSQL compatibility may limit use of dialect-specific features.
- Synthetic data supports safe demonstrations and repeatable evaluation but does not establish real-world model effectiveness.
- Deterministic rules improve transparency/reproducibility, but thresholds and label quality will bound detection quality.
- The React analyst UI is a hackathon workflow, not an authenticated or production-ready financial operations system.

## Rejected alternatives

No rejected technology, architecture, score, or data-generation alternatives are recorded in the code or existing documentation. Do not invent an ADR or attribute an unrecorded rationale to the team.

## Decisions and work still to close

1. Phase 6 case/action behavior and metric formulas are implemented in code and documented in `docs/06_backend_development.md`; Phase 7 added test coverage for API validation, ordering, pagination, and workflows.
2. The synthetic demo analyst ID remains unauthenticated for local hackathon use only; define authentication/authorization before external deployment.
3. Optimize/profile evaluation before attempting to evaluate all 100,000 transactions; PostgreSQL compatibility remains unverified.
4. Decide whether to replace the deprecated HTTPX/TestClient integration after checking compatible package versions and the project environment.
5. Active-case singleton attachment is implemented and covered. Simultaneous grouping requests are not serialized, and the schema does not enforce that an alert can have only one active case association; revisit if concurrent callers become a supported workload.
