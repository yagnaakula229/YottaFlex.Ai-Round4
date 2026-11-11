# RiskTrace AI

RiskTrace AI is a hackathon project for explainable transaction-risk monitoring and analyst case management. Its goal is to prioritize synthetic banking transactions and linked accounts for analyst review using deterministic, transparent risk indicators.

> **Implementation status:** The repository currently contains the Phase 3 project scaffold and the unmodified React/Vite starter screen. The risk-monitoring product capabilities below are requirements, not implemented features.

## Planned capabilities

- Generate deterministic synthetic banking data while preserving relational integrity.
- Detect suspicious transaction patterns and explain risk scores through versioned rules and evidence.
- Prioritize alerts and group related alerts into analyst cases.
- Record analyst decisions and an audit history.
- Keep evaluation ground truth separate from detection inputs and report measurable metrics.

## Architecture and technology

| Tier | Planned technology | Current implementation |
|---|---|---|
| Frontend | React, Vite, JavaScript, CSS | Vite/React starter app; no product UI or API integration |
| Backend | Python, FastAPI, SQLAlchemy 2.x, Pydantic | FastAPI application shell; no domain routes or persistence |
| Database | SQLite; PostgreSQL compatibility considered for the future | No database file, schema, or database connection |

The intended data flow is frontend → FastAPI → relational database. At present, only the standalone starter frontend and FastAPI framework documentation endpoints exist; the tiers are not integrated.

## Repository layout

```text
backend/       FastAPI application shell, dependency manifest, and test location
docs/          Phase documentation and project handover package
frontend/      Independent React + Vite JavaScript application
exports/       Reserved for generated exports
ground_truth/  Reserved for evaluation labels kept separate from detection data
```

## Setup (Windows PowerShell)

### Backend

From the repository root:

```powershell
Set-Location .\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The framework documentation is at <http://127.0.0.1:8000/docs>. No application-specific API routes are implemented yet.

### Frontend

In a second terminal from the repository root:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Vite prints its local URL (normally <http://localhost:5173>).

### Environment configuration

Copy `.env.example` to `.env` for local settings. `.env` is ignored by Git. Automatic environment loading and use of these settings are not implemented yet.

## Documentation

- [Phase 1: Problem Analysis](docs/01_problem_analysis.md)
- [Phase 2: System Architecture](docs/02_system_architecture.md)
- [Phase 3: Project Setup](docs/03_project_setup.md)
- [Project handover package](docs/project_handover/README.md)
- [Project context](docs/project_handover/PROJECT_CONTEXT.md)
- [Project progress](docs/project_handover/PROJECT_PROGRESS.md)
- [Architecture reference](docs/project_handover/ARCHITECTURE_REFERENCE.md)
- [Technical decisions](docs/project_handover/TECHNICAL_DECISIONS.md)
- [Setup and execution](docs/project_handover/SETUP_AND_EXECUTION.md)
- [Known issues and pending work](docs/project_handover/KNOWN_ISSUES_AND_PENDING_WORK.md)
- [AI continuation prompt](docs/project_handover/AI_CONTINUATION_PROMPT.md)

See the handover package for implementation evidence, phase status, and the precise next task.
