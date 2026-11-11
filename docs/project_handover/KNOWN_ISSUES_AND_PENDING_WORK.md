# RiskTrace AI: Known Issues and Pending Work

**Snapshot:** 2026-11-11. Items below are based on inspected repository files, the sole reachable commit (`9fb2c99`), current Git status, and rerun verification; they are not claims about unobserved external discussions.

## Known issues and limitations

1. **No application functionality:** backend is an app shell and frontend is a generic template/counter; no transaction monitoring or analyst workflow exists.
2. **No persistence:** no database file, engine/session, schema, migrations, models, initialization, or seed data.
3. **No business endpoints/integration:** FastAPI exposes framework routes only; React makes no API requests. `GET /` is 404.
4. **No tests collected:** `backend/tests/` only has a placeholder; `python -m pytest -q` prints “no tests ran” and exits 5. No frontend test runner/script or API integration tests are present.
5. **Environment settings are declarative only:** `.env.example` is present, but no `.env` loader or use of `DATABASE_URL`, `RANDOM_SEED`, `API_HOST`, or `API_PORT`.
6. **Design ambiguities remain:** account ID example `ACC--01`, score ranges/weights/priorities, transaction and balance semantics, case/action vocabularies, metric definitions, exception fixture handling, and auth are not specified.
7. **TestClient dependency warning:** manual FastAPI `TestClient` smoke check emits a Starlette deprecation warning for HTTPX usage (message recommends `httpx2`). It did not prevent successful responses. Revisit when adding tests; do not silently change test dependencies without compatibility verification.
8. **Performance unmeasured:** the 100,000-transaction baseline is a requirement only; no generator, index plan, benchmark, or profiling evidence exists.
9. **Portability unverified:** only the inspected Windows workstation was exercised. The portable Node installation is machine-local, outside the repo.
10. **Phase-order gap:** the scaffold (Phase 3) is committed, but no Phase 1 problem-analysis or Phase 2 architecture deliverable is evidenced in this repository. Resume with Phase 1, then Phase 2; Phase 3 is already complete and must not be repeated.
11. **Uncommitted handover documentation:** root `README.md` is modified and `docs/project_handover/` is untracked. These are documentation changes only; application source remains unchanged. They have not been committed or pushed.
12. **Final handoff remains future work:** this package captures the current state; final operational, demo, evaluation, and release documentation depends on implementation.

## Immediate next task (exact)

**Resume at Phase 1 — Problem Analysis.** The supplied 12-phase plan orders Phase 1 and Phase 2 before Phase 3, but repository history contains only the Phase 3 setup commit; no persisted Phase 1 or 2 deliverables were found. Create a Phase 1 artifact (for example `docs/01_problem_analysis.md`) that captures the business problem, users and scenarios, scope/non-scope, requirements and testable acceptance criteria, constraints, assumptions, risks, and open questions from the project brief. Clearly label unconfirmed requirements and do not invent stakeholder decisions. Do not redo the completed Phase 3 setup.

After Phase 1, complete Phase 2 architecture. Then continue to **Phase 4 — Database Design and Data Dictionary**: define all requested core/supporting entities, fields/types, PK/FK relationships/cardinalities, uniqueness/check constraints, indexes, lifecycle/status/disposition vocabularies, monetary precision/currency and time semantics, balance/overdraft/reversal behavior, alert/rule version/evidence fields, audit history, exception isolation, ground-truth separation, and SQLite/PostgreSQL portability. Include an ER diagram and explicitly resolve or record the `ACC--01` ID-format ambiguity. Do not create models or seed records until the design is sufficiently agreed.

## Subsequent work (ordered by supplied phases)

1. Phase 2: design the architecture after Phase 1.
2. Phase 4: define and review the data model/dictionary after Phases 1–2 (Phase 3 setup is already complete).
3. Phase 5: implement the approved relational design, initialization, deterministic synthetic data, validation, and separately held ground truth.
4. Phase 6: implement versioned explainable risk rules, API, alert prioritization, case grouping, analyst actions, and audit trail.
5. Phase 7: add/run backend unit, invariant, and API integration tests, including all five isolated invalid scenarios and reproducibility.
6. Phase 8: replace the generic template with analyst workflows and implement the agreed API integration.
7. Phase 9: add/run frontend behavior/accessibility tests.
8. Phase 10: integrate frontend, backend, and database; validate configuration, CORS, and data flow.
9. Phase 11: test seeded-data-to-analyst-disposition user journeys and evaluation/reporting.
10. Phase 12: update phase documentation, final setup/demo guide, evidence, known issues, and handoff.

Do not treat sequence alone as implementation proof; record tests, results and artifacts when each task actually happens.
