# RiskTrace AI: Project Context

**Status snapshot:** 2026-11-11  
**Product status:** Phase 5 relational schema, small deterministic seed baseline, validation, and separate ground-truth JSONL are implemented. Phase 6 backend APIs, deterministic risk detection, analyst workflows, and evaluation are also implemented for the local demo scope. Product UI and frontend/API integration remain unimplemented.

## Project overview and business problem

RiskTrace AI is a hackathon application for explainable transaction-risk monitoring and analyst case management. The system uses synthetic banking activity and transparent rules to prioritize transactions and linked accounts for human review. Phase 6 implements these backend workflows; no product analyst UI is available yet.

The business objective is to help analysts review a prioritized, evidence-backed queue, connect related activity, record dispositions, and evaluate detection quality without hiding the reason an alert was raised.

## Functional requirements

1. Generate reproducible synthetic customers, accounts, merchants, devices, transactions, transfers, alerts, and cases.
2. Preserve valid relational references and reconcile transaction balances.
3. Include normal activity, suspicious patterns, and intentional false positives.
4. Apply deterministic and explainable rules; retain rule identity/version, evidence, triggering transaction, score contribution, detection time, and priority with each alert.
5. Prioritize alerts and group related alerts into reviewable cases.
6. Record analyst actions/dispositions and preserve an audit trail.
7. Store evaluation ground truth separately from detector input.
8. Produce measurable evaluation metrics and validate reproducibility/data consistency.
9. Isolate explicitly invalid exception scenarios instead of silently corrupting valid operational data.

These are project requirements. Phases 5 and 6 implement the relational schema, small deterministic seed data, validation, exception/truth storage, backend detection and workflows, and a separate evaluation service. Full-scale performance and end-to-end behavior remain unverified.

## Non-functional requirements

- Deterministic output under a fixed seed (`20261022`) and documented generation inputs.
- Explainable, reviewable rule outcomes; no opaque score without evidence.
- Referential integrity, explicit validation errors, and auditable analyst changes.
- Keep ground-truth labels out of the detection data path.
- Handle the requested baseline of 100,000 transactions locally and allow performance to be measured.
- Keep the persistence design relational and SQLite-friendly while avoiding unnecessary SQLite-only application coupling where practical.
- Keep frontend/backend independently installable and testable.
- Do not commit credentials, local `.env`, virtual environments, node modules, database files, or build output.
- PostgreSQL portability is a future consideration, not a current deployment requirement.

## Three-tier architecture

### Target

1. **Presentation:** React + Vite + JavaScript + CSS for analyst workflows.
2. **Application/API:** Python + FastAPI, Pydantic request/response validation, and SQLAlchemy 2.x persistence.
3. **Relational storage:** SQLite for the hackathon; later PostgreSQL compatibility may be evaluated.

### Implemented

- The frontend is an independent Vite/React starter and currently renders its generic counter/tutorial screen.
- The backend creates `FastAPI(title="RiskTrace AI")` and implements the routes documented in `docs/06_backend_development.md`.
- The backend has SQLAlchemy 2.x models for all 16 designed entities, SQLite connection/FK enforcement, UTC handling, Alembic migrations through `a61c9f3d10b2`, seed generation, and data-quality validation.
- The local `backend/risktrace.db` is generated, Git-ignored runtime data. The browser and backend are not integrated.

See [ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md) for diagrams and route status.

## Domain entities and intended relationships

The list below is implemented in the Phase 5 schema. `docs/04_database_design.md` is the authoritative field-level design; `docs/05_database_implementation.md` documents the implemented schema and verification.

### Core entities

1. **Customer** — synthetic person/entity owning one or more accounts.
2. **Account** — synthetic financial account; has an account status and balance history or derived ledger.
3. **Merchant** — counterparty for applicable purchase transactions.
4. **Device** — synthetic device seen in customer activity.
5. **Transaction** — posted or otherwise explicitly modeled activity on an account; references an account and may reference a merchant/device.
6. **TransferLink** — links the sender and receiver transaction legs for a transfer and stores reconciliation evidence/status.
7. **RiskRule** — versioned deterministic detector rule and its configured contribution.
8. **Alert** — rule outcome linked to evidence and the triggering transaction.
9. **Case** — analyst review container for related alerts.
10. **AnalystAction** — time-ordered analyst disposition/action associated with a case and optionally an alert.

### Supporting entities

- **KYCProfile** — synthetic customer KYC attributes; minimize attributes to what the demo needs.
- **CustomerAccount** — ownership association (supports joint ownership if selected).
- **CustomerDevice** — customer/device association, optionally with first/last-seen timestamps.
- **CaseAlert** — alert/case association; permits multiple alerts per case and records link/unlink state; detailed policy is in the Phase 4 design.
- **ExceptionRecord** — isolated record of a deliberately invalid or validation-failing scenario.
- **AuditEvent** — append-oriented record of material system and analyst changes.

### Proposed relationship outline

- Customer ↔ Account: many-to-many through `CustomerAccount`.
- Customer ↔ Device: many-to-many through `CustomerDevice`.
- Customer → KYCProfile: one-to-zero/many versioned profiles (specified in the Phase 4 design baseline).
- Account → Transaction: one-to-many.
- Merchant/Device → Transaction: optional one-to-many references where the activity type supports them.
- TransferLink → sender/receiver Transaction: references both legs; each transfer must reconcile under the chosen fee/currency model.
- RiskRule version → Alert: one-to-many; each alert snapshots the exact rule version used.
- Transaction → Alert: one-to-many; operational alerts require a triggering transaction. Invalid orphan scenarios are quarantined as exceptions.
- Case ↔ Alert: many-to-many through `CaseAlert`.
- Case → AnalystAction: one-to-many; actions are time ordered.
- AuditEvent and ExceptionRecord: link to affected records where possible and preserve the original validation context.

## Risk rules and scoring

Implemented deterministic Phase 6 rules:

- Transaction velocity spike.
- High-value transaction.
- New-device activity.
- Dormant-account reactivation.
- Circular transfers.
- Linked suspicious transactions supported by related alert evidence.

The approved demo scale is 0–10,000 bps; contributions are summed per transaction and capped at 10,000. Priority bands are P1 >= 7,500, P2 >= 5,000, P3 >= 2,500, otherwise P4. Case priority is the highest currently linked alert priority. Six deterministic rule versions are implemented; their contributions are demo policy values, not calibrated risk estimates. Evaluation uses the separate ground-truth service and does not feed labels into detection.

At minimum, an alert should preserve the triggered rule and version, triggering transaction, evidence, score contribution, detection timestamp, and risk priority. Scores should be reproducible from the same input and rule version.

## Synthetic data requirements

Baseline targets from the project brief:

| Record type | Target |
|---|---:|
| Customers | 5,000 |
| Accounts | 7,000 |
| Transactions | 100,000 |
| Alerts | 1,000 |

- Fixed random seed: `20261022`.
- Generate master records before dependent records; validate all foreign keys.
- Generate valid operational activity with balances derived from source transaction/ledger records and reconciled transfer legs.
- Cover ordinary patterns plus velocity spikes, new devices, circular transfers, dormant-account reactivation, and false positives.
- Keep truth labels in a separate `ground_truth/` artifact/flow; neither rules nor detector queries may read those labels.
- Run consistency checks and compare deterministic output across repeated runs.
- Phase 4 adopts the literal `ACC--` prefix followed by a positive decimal ordinal with minimum width two (`ACC--01`, expanding beyond two digits as needed). Other supplied examples are `CUS-000001`, `TXN-2026-00000001`, `ALT-2026-000001`, and `CASE-2026-000001`.
- The Phase 5 generator currently validates a small baseline of 50 customers, 70 accounts, 20 merchants, 30 devices, and 500 transactions. The target 5,000/7,000/100,000/1,000 configuration validates but has not been generated or benchmarked.
- The schema uses integer minor-unit money, UTC-normalized timestamps, ordered posted ledger entries, optional one-to-one compensating reversals, and overdraft validation.

## Required exception scenarios

The following are deliberately invalid cases, not valid operational records:

1. Transaction references a closed account.
2. Account has a negative balance without an overdraft allowance.
3. Transfer legs do not reconcile.
4. Alert has no triggering transaction.
5. Case disposition precedes its alert.

The Phase 5 seed represents all five scenarios as quarantined `ExceptionRecord` payloads; invalid candidates are not inserted into valid operational tables. The orphan-alert and temporal-order cases do not weaken constraints for valid alerts/actions.

## Business workflow (target)

1. Create deterministic master data.
2. Generate transaction/transfer activity and derive balances/statuses.
3. Validate references, ledger reconciliation, and domain invariants.
4. Run versioned rules using detection inputs only.
5. Persist explainable alert evidence and priorities.
6. Group linked alerts into cases.
7. Analyst reviews evidence and records a timestamped action/disposition.
8. Append audit history and compute evaluation metrics against separately held ground truth.
9. Export validated operational and evaluation outputs separately.

## Evaluation metrics

The implemented evaluation service reports precision, recall, F1, false-positive rate, and top-100 precision at transaction level; ambiguous labels are excluded from binary metrics. Evaluation is separate from operational detection. See `docs/06_backend_development.md` for implemented metric details and limitations.

## Constraints, assumptions, and unresolved questions

- Hackathon implementation uses SQLite; PostgreSQL is a portability consideration only.
- Synthetic data only; no real customer data or credentials should be added.
- The project brief and [Phase 1 analysis](../01_problem_analysis.md) are the requirements baseline; [Phase 2 architecture](../02_system_architecture.md) is a proposal. No architecture decision record exists in the repository.
- One local developer setup is verified; runtime versions on other machines are not guaranteed.
- No auth/authorization requirements or analyst identity provider have been selected.
- Phase 4 decisions are incorporated in `docs/04_database_design.md`; Phase 5 and 6 implementation evidence is in `docs/05_database_implementation.md` and `docs/06_backend_development.md`. The next task is Phase 7 — Backend Testing. The 100k workload, PostgreSQL portability, authentication, frontend/API integration, and end-to-end behavior remain to be verified.
