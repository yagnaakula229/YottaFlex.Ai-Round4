# Phase 1: Problem Analysis

**Project:** RiskTrace AI  
**Source:** Original RiskTrace AI hackathon project statement supplied in the project brief.  
**Status:** Requirements analysis documented; stakeholder interpretations and unresolved decisions are explicitly identified below.

## 1. Problem statement

Analysts need to review a large stream of banking transactions and identify suspicious activity involving transactions and linked accounts. A useful review system must make the highest-priority activity visible, explain why it was flagged, connect related alerts into cases, and preserve analyst decisions for audit and evaluation.

RiskTrace AI will demonstrate this workflow using deterministic synthetic banking data and transparent risk rules. It is not intended to make an opaque or autonomous financial decision. The system should help prioritize human review and show evidence that supports each alert.

## 2. Business objective and intended outcome

Build a three-tier application that can:

1. Generate a reproducible synthetic banking dataset with valid relationships.
2. Detect selected suspicious transaction patterns using deterministic rules.
3. Calculate explainable risk scores and prioritize alerts.
4. Group related alerts into reviewable cases.
5. Record analyst review/dispositions and retain an audit history.
6. Measure detection performance against ground truth that is kept separate from detection inputs.

The project is successful when a developer can generate the agreed dataset from a fixed seed, trace an alert back to its rule/version and source evidence, review related activity as a case, record a chronological analyst action, and run documented evaluation checks. These are target outcomes; they are not yet implemented.

## 3. Users and stakeholders

The project brief does not name real stakeholders or define access roles. The following are working personas inferred from the requested workflow and must be confirmed during product/design review:

- **Transaction analyst:** reviews prioritized alerts and evidence, opens related cases, and records a disposition.
- **Project operator/demo user:** initializes the synthetic dataset and starts the application for a hackathon demonstration.
- **Evaluator/developer:** checks reproducibility, data integrity, rule explanations, exception handling, and measurable metrics.

Authentication, authorization, analyst identity, and production deployment are not specified.

## 4. Scope

### In scope

- Synthetic customers, accounts, merchants, devices, transactions, transfer links, risk rules, alerts, cases, analyst actions, and supporting records.
- Relational integrity and transaction/balance reconciliation.
- Deterministic generation using seed `20261022`.
- Rule-based detection of the patterns listed below.
- Explainable scoring, prioritization, case grouping, analyst dispositions, audit history, and evaluation metrics.
- Explicitly labeled invalid scenarios isolated from valid operational data.
- SQLite for the hackathon implementation; PostgreSQL migration compatibility as a future consideration.
- The specified 12-phase delivery plan, with documentation per phase.

### Out of scope unless later approved

- Real customer or payment data.
- Autonomous blocking, declining, or freezing of transactions/accounts.
- Claims of production banking compliance, regulatory certification, or real-world detection efficacy.
- Machine-learning detection or unrequested external integrations.
- A production identity provider or multi-tenant deployment.

These exclusions are scope boundaries inferred from the brief, not stakeholder-approved policy.

## 5. Functional requirements and acceptance criteria

Acceptance criteria below make the original requirements testable. Where exact values or policy are absent, they are marked **TBD** rather than invented.

| ID | Requirement | Acceptance evidence |
|---|---|---|
| FR-01 | Generate baseline synthetic data: 5,000 customers, 7,000 accounts, 100,000 transactions, and 1,000 alerts. | A generation report shows counts and run configuration; exact count semantics (e.g., generated vs. accepted alerts) are confirmed before implementation. |
| FR-02 | Make data generation deterministic with random seed `20261022`. | Two clean runs with the same code/config/seed produce identical normalized data or a documented deterministic checksum; define which timestamps/ordering are included. |
| FR-03 | Use stable, deterministic identifiers and generate master records before dependent records. | ID-format tests and foreign-key validation pass; supplied examples include `CUS-000001`, `ACC--01`, `TXN-2026-00000001`, `ALT-2026-000001`, and `CASE-2026-000001`. Clarify the account example before finalizing its grammar. |
| FR-04 | Preserve relational integrity and reconcile transaction balances. | Referential-integrity checks find no invalid operational references; balances derive from transaction/ledger records under documented currency, ordering, and overdraft semantics. |
| FR-05 | Generate normal activity, velocity spikes, new-device activity, circular transfers, dormant-account reactivation, and false positives. | A scenario coverage report identifies each pattern and corresponding generated records without leaking truth labels into detection inputs. |
| FR-06 | Detect suspicious patterns using deterministic, explainable rules. | Rule tests demonstrate each agreed rule, boundary conditions, stable results, and reproducible evidence for known fixtures. |
| FR-07 | Produce explainable, prioritized alerts. | Each alert records triggering rule and version, triggering transaction, evidence, score contribution, detection time, and priority; scores and priority mapping follow an approved specification. |
| FR-08 | Group related alerts into cases. | Case-linking tests show the documented grouping behavior and preserve alert-to-case associations. The grouping policy is TBD. |
| FR-09 | Support analyst review and dispositions. | An analyst can record a valid action/disposition with actor, timestamp, target, and audit event; disposition vocabulary and case lifecycle are TBD. |
| FR-10 | Preserve audit history. | Material analyst/system actions are queryable in chronological order and corrections do not silently erase the original event. Exact retention policy is TBD. |
| FR-11 | Keep ground truth separate from detection input. | Detection code and operational queries cannot access label fields; evaluation consumes a separate truth artifact/path and tests detect prohibited leakage. |
| FR-12 | Measure evaluation performance. | A reproducible evaluation report states label definitions, evaluation unit, metric formula, threshold, and counts. Metric selection and acceptance thresholds are TBD. |
| FR-13 | Validate deliberately invalid data without corrupting valid operational records. | Each required exception scenario is identified, rejected or quarantined with its reason; normal operational integrity checks continue to pass. |

## 6. Initial detection patterns

The project brief proposes five initial deterministic rules:

1. Transaction velocity spike.
2. High-value transaction.
3. New-device activity.
4. Dormant-account reactivation.
5. Circular transfers.

Rule thresholds, lookback windows, score contributions, score range, aggregation, priority bands, tie-breaking, rule activation/version policy, and historical rescoring behavior are not defined. They require explicit technical/product decisions before implementation.

## 7. Data and identifier requirements

Requested entities:

- **Core:** Customer, Account, Merchant, Device, Transaction, TransferLink, RiskRule, Alert, Case, AnalystAction.
- **Supporting:** KYCProfile, CustomerAccount, CustomerDevice, CaseAlert, ExceptionRecord, AuditEvent.

Data requirements:

- Create master entities before dependent records and validate every foreign key.
- Reconcile account balances to their source activity and reconcile both legs of a transfer.
- Derive balances, scores, and statuses from authoritative source records rather than independently randomizing values.
- Keep operational data and ground-truth labels separate.
- Validate deterministic output and consistency.

The supplied account ID sample `ACC--01` is ambiguous and may be a typographical example. Do not silently normalize it; resolve it in Phase 4. Currency, amount precision, transaction ordering/status/reversal rules, time zone, account closure behavior, and overdraft policy are also TBD.

## 8. Required invalid/exception scenarios

These are intentional validation failures, not valid operational records:

1. A transaction references a closed account.
2. An account has a negative balance without an overdraft allowance.
3. Transfer legs do not reconcile.
4. An alert has no triggering transaction.
5. A case disposition precedes its alert.

Each scenario must be separately labeled and captured in an exception/rejection path with a reason and validation outcome. It must not bypass or weaken constraints for valid operational data. The storage representation (rejected source row, quarantined fixture, or `ExceptionRecord`) is a Phase 4/5 decision.

## 9. Non-functional requirements

- Deterministic, reproducible generation and rule evaluation.
- Explainable results that can be traced from priority/score to rule, evidence, and source transaction.
- Relational integrity and explicit exception handling.
- Ground-truth isolation from detection.
- Capacity for the requested 100,000-transaction local baseline; performance is to be measured, not assumed.
- Independently installable frontend and backend.
- SQLite hackathon setup with PostgreSQL compatibility considered in schema and query design.
- Synthetic data only; no secrets or real customer information in source control.
- Test results and phase status must reflect executed evidence; no undocumented completion claims.

## 10. Constraints, assumptions, and open questions

### Fixed by the brief

- Three-tier stack: React/Vite/JavaScript/CSS; Python/FastAPI/SQLAlchemy 2.x/Pydantic; SQLite.
- Fixed seed and baseline record counts.
- Required business entities and invalid scenarios.
- Initial transparent rule categories.
- Twelve project phases, each with its own documentation.

### Assumptions to validate

- The initial user is an analyst operating a local synthetic-data demo.
- An alert references at least one source transaction; an operational alert requires a trigger.
- Case grouping and score priorities are deterministic and versioned.
- Invalid scenarios should be demonstrable without entering the valid operational dataset.

### Questions for design/review

- What is the correct account ID format?
- What currency/currencies, amount precision, time zone, transaction statuses, posting order, and reversal behavior should be modeled?
- How are balances calculated and how are overdrafts/closed accounts represented?
- Which thresholds, lookback windows, score scale, weights, priority bands, and false-positive labels should be used?
- What links alerts into cases; can alerts move between cases?
- What analyst dispositions and case states are allowed? Is an analyst identity/authentication required?
- Which metrics and evaluation unit are required, and what thresholds constitute success?
- How should the five invalid records be represented and reported?
- Which PostgreSQL compatibility guarantees are required for the hackathon?

## 11. Delivery phase plan

1. Problem Analysis.
2. System Architecture.
3. Project Setup.
4. Database Design and Data Dictionary.
5. Database Implementation and Seed Data.
6. Backend Development.
7. Backend Testing.
8. Frontend Development.
9. Frontend Testing.
10. Frontend-Backend-Database Integration.
11. End-to-End Testing.
12. Documentation and Final Project Handoff.

At this document’s creation, the repository already contains Phase 3 setup. Phases 1 and 2 were not previously documented in the repository; this artifact records Phase 1 requirements analysis based on the supplied brief, while unresolved stakeholder decisions remain open.
