# RiskTrace AI

RiskTrace AI is a hackathon application for explainable transaction-risk monitoring and analyst case management. It uses deterministic, versioned rules to identify transaction patterns, prioritize alerts, group related alerts into cases, and preserve analyst decisions. Ground-truth labels are kept separate from operational risk evaluation.


<img width="6148" height="9045" alt="diagram (1)" src="https://github.com/user-attachments/assets/a3d460ad-877d-4699-a6d9-89870306dcf6" />



## Current implementation

| Tier | Technology | Status |
|---|---|---|
| Frontend | React, Vite, JavaScript | Analyst dashboard integrated with the FastAPI operational API through a Vite development proxy. |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Pydantic | Phase 6 APIs, deterministic risk evaluation, case/action services, dashboard metrics, and isolated evaluation endpoint are implemented. |
| Database | SQLite and Alembic | 16 ORM entities, deterministic small seed baseline, and additive Phase 6 migration implemented; current local database is at `a61c9f3d10b2`. |

The backend suite has 65 passing tests (one existing Starlette/TestClient deprecation warning). The seeded development database contains 500 transactions and was preserved during verification. A separate temporary SQLite benchmark generated 100,000 transactions; risk evaluation was measured only for the first 1,000, so full-dataset evaluation performance is not established. PostgreSQL, authentication, and production deployment remain unverified.

The frontend includes Overview, Transactions, Alerts, and Cases screens, connected to the operational API through the Vite `/api` proxy. It displays backend-provided data and does not connect to SQLite or expose ground-truth labels. Analyst identity is a synthetic demo identity, not authentication.

## Repository layout

```text
backend/       FastAPI application, database, migrations, services, and tests
docs/          Phase documentation and project handover package
frontend/      Independent React + Vite JavaScript application
exports/       Reserved for generated exports
ground_truth/  Separate synthetic evaluation labels
```

## Setup (Windows PowerShell)

### Backend

From the repository root:

```powershell
Set-Location .\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

For a **new empty database only**, generate the deterministic baseline and separate truth file with:

```powershell
python -m app.services.seed_data
```

Do not rerun seeding against a populated database. The default local database path is `backend/risktrace.db`; generated database files are local runtime data. The API documentation is available at <http://127.0.0.1:8000/docs>.

Run backend tests from `backend/`:

```powershell
python -m pytest -q
```

### Frontend

Start the backend first in one terminal. Then, from the repository root, start the frontend in a second terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite prints its local URL (normally <http://localhost:5173>). During development, `/api` requests are proxied to `http://127.0.0.1:8000`. Set `VITE_API_BASE_URL` to an API base URL ending in `/api` when using a separately hosted backend.

Build the production frontend from `frontend/` with `npm run build`.

### Environment configuration

Copy `.env.example` to `.env` for local settings; `.env` is ignored by Git. The backend does not automatically load `.env`; provide settings through the process environment.

## Documentation

- [Phase 1: Problem Analysis](docs/01_problem_analysis.md)
- [Phase 2: System Architecture](docs/02_system_architecture.md)
- [Phase 3: Project Setup](docs/03_project_setup.md)
- [Phase 4: Database Design and Data Dictionary](docs/04_database_design.md)
- [Phase 5: Database Implementation and Seed Data](docs/05_database_implementation.md)
- [Phase 6: Backend Development](docs/06_backend_development.md)
- [Project handover package](docs/project_handover/README.md)
- [Project progress](docs/project_handover/PROJECT_PROGRESS.md)
- [Technical decisions](docs/project_handover/TECHNICAL_DECISIONS.md)
- [Known issues and pending work](docs/project_handover/KNOWN_ISSUES_AND_PENDING_WORK.md)
- [AI continuation prompt](docs/project_handover/AI_CONTINUATION_PROMPT.md)

## Benchmark evidence

The Phase 9 completion-sprint benchmark used a temporary database and temporary truth JSONL file; neither the development database nor checked-in truth data was used. With the deterministic seed `20261022`, generation of 5,000 customers, 7,000 accounts, 1,000 merchants, 1,000 devices, and 100,000 transactions took **60.222 seconds**. The first 1,000 transactions were then evaluated in **33.874 seconds** (**29.52 transactions/second**). The database contained 100,000 transactions and 2,142 alerts after evaluation, `PRAGMA foreign_key_check` reported zero violations, and the final database size was **58,335,232 bytes**. A Windows process working-set sampler observed a peak of **697,450,496 bytes** (~665 MiB); this is process-level sampled memory, not an isolated application allocation measurement. The temporary truth file was 35,181,667 bytes.

This is a measured generation result and a 1,000-transaction evaluation sample, **not** a 100,000-transaction evaluation benchmark or a claim of full-scale support. Evaluation performs per-transaction database lookups and account-link analysis; larger evaluation batches require further profiling and optimization.

## Five-minute demo

1. Start the backend and frontend using the commands above.
2. Open the Vite URL and show Overview metrics, priority distribution, and account risk distribution.
3. Open Transactions, inspect a transaction, and demonstrate posted-transaction risk evaluation.
4. Open Alerts and show priority/status filters, rule matches, and evidence.
5. Open Cases, show linked alerts and action/audit history; start review before recording a disposition.

Use synthetic local data only. Do not expose the unauthenticated demo API outside a trusted local environment.
