# RiskTrace AI: Known Issues and Pending Work

**Snapshot:** 2026-11-11 (final completion sprint). Verified against the application, benchmark evidence, tests, and handover documents. No commit or push was made.

The application has 16 ORM entities: Customer, Account, Merchant, Device, Transaction, TransferLink, RiskRule, Alert, Case, AnalystAction, KYCProfile, CustomerAccount, CustomerDevice, CaseAlert, ExceptionRecord, and AuditEvent. Phase 6 added the rule key `linked_suspicious` through migration `a61c9f3d10b2`; it did not add or remove an entity.

## Known issues and limitations

1. **Frontend behavior-test gap:** Overview, Transactions, Alerts, and Cases are implemented and connected to the FastAPI operational API. The Vite proxy and live data reads were verified, and the production build passes. No automated frontend behavior/E2E test suite is configured; the live read-only integration check did not perform a state-mutating analyst action against the development database.
2. **Environment loading:** `.env.example` is provided, but the application does not automatically load `.env`. Configure environment variables in the backend process.
3. **Evaluation scale remains unverified beyond a sample:** An isolated temporary benchmark generated 5,000 customers, 7,000 accounts, 1,000 merchants, 1,000 devices, and 100,000 transactions. Generation took 60.222 seconds. Risk evaluation measured only the first 1,000 transactions: 33.874 seconds, 29.52 transactions/second, and 1,142 alerts created. Do not extrapolate this rate or claim that all 100,000 transactions were evaluated.
4. **Database portability:** SQLite is verified; PostgreSQL compatibility and dialect-specific trigger equivalents are not.
5. **Authentication and deployment:** analyst actions use synthetic identity `analyst-demo-001` without authentication. Do not expose the API externally; authentication, authorization, transport security, and deployment controls are pending.
6. **Risk calibration:** six deterministic rules, contributions, and thresholds are demo policy. They are explainable and reproducible but are not calibrated or evidence of real-world detection quality.
7. **Evaluation scope:** metrics use the checked-in synthetic transaction labels. They are not representative of a production population, and no real-world validation or train/validation evaluation has occurred.
8. **Testing warning:** Latest full `python -m pytest -q` passes 65 tests, but emits one Starlette deprecation warning recommending `httpx2` for `TestClient`. No dependency migration has been performed. Oxlint exits successfully but reports four `react(set-state-in-effect)` warnings in the four page components; no refactor was made.
9. **Case grouping concurrency:** singleton attachment is sequentially idempotent and uses the existing unique `(case_id, alert_id)` constraint. Concurrent grouping requests are not fully serialized, and the schema does not enforce one active-case association per alert.
10. **Reset caution:** seed generation targets an empty database; do not rerun it against the populated development database. The explicit local reset path protects analyst/audit history and is not a production reset strategy.
11. **Benchmark measurement limits:** Windows process working set was sampled during the benchmark; the observed peak was 697,450,496 bytes (~665 MiB), not an isolated application allocation measurement. Final SQLite database size was 58,335,232 bytes; temporary truth JSONL size was 35,181,667 bytes. The benchmark used a temporary database and truth file; development data was preserved.
12. **Worktree:** existing application and documentation changes are preserved and remain uncommitted. No commit or push was made.

## Verified current database state

- Alembic revision: `a61c9f3d10b2 (head)`.
- Records preserved through the additive upgrade: 500 transactions, 6 rules, 10 alerts, 1 case, 1 analyst action, and 2 audit events.
- The new active rule is `RUL-linked_suspicious-V01`.
- `PRAGMA foreign_key_check` returned no violations; both risk-rule protection triggers are present.
- Phase 6 tests use isolated temporary SQLite databases and do not reset the development database.
- Latest backend suite: 65 passed (one Starlette/TestClient deprecation warning). Alembic check reported no new upgrade operations; compileall, pip check, and diff check passed in the consolidated backend verification. The frontend production build passed. Latest local DB checks are documented in the earlier handover evidence; the temporary benchmark DB had 100,000 transactions and zero foreign-key violations.

## Recommended next work (not part of the completed sprint)

1. Add automated frontend behavior tests for loading/error/empty states, filters, and case review/disposition. Keep state-mutating tests isolated from `backend/risktrace.db`.
2. Profile/optimize risk evaluation before attempting a complete 100,000-transaction evaluation. Preserve the measured generator and evaluation timings as separate measures.
3. Resolve the Starlette/TestClient deprecation only after checking compatible dependency versions and behavior; do not make a dependency change solely to silence the warning.
4. Add authentication/authorization and deployment controls before any non-local use.
5. Verify PostgreSQL compatibility only if PostgreSQL becomes a target.

The current demo implementation is complete for its documented local scope; the items above are follow-up hardening, not evidence that the benchmark, frontend, or backend implementation failed.

Do not treat sequence alone as implementation proof. Record files, commands, results, and limitations after each phase.
