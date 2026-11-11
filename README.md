# RiskTrace AI

RiskTrace AI is a transaction risk monitoring and analyst case-management application. It is being developed in phases; this phase establishes the project structure and development environments only.

## Technology stack

- **Frontend:** React with Vite and JavaScript
- **Backend:** Python with FastAPI
- **Database:** SQLite with SQLAlchemy 2.x (database models are not part of this setup phase)

## Project layout

```text
backend/       FastAPI application, tests, and Python dependencies
docs/          Project and phase documentation
frontend/      Independent React + Vite application
exports/       Reserved for generated exports
ground_truth/  Reserved for evaluation ground truth
```

## Setup

### Backend

From `risktrace-ai/backend` in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The FastAPI application is available at <http://127.0.0.1:8000>; interactive API documentation is at <http://127.0.0.1:8000/docs>.

### Frontend

From `risktrace-ai/frontend`:

```powershell
npm install
npm run dev
```

Vite prints the local development URL after startup.

### Environment configuration

Copy `.env.example` to `.env` and adjust local settings as needed. `.env` is ignored by Git; do not commit secrets. Environment loading is not wired into the application in this setup phase.

## Phase status

See [docs/03_project_setup.md](docs/03_project_setup.md) for the phase objective, detailed setup, and verification results.
