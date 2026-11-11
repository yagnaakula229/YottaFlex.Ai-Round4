# RiskTrace AI: Setup and Execution

**Verified environment snapshot:** Windows, PowerShell, Python 3.13.2, Node.js 26.13.0, npm 11.20.0. Other compatible versions/platforms have not been verified here.

Run commands from the cloned repository root `YottaFlex.Ai-Round4/`. Backend and frontend have independent dependency manifests.

## Prerequisites

- Git.
- Python 3.13 or a compatible Python 3 installation with `python` on `PATH`.
- Node.js/npm compatible with the locked Vite toolchain.
- PowerShell on Windows; translate activation/path commands for other shells.
- The current workstation has a per-user portable Node runtime at `%LOCALAPPDATA%\RiskTraceAI\node-v26.13.0-win-x64`. That location is machine-specific, is not part of the repository, and must not be assumed on a new machine. Install Node.js normally or use another managed runtime there.

## Backend environment and installation

From the repository root:

```powershell
Set-Location .\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell prevents venv activation, call the environment executable directly:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Frontend installation

In another terminal:

```powershell
Set-Location .\frontend
npm install
```

`frontend/package-lock.json` is committed; prefer `npm ci` for a clean, lockfile-based install in CI.

## Environment variables

The repository root `.env.example` contains:

```dotenv
APP_NAME=RiskTrace AI
DATABASE_URL=sqlite:///./risktrace.db
RANDOM_SEED=20261022
API_HOST=127.0.0.1
API_PORT=8000
```

For local use, copy it without overwriting an existing `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

`.env` is ignored by Git. **The current application does not load `.env` or consume these settings.** Do not add secrets to the example file.

## Database initialization and seed data

From `backend/` with the virtual environment active:

```powershell
python -m alembic upgrade head
python -m app.services.seed_data
```

The migration creates the 16-entity SQLite schema; the seed command creates the default 50-customer / 70-account / 500-transaction demo dataset and writes separate transaction-level truth to `ground_truth/generated/truth_2026.jsonl`. By default the local database is `backend/risktrace.db` (Git-ignored). Pass `--database-url` and `--ground-truth` to override paths. `.env` is not automatically loaded; set `DATABASE_URL` in the shell or use explicit CLI arguments.

The generator refuses to seed a non-empty database. `--reset` is an explicit local SQLite operation and refuses to remove analyst/audit history. Do not use it as an automatic startup or production reset mechanism.

## Start the backend

From `backend/`, with its virtual environment active:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected framework URLs:

- <http://127.0.0.1:8000/docs> — Swagger UI (verified HTTP 200)
- <http://127.0.0.1:8000/redoc> — ReDoc
- <http://127.0.0.1:8000/openapi.json> — generated framework schema (verified HTTP 200)
- <http://127.0.0.1:8000/health> — basic health endpoint
- `GET /` is not implemented.

The Phase 6 API routes include transaction, account-link, alert, risk-evaluation, case/action, dashboard, and evaluation endpoints; see [Phase 6 backend development](../06_backend_development.md) for exact methods and paths. The frontend is not connected to these routes.

## Start the frontend

From `frontend/`:

```powershell
npm run dev
```

Vite normally prints <http://localhost:5173>. If occupied, Vite may select another port and report it. Frontend and backend are not connected; no API proxy/base URL has been configured.

## Tests and verification

From `backend/`:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m pip check
python -m pytest -q
```

Only seed a **new empty database** with `python -m app.services.seed_data`; the generator intentionally refuses to overwrite a populated database. Verified Phase 6 results: Alembic reports `a61c9f3d10b2 (head)`, `pip check` reported no broken requirements, and `pytest -q` passed 19 tests with one Starlette HTTPX/TestClient deprecation warning. The migration preserved the existing 500-transaction database. The 100,000-transaction dataset has not been generated or benchmarked.

From `frontend/`:

```powershell
npm run lint
npm run build
```

Both passed in the inspected workspace. `npm run build` is a production-build check, not a UI behavior test.

Backend import/version check:

```powershell
python -c "import fastapi, uvicorn, sqlalchemy, pydantic, pytest, httpx; print('imports ok')"
```

A FastAPI `TestClient` smoke check and automated tests exercise the implemented API routes. The suite emitted a Starlette deprecation warning recommending `httpx2` instead of HTTPX for `TestClient`; dependency migration remains for Phase 7. Root `/` is not implemented.

## Troubleshooting

- **`py` not found:** use `python`; the verified workstation did not have the Windows Python launcher.
- **`npm` not found:** install Node.js/npm on this machine. The portable runtime used during setup is outside the repo and must not be copied into Git.
- **Backend import fails from repository root:** switch to `backend/` before running `uvicorn app.main:app`.
- **PowerShell activation is blocked:** invoke `backend\venv\Scripts\python.exe` directly or follow local policy to enable activation.
- **Port occupied:** choose an available port and update the browser URL. No app configuration currently reads `API_PORT`.
- **Database migration fails:** run the Alembic command from `backend/` with the project virtual environment active; set `DATABASE_URL` or pass `--database-url` if using a non-default location.
- **Seed refuses to run:** it does not overwrite a non-empty database. Use a new empty database, or review the explicit local `--reset` guard; it will refuse to erase analyst/audit history.
- **Root endpoint unavailable:** `/` is not implemented; use `/health` or `/docs`.
