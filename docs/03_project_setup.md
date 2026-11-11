# Phase 3: Project Setup

## 1. Phase objective

Establish an independent frontend and backend project structure, install the development dependencies, document local setup, and verify that both development environments start. This phase intentionally does not implement business logic, database models, synthetic data, risk rules, or dashboard features.

## 2. Technology stack and reasons

- **React + Vite + JavaScript:** React provides the UI foundation; Vite supplies a lightweight development server and build tooling. JavaScript is used as requested.
- **Python + FastAPI:** FastAPI provides a small, typed Python web application foundation and built-in OpenAPI documentation.
- **SQLite + SQLAlchemy 2.x:** SQLite is a simple local database choice; SQLAlchemy 2.x is the planned persistence toolkit. Models and database integration are deferred.
- **Pydantic:** Supports validation and data schemas for later API work.
- **pytest + HTTPX:** Provide a test runner and an HTTP client for later backend tests.

## 3. Folder structure

```text
risktrace-ai/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── database/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── venv/                 (local; excluded from Git)
├── docs/
│   └── 03_project_setup.md
├── exports/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── data/
│   │   ├── pages/
│   │   └── services/
│   ├── package.json
│   └── vite.config.js
├── ground_truth/
├── .env.example
├── .gitignore
└── README.md
```

## 4. Python setup instructions

From the `backend` directory, create and activate the local virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use the interpreter directly:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 5. Frontend setup instructions

From the `frontend` directory, install npm packages and start the Vite development server:

```powershell
npm install
npm run dev
```

Node.js 26.13.0 was installed as a portable per-user runtime and added to the user `PATH`. Restart VS Code so new integrated terminals inherit the updated path.

## 6. Installation commands

Backend dependencies are declared in `backend/requirements.txt`:

```powershell
python -m pip install -r requirements.txt
```

Frontend dependencies are declared in `frontend/package.json`:

```powershell
npm install
```

## 7. How to start the backend

From `backend`, activate `venv` and run:

```powershell
uvicorn app.main:app --reload
```

The setup-only FastAPI application exposes the framework's default documentation endpoints. No domain API routes are implemented.

## 8. How to start the frontend

From `frontend`, run:

```powershell
npm run dev
```

Open the URL printed by Vite in the terminal.

## 9. Environment configuration

Copy `.env.example` to `.env` for local configuration. The sample contains `APP_NAME`, `DATABASE_URL`, `RANDOM_SEED`, `API_HOST`, and `API_PORT`. `.env` is excluded by `.gitignore`; do not store real credentials in the example file. Automatic `.env` loading is not configured at this stage.

## 10. Verification results

- Python 3.13.2 created the `backend/venv` environment; all six declared backend dependencies installed successfully.
- Backend imports succeeded: FastAPI 0.162.4, Uvicorn 0.54.0, SQLAlchemy 2.1.8, Pydantic 2.14.3, pytest 8.4.2, and HTTPX 0.28.1. `pip check` reported no broken requirements.
- Node.js 26.13.0 and npm 11.20.0 were used. Frontend packages installed successfully; npm reported 0 vulnerabilities.
- `npm run build` completed successfully. The Vite development server returned HTTP 200 and served the React root page.
- Uvicorn started the FastAPI application; `/docs` returned HTTP 200 and served Swagger UI.
- Frontend and backend have independent manifests and can be installed and started from their respective directories.
- Required project directories, `.env.example`, `.gitignore`, and documentation files are present.

## 11. Issues encountered and resolutions

- The `py` launcher was unavailable, so Python commands use the installed `python` executable.
- Node.js/npm were initially unavailable. The Node MSI required an administrator prompt, so Node.js 26.13.0 was installed as a portable per-user runtime and added to the user `PATH`.
- The first Vite scaffold command treated an absolute Windows path as a package name. The generated scaffold was moved into `frontend/`, its incidental workspace-root lockfile was removed, and the frontend was installed and verified from its project directory.

## 12. Phase completion status

Complete. The application structure and development environments are set up and verified. No database models, business APIs, synthetic data, risk rules, or product UI features were implemented.
