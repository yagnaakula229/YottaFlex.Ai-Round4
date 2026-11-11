# Reusable AI Continuation Prompt

Copy this prompt into a new coding assistant while the `YottaFlex.Ai-Round4` repository is open:

```text
You are continuing RiskTrace AI in the current VS Code workspace.

Before working:
1. Read every file in docs/project_handover/, including its README.
2. Read README.md and docs/01_problem_analysis.md through docs/06_backend_development.md.
3. Inspect the actual source, configuration, migrations, tests, and Git status/diff. Documentation is not proof that implementation exists.
4. Preserve all pre-existing modified and untracked files. Do not reset, delete, stage, commit, or push unless explicitly authorized.
5. Never alter, reset, or reseed backend/risktrace.db or overwrite checked-in ground truth without explicit approval.

Current state:
- React + Vite + JavaScript frontend; Python + FastAPI + SQLAlchemy 2.x + Pydantic backend; SQLite + Alembic database.
- The frontend has Overview, Transactions, Alerts, and Cases screens, a centralized API client, and a Vite `/api` proxy. It reads through FastAPI and does not access SQLite or ground-truth labels directly.
- Backend includes 16 ORM entities, six deterministic explainable risk rules, alert evaluation, account-link analysis, case grouping, singleton attachment, analyst actions/audit history, dashboard metrics, and a separate evaluation service. See docs/06_backend_development.md for endpoint contracts.
- The latest backend suite has 65 passing tests and one existing Starlette/TestClient deprecation warning recommending `httpx2`. The frontend production build passed. The local Vite proxy and four screens were verified with live API reads. Oxlint exits successfully with four `react(set-state-in-effect)` warnings.
- Phase 9 benchmark: a separate temporary SQLite database generated 100,000 transactions in 60.222 seconds (5,000 customers, 7,000 accounts, 1,000 merchants, 1,000 devices; seed 20261022). Evaluation covered only the first 1,000 transactions and took 33.874 seconds (29.52 transactions/second), creating 1,142 alerts. Final DB size was 58,335,232 bytes; sampled process peak working set was 697,450,496 bytes (~665 MiB); FK check found zero violations. These measurements do NOT establish 100,000-transaction evaluation support. Benchmark DB and truth JSONL were temporary; development data was preserved.
- Alembic head: `a61c9f3d10b2`. Development DB is `backend/risktrace.db`; do not reset/reseed it. Checked-in synthetic truth is `ground_truth/generated/truth_2026.jsonl`; only the separate evaluation service reads labels.
- Known limitations: no authentication or authorization (synthetic analyst ID only); do not expose externally. Concurrent grouping requests are not fully serialized and the schema does not enforce one active case per alert. PostgreSQL compatibility is unverified. Full 100,000-record evaluation is unmeasured. No automated frontend behavior/E2E suite exists; the live state-mutating analyst flow was not verified against the development database.

Recommended next work, if requested:
1. Add frontend behavior/E2E tests using isolated test data and databases.
2. Profile and optimize risk evaluation before measuring larger batches; report actual results only.
3. Review the TestClient deprecation against compatible dependency versions before changing dependencies.
4. Add authentication/authorization and deployment controls before external exposure.

Follow existing project conventions and constraints. Use isolated temporary databases for tests. Keep ground-truth labels out of operational risk detection. Make only requested changes, run the focused verification, and report exact files, commands/results, limitations, and remaining work. Do not claim unmeasured behavior or performance.
```

Current sprint documentation covers actual implementation, verification, benchmark method/results, and outstanding work. The original setup/documentation commits are `9fb2c99` and `68994b0`; preserve the current worktree and re-check its status before making changes.
