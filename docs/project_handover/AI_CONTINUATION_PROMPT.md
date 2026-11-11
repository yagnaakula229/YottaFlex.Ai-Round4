# Reusable AI Continuation Prompt

Copy the prompt below into a new coding assistant while the `YottaFlex.Ai-Round4` repository is open as the workspace:

```text
You are continuing RiskTrace AI in the current VS Code workspace.

Before doing work:
1. Read every document in docs/project_handover/, including the handover README.
2. Read the root README.md, docs/01_problem_analysis.md, docs/02_system_architecture.md, and docs/03_project_setup.md.
3. Inspect the actual repository tree and the relevant source, configuration, and tests. Treat documentation as a snapshot, not proof that code exists.
4. Check `git status --short --branch` and inspect existing diffs before modifying anything. Preserve user changes and Git history. Do not commit or push unless explicitly asked.
5. Re-verify the reported phase state and tests if the code has changed since the documented snapshot.

Exact next task at this handover snapshot:
Continue Phase 4 — Database Design and Data Dictionary. Phases 1 and 2 documentation artifacts were created from the supplied hackathon problem statement in `docs/01_problem_analysis.md` and `docs/02_system_architecture.md`; Phase 3 setup is already implemented. Do not recreate those documents or the setup. Review the Phase 2 proposed architecture and resolve the choices that affect the schema. Create a Phase 4 data dictionary and reviewed relational design covering all core/supporting entities; fields/types; keys, cardinalities, constraints and indexes; lifecycle/disposition vocabularies; currency, amount precision and time semantics; balance, overdraft and reversal behavior; rule/version/evidence data; audit history; ground-truth separation; exception isolation; and SQLite/PostgreSQL portability. Include an ER design and resolve or explicitly document the ambiguous `ACC--01` example. Do not implement SQLAlchemy models, migrations, database initialization, or seed data yet.

Project rules:
- Continue from the exact next incomplete task in docs/project_handover/PROJECT_PROGRESS.md; respect the supplied phase order. Phase 3 setup is already complete; do not recreate it or invent completed features.
- Follow the required three-tier architecture: React + Vite + JavaScript/CSS, Python + FastAPI + SQLAlchemy 2.x + Pydantic, SQLite for the hackathon (PostgreSQL compatibility is a future consideration).
- Preserve existing implementations and user changes. Do not overwrite or delete working files; ask before destructive changes.
- Keep ground-truth labels out of all detector inputs and paths. Keep deliberately invalid scenarios isolated from valid operational data.
- Use deterministic, explainable risk rules and preserve rule version, evidence, triggering transaction, score contribution, timestamp, and priority.
- Maintain phase documentation after each phase; record actual files, implementation, commands, test outcomes, pending work, and issues.
- Run the smallest relevant tests/builds before claiming success. Clearly distinguish passing checks from missing tests and failures. Never invent results.
- Avoid duplicate functionality and unrelated changes. Do not add secrets, commit, or push without authorization.

At the end, summarize changed files, design/implementation decisions, commands/tests with exact outcomes, unresolved questions, and the next task. Update the handover tracker so the next developer can continue without this chat.
```

The exact next task above is based on the inspected repository snapshot dated 2026-11-11: one reachable commit (`9fb2c99`, the Phase 3 setup commit), plus uncommitted documentation changes for Phases 1, 2, and 12. Application source is unchanged. Re-check the progress tracker and repository before following the task if later work has landed.
