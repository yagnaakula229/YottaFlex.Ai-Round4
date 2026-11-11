# RiskTrace AI: Project Context

**Status snapshot:** 2026-11-11  
**Product status:** Scaffold only; requirements below describe intended behavior unless marked implemented.

## Project overview and business problem

RiskTrace AI is a hackathon application for explainable transaction-risk monitoring and analyst case management. The intended system uses synthetic banking activity and transparent rules to prioritize transactions and linked accounts for human review. The handover must not be interpreted as a claim that detection, data generation, or case management already exists.

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

These are requirements supplied in the project brief; none are implemented in the current repository.

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
- The backend creates `FastAPI(title="RiskTrace AI")`.
- There are no domain routes, frontend-to-backend calls, database configuration/session, SQLAlchemy models, migrations, or database files.
- The browser and backend are not integrated.

See [ARCHITECTURE_REFERENCE.md](ARCHITECTURE_REFERENCE.md) for diagrams and route status.

## Domain entities and intended relationships

The list below is a design vocabulary, not an implemented schema. Resolve cardinalities, nullable fields, uniqueness, effective dating, and delete/update behavior during Phase 4.

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
- **CaseAlert** — alert/case association; permits multiple alerts per case and, if desired, reassignment/history.
- **ExceptionRecord** — isolated record of a deliberately invalid or validation-failing scenario.
- **AuditEvent** — append-oriented record of material system and analyst changes.

### Proposed relationship outline

- Customer ↔ Account: many-to-many through `CustomerAccount`.
- Customer ↔ Device: many-to-many through `CustomerDevice`.
- Customer → KYCProfile: one-to-zero/one or one-to-many versions (Phase 4 decision).
- Account → Transaction: one-to-many.
- Merchant/Device → Transaction: optional one-to-many references where the activity type supports them.
- TransferLink → sender/receiver Transaction: references both legs; each transfer must reconcile under the chosen fee/currency model.
- RiskRule version → Alert: one-to-many; each alert snapshots the exact rule version used.
- Transaction → Alert: one-to-many; operational alerts require a triggering transaction. Invalid orphan scenarios are quarantined as exceptions.
- Case ↔ Alert: many-to-many through `CaseAlert`.
- Case → AnalystAction: one-to-many; actions are time ordered.
- AuditEvent and ExceptionRecord: link to affected records where possible and preserve the original validation context.

## Risk rules and scoring

Initial proposed rules:

- Transaction velocity spike.
- High-value transaction.
- New-device activity.
- Dormant-account reactivation.
- Circular transfers.

Rule thresholds, lookback windows, score scale, contribution weights, score caps, priority bands, tie-breaking, and version activation policy are **not specified yet**. Phase 4 should avoid embedding assumptions about them in the database design; Phase 5/6 should agree on these before implementation.

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
- The exact account ID example `ACC--01` is ambiguous. Preserve it as a supplied example, but resolve the intended account ID grammar before generating data. Other supplied examples are `CUS-000001`, `TXN-2026-00000001`, `ALT-2026-000001`, and `CASE-2026-000001`.
- Transaction posting order, currency/decimal precision, reversals, transaction lifecycle, and account overdraft semantics require explicit Phase 4 decisions.

## Required exception scenarios

The following are deliberately invalid cases, not valid operational records:

1. Transaction references a closed account.
2. Account has a negative balance without an overdraft allowance.
3. Transfer legs do not reconcile.
4. Alert has no triggering transaction.
5. Case disposition precedes its alert.

Represent these in a separate, labeled validation/exception path. Do not silently insert them into valid operational tables. Decide whether exception fixtures are raw input, rejected rows, or `ExceptionRecord` cases; preserve a reason and validation outcome. The orphan-alert and temporal-order cases must not weaken constraints for valid alerts/actions.

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

No metric definitions or thresholds have yet been approved. Proposed measures to discuss include precision, recall, F1, false-positive rate, alert volume, precision/recall at a review-capacity cutoff, case-linkage quality, and analyst workflow measures (time to disposition, backlog/throughput). Specify ground-truth label semantics, unit of evaluation (transaction/alert/case), threshold selection, and treatment of unreviewed alerts before reporting metrics. Never claim these metrics exist until implemented and tested.

## Constraints, assumptions, and unresolved questions

- Hackathon implementation uses SQLite; PostgreSQL is a portability consideration only.
- Synthetic data only; no real customer data or credentials should be added.
- The project brief is the current requirements source; there is no separate Phase 1/2 specification or architecture decision record in the repository.
- One local developer setup is verified; runtime versions on other machines are not guaranteed.
- No auth/authorization requirements or analyst identity provider have been selected.
- Resolve: account ID format, currency and monetary precision, time zone, transaction statuses, overdraft handling, KYC versioning, rule score/priority scale, dispositions, case ownership/closure states, ground-truth schema, and exception storage policy.
