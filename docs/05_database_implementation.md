# Phase 5: Database Implementation and Seed Data

**Status:** Phase 5 implemented and verified for the 50-customer / 70-account / 500-transaction demo baseline. Phase 6 later added an additive migration and backend behavior; see [Phase 6](06_backend_development.md) for the current migration head and backend verification.

## 1. Scope and implementation

The approved Phase 4 schema is implemented in SQLAlchemy 2.x using SQLite. Schema changes are managed by Alembic. Monetary values use integer minor units, timestamps use an application UTC type, and SQLite foreign-key enforcement is enabled on every connection.

| Area | Implementation |
|---|---|
| Database connection and UTC type | `backend/app/database/session.py`, `backend/app/database/types.py` |
| Initialization | `backend/app/database/init_db.py`; Alembic upgrade to `head` |
| ORM entities | `backend/app/models/entities.py` and `backend/app/models/__init__.py` |
| Migration | `backend/migrations/versions/0055723a91d0_initial_schema.py` |
| Deterministic generator | `backend/app/services/seed_data.py` |
| Integrity validation | `backend/app/services/data_quality.py` |
| Automated coverage | `backend/tests/test_database_phase5.py` |
| Separate evaluation labels | `ground_truth/generated/truth_2026.jsonl` |

The 16 implemented entities are Customer, Account, Merchant, Device, Transaction, TransferLink, RiskRule, Alert, Case, AnalystAction, KYCProfile, CustomerAccount, CustomerDevice, CaseAlert, ExceptionRecord, and AuditEvent. Ground truth is a separate JSONL artifact, not a database entity.

## 2. Schema and integrity

- Every entity has an application-generated text primary key. ORM guards and SQLite migration triggers prevent primary-key changes.
- Foreign keys use `ON DELETE RESTRICT`; SQLite connections set `PRAGMA foreign_keys=ON`.
- SQLAlchemy relationships implement the documented ownership/device/case associations and transaction/account relationships. Account ownership is effective-dated.
- Transaction reversal is an optional one-to-one self-relationship: the unique nullable `reversal_of_transaction_id` references the original transaction.
- Transfer legs use composite account/transaction foreign keys. Equal positive minor-unit amounts and USD are checked in the database; ledger direction and reconciliation are checked by the validator.
- AnalystAction and AuditEvent are append-only, guarded by ORM listeners and SQLite update/delete triggers. Active or referenced RiskRule versions and all public primary keys are immutable.
- Check constraints cover status enums, amount direction/non-negativity, balance equations, identifiers' key uniqueness, timestamp ordering, and required fields. Cross-row ownership intervals, ledger continuity, transfer reconciliation, priority aggregation, and action chronology are validated in the service layer.
- ExceptionRecord has no FK to its invalid polymorphic subject. AuditEvent's `(entity_type, entity_id)` pair is informational, not an FK.
- The initial migration creates all 16 tables, indexes, constraints, and SQLite integrity triggers. It is intentionally retained as the Phase 5 history; Phase 6 extends the allowed rule-key set through a forward migration.

## 3. Seed generation and truth isolation

The generator uses a local `random.Random(seed)` with default seed `20261022`, fixed UTC timestamps from 2026-01-01 through 2026-10-22, deterministic IDs, master-before-dependent insertion, and batched transaction inserts. The CLI accepts counts for customers, accounts, merchants, devices, transactions, and alerts. It refuses to seed a non-empty database.

The validated default run produced:

| Record type | Count |
|---|---:|
| Customers / accounts / merchants / devices | 50 / 70 / 20 / 30 |
| Effective-dated customer-account links / customer-device links | 81 / 30 |
| Posted transactions | 500 |
| Reconciled transfer links | 25 |
| Versioned risk rules / representative seed alerts | 5 / 10 at the original Phase 5 baseline |
| Cases / case-alert links / analyst actions / audit events | 1 / 10 / 1 / 2 |
| Quarantined exception records | 5 |
| Ground-truth JSONL records | 500 |

The five required invalid candidates (closed-account transaction, unauthorized negative balance, mismatched transfer legs, orphan alert, and disposition before alert) are represented only as quarantined ExceptionRecord payloads. Invalid operational Transaction, TransferLink, Alert, or AnalystAction rows are not created.

Ground truth is written separately to `ground_truth/generated/truth_2026.jsonl`, with one record per transaction and deterministic labels/pattern metadata. No seed or validation path joins truth labels into operational records. **The 10 seeded alerts are representative examples, not detector output**; detection and evaluation metrics are not implemented in Phase 5.

The output JSONL SHA-256 for the verified default run was:

`2480cc93e270ab7a59449877144d743d4074b4d673f2f026ca60bda33cb92ba5`

The target-size configuration (5,000 customers, 7,000 accounts, 100,000 transactions, 1,000 alerts) passed parameter validation, but a full 100,000-transaction generation/benchmark has not been run.

## 4. Setup and commands (Windows PowerShell)

From the repository root:

```powershell
Set-Location .\backend
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m app.services.seed_data
```

The default database is `backend/risktrace.db` and the default truth file is `ground_truth/generated/truth_2026.jsonl`. Both paths can be overridden with `DATABASE_URL`, `--database-url`, and `--ground-truth`. The `.env` file is not automatically loaded by the current application; set environment variables in the shell explicitly.

To generate a different dataset size in a new/empty database:

```powershell
python -m app.services.seed_data --customers 5000 --accounts 7000 --merchants 20 --devices 30 --transactions 100000 --alerts 1000
```

`--reset` is an explicit local SQLite operation and refuses to remove the database when analyst-action or audit history exists. It is not a production reset/migration strategy. Do not remove or reset the database as part of routine startup.

To run tests:

```powershell
python -m pytest -q
```

## 5. Verification evidence

Commands were run from `backend/` with the existing virtual environment:

| Check | Result |
|---|---|
| `python -m alembic upgrade head` using the local SQLite default | Passed; initialized `risktrace.db` |
| Default `python -m app.services.seed_data --database-url sqlite:///./risktrace.db --ground-truth ..\ground_truth\generated\truth_2026.jsonl` | Passed; generated the counts above and validated FK, ownership, ledger, transfer, alert/case priority, and chronology consistency |
| `python -m pytest -q tests\test_database_phase5.py` | Passed: 8 tests |
| `SeedConfig(customers=5000, accounts=7000, merchants=20, devices=30, transactions=100000, alerts=1000).validate()` | Passed; configuration accepted (data at this scale not generated) |

The Phase 5 tests cover all 16 tables and SQLite FK/integrity checks, ORM relationships, UTC round trips and naive-input rejection, invalid amount/transfer/orphan-alert constraints, exception isolation, seed consistency, fixed-seed database/truth reproducibility, and ORM plus SQLite enforcement of append-only and immutable records. The Phase 6 suite also verifies a populated Phase 5 database upgrades without losing seed records; see [Phase 6 verification](06_backend_development.md).

## 6. Limitations and next work

- The full 100,000-transaction workload has not been generated, benchmarked, or profiled.
- The Phase 5 fixture baseline has five versioned rules and representative alerts; Phase 6 adds the sixth rule and implements the detector, business APIs, and isolated metrics. See [Phase 6](06_backend_development.md) for the current behavior.
- There is no frontend integration or database portability test against PostgreSQL.
- SQLite migration triggers provide direct-SQL immutability protections; equivalent PostgreSQL triggers have not been implemented.
- `risktrace.db` is a local runtime artifact and is excluded from Git. Generated ground truth is a separate synthetic evaluation artifact; confirm repository retention policy before sharing externally.
- The schema may be extended in later phases only through reviewed model changes and new Alembic migrations; do not edit the initial migration after it has been published/shared.

Phase 5 is complete for the implemented and tested small baseline. The Phase 5 baseline above remains historical evidence; the current local schema revision and backend implementation status are recorded in [Phase 6](06_backend_development.md).
