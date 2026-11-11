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

## Database initialization

There is no database initialization command yet: no SQLAlchemy engine/session, models, migrations, seed-data generator, or database file exists. Do not expect `risktrace.db` to be created by startup.

## Start the backend

From `backend/`, with its virtual environment active:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected framework URLs:

- <http://127.0.0.1:8000/docs> — Swagger UI (verified HTTP 200)
- <http://127.0.0.1:8000/redoc> — ReDoc
- <http://127.0.0.1:8000/openapi.json> — generated framework schema (verified HTTP 200)
- `GET /` currently returns 404; no root or health endpoint exists.

## Start the frontend

From `frontend/`:

```powershell
npm run dev
```

Vite normally prints <http://localhost:5173>. If occupied, Vite may select another port and report it. Frontend and backend are not connected; no API proxy/base URL has been configured.

## Tests and verification

From `backend/`:

```powershell
python -m pip check
python -m pytest -q
```

At the snapshot, `pip check` passed. Pytest reported “no tests ran” and returned exit code 5 because `backend/tests/` has no test modules; this is **not** a passing test suite.

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

A manual FastAPI `TestClient` smoke check returned 200 for `/docs` and `/openapi.json`; `/` returned 404. It emitted a Starlette deprecation warning recommending `httpx2` instead of HTTPX for `TestClient`. No automated API integration tests are present.

## Troubleshooting

- **`py` not found:** use `python`; the verified workstation did not have the Windows Python launcher.
- **`npm` not found:** install Node.js/npm on this machine. The portable runtime used during setup is outside the repo and must not be copied into Git.
- **Backend import fails from repository root:** switch to `backend/` before running `uvicorn app.main:app`.
- **PowerShell activation is blocked:** invoke `backend\venv\Scripts\python.exe` directly or follow local policy to enable activation.
- **Port occupied:** choose an available port and update the browser URL. No app configuration currently reads `API_PORT`.
- **No database created:** expected until database implementation phase.
- **Pytest exit 5:** currently expected when no test files are collected; add tests before treating pytest as a passing verification.
- **Root endpoint 404:** expected until a product/root/health endpoint is implemented.
