# RiskTrace AI: Technical Decisions and Open Questions

**Snapshot:** 2026-11-11  
**Repository evidence:** the only reachable commit is `9fb2c99` (`Set up RiskTrace AI project`). There are no earlier phase commits or formal ADR files. This log separates choices mandated by the project brief, observed setup choices, recommendations, and decisions not yet made.

## Phase-by-phase decision/change evidence

| Phase | Evidence in repository | Technical decisions actually made |
|---|---|---|
| 1 — Problem Analysis | `docs/01_problem_analysis.md` was created in the current uncommitted documentation work from the supplied hackathon statement. | Records requirements, acceptance criteria, assumptions, and unresolved questions. Inferred personas are explicitly not confirmed stakeholder decisions. |
| 2 — System Architecture | `docs/02_system_architecture.md` was created in the current uncommitted documentation work. | Records a proposed three-tier architecture, conceptual ER relationships, proposed API contracts, data/risk/exception flows. These are documented proposals, not implemented routes or an approved database schema. |
| 3 — Project Setup | Commit `9fb2c99` adds the app scaffold, dependency manifests, `.env.example`, `.gitignore`, and setup documentation. | Chose/created the required React/Vite/JavaScript and Python/FastAPI scaffolds, declared SQLAlchemy 2.x/Pydantic/pytest/HTTPX, and reserved SQLite configuration. This is setup evidence, not a domain architecture or database implementation. |
| 4 — Database Design and Data Dictionary | No schema, dictionary, ER artifact, or phase-specific commit found. | No schema or storage semantics approved. |
| 5 — Database Implementation and Seed Data | No models, database engine, migrations, generator, seed records, or phase-specific commit found. | No persistence or data-generation choices implemented. |
| 6 — Backend Development | Only the Phase 3 FastAPI shell exists; no domain API/service/rule implementation or phase-specific commit found. | No endpoint, score, case, or analyst workflow contract implemented. |
| 7 — Backend Testing | No test modules or test-runner additions; no phase-specific commit found. | pytest/HTTPX are setup dependencies only; no test design is implemented. |
| 8 — Frontend Development | Vite/React starter source is present from the scaffold commit; no product UI or API integration. | No product interaction, state, or frontend/API design implemented. |
| 9 — Frontend Testing | No frontend test files or behavior-test script found. | No frontend test strategy/tool choice beyond lint/build scripts. |
| 10 — Frontend-Backend-Database Integration | No integration code or database exists. | No CORS, API base URL, persistence lifecycle, or integration decision implemented. |
| 11 — End-to-End Testing | No E2E tests or harness found. | No E2E technology or workflow decision evidenced. |
| 12 — Documentation and Final Handoff | Current handover package and root README are being created/updated in the uncommitted worktree; see `PROJECT_PROGRESS.md`. | Documentation records current evidence and recommendations; it does not approve the proposed architecture or scoring/schema decisions. No source-code decision or release decision was made. |

This table describes repository evidence; it does not claim that no discussion happened outside the repository.

## Decisions/constraints from the project brief

| Topic | Decision/constraint | Status and rationale |
|---|---|---|
| Frontend | React, Vite, JavaScript, CSS | Required; JavaScript (not TypeScript) is an explicit constraint. Scaffold exists. |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Pydantic | Required stack; minimal FastAPI shell and dependency declarations exist. |
| Database | SQLite for hackathon; PostgreSQL migration compatibility as a future consideration | Required; schema and connection are not implemented. |
| Testing | pytest, HTTPX, API integration tests, frontend build verification | Required testing tools/goals; pytest/HTTPX installed, but no pytest test cases or API integration tests exist. |
| Synthetic data | Fixed seed `20261022`, specified target counts, deterministic identifiers and relational integrity | Requirements only; no generator exists. |
| Detection | Deterministic, explainable risk rules; preserve per-alert evidence and rule version | Requirements only; no rules engine or score policy exists. |
| Ground truth | Keep evaluation labels separate from detection inputs | Required leakage boundary; no implementation exists. |
| Git/secrets | Keep local secrets and generated/runtime directories out of commits | `.gitignore` exists. |

## Choices observed in the repository

- The frontend uses the Vite React JavaScript template, `@vitejs/plugin-react`, and Oxlint; React, Vite, and build dependencies are captured in `frontend/package.json`/lockfile.
- The backend uses a top-level `app` package under `backend/`; startup target is `app.main:app`.
- The current app title is `RiskTrace AI`.
- `.env.example` provides `APP_NAME`, `DATABASE_URL`, `RANDOM_SEED`, `API_HOST`, and `API_PORT`, but the application does not load or consume these values yet.
- Backend dependency ranges use minimum/maximum version constraints rather than a lock file; an environment was verified at the versions recorded in `SETUP_AND_EXECUTION.md`.
- The committed frontend uses the standard Vite/React starter UI, and `frontend/package-lock.json` records its npm dependency resolution.
- The setup verification on this workstation used Python 3.13.2, FastAPI 0.162.4, Uvicorn 0.54.0, SQLAlchemy 2.1.8, Pydantic 2.14.3, pytest 8.4.2, HTTPX 0.28.1, Node.js 26.13.0, and npm 11.20.0. These are observed local versions, not a promise that every environment resolves to the same patch versions.
- Node.js was installed as a portable per-user runtime outside the repository after the MSI required an administrator prompt. It is not a project dependency artifact and must be installed separately on another machine.
- Setup notes record that the Windows `py` launcher was absent (`python` was used) and that an initial absolute-path Vite scaffold invocation produced a misplaced folder; it was moved into `frontend/` and verified there. These are setup resolutions, not product design decisions.

## Proposed engineering decisions to take to Phase 4+

### Database and domain model

- Design a relational schema with explicit PK/FK and `CHECK`/unique constraints where appropriate; keep invalid demonstration scenarios out of valid operational tables.
- Define currency, monetary decimal precision, timestamps/time zone, transaction lifecycle, balance derivation/ledger, overdraft semantics, and deletion policy before choosing concrete column types/constraints.
- Keep status vocabularies and rule versions explicit and stable; snapshot enough rule metadata/evidence with alerts for reproducible review.
- For SQLite/PostgreSQL portability, avoid relying on SQLite-only types/SQL in business services, document UUID/ID strategy, and test constraints on the target backend. These are recommendations, not implemented decisions.

### Risk scoring

- Keep rule outcomes deterministic and persist the individual contribution/evidence before aggregating.
- Select a bounded score scale, aggregation/caps, threshold/priority bands, tie handling, rule activation/version policy, and historical rescoring behavior before Phase 6.
- Do not infer numeric weights or thresholds from this handover; none are specified in the brief or code.

### Synthetic data generation

- Proposed order: master entities → associations → accounts/KYC/devices → transaction stream → paired transfer legs → truth labels and scenarios → validation.
- Derive balances and statuses from authoritative generated operational records rather than separately randomizing them.
- Fix all randomness sources/ordering and record the seed/config version. Keep truth labels outside detector input and access paths.
- Define IDs from stable ordinal/key material. `ACC--01` is ambiguous and must be clarified before generation.

### Error handling and security

- Current error handling is only FastAPI's framework default; there is no domain validation or application logging/error contract.
- Future API work should return explicit validation/not-found/conflict errors, avoid success-shaped fallbacks, and preserve useful server-side diagnostics without leaking sensitive information.
- No auth, role model, transport security, deployment boundary, or secret-management design is implemented. Determine the minimum hackathon analyst identity/authorization scope before exposing case actions.
- Use synthetic-only data; never add real personal/financial data or credentials to fixtures, docs, or commits.

### Performance and auditability

- Required local baseline reaches 100,000 transactions; benchmark realistic indexes and batch generation/query patterns once a schema exists.
- Use deterministic fixtures and record reproducibility/validation outputs; do not assert performance until measured.
- Keep analyst actions/audit events time ordered and append-oriented; define correction/undo semantics rather than erasing history.

## Trade-offs

- SQLite minimizes local setup and is suitable for the hackathon baseline, while PostgreSQL compatibility may limit use of dialect-specific features.
- Synthetic data supports safe demonstrations and repeatable evaluation but does not establish real-world model effectiveness.
- Deterministic rules improve transparency/reproducibility, but thresholds and label quality will bound detection quality.
- A simple starter frontend enables setup verification but has no product value until replaced with analyst workflows.

## Rejected alternatives

No rejected technology, architecture, score, or data-generation alternatives are recorded in the code or existing documentation. Do not invent an ADR or attribute an unrecorded rationale to the team.

## Decisions to close

1. Exact account ID grammar (`ACC--01` ambiguity).
2. Domain cardinalities and ownership/KYC versioning.
3. Currency, amount precision, transaction ordering, status/reversal model, balance and overdraft semantics.
4. Risk score scale/aggregation, weights, thresholds, priority mapping and rule-version lifecycle.
5. Case lifecycle, allowed analyst dispositions, identity and audit event semantics.
6. Exception fixture storage/rejection format and evaluation rules.
7. Ground-truth schema, label ontology, evaluation unit and metric thresholds.
8. Minimal authentication/authorization and API error contract.
