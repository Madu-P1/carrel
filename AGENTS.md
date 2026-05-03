# AGENTS.md

## Project

Carrel is a local-first, source-grounded AI study and research workspace for macOS.
The app uses a Swift/SwiftUI shell, a bundled Preact/Vite frontend, a FastAPI backend,
SQLite with migrations/FTS5/sqlite-vec, and Claude/Ollama provider routing.

## Non-negotiable rules

- Do not commit local user data, database files, uploaded documents, logs, or secrets.
- Do not edit generated files manually. Regenerate API types with `./script/generate-api-types.sh`.
- Keep changes small and independently reviewable.
- Preserve local-first privacy and source-grounding guarantees.
- No silent AI fallbacks. If AI fails or is disabled, the response must say so in metadata/UI.
- Every cited tutor quote must remain verbatim and validated against source chunks.

## Setup

- Python: use `.venv` when available.
- Frontend package manager: `pnpm` via `corepack`.
- Backend entry: `python -m uvicorn main:app --reload`.
- macOS launch: `./script/build_and_run.sh`.

## Required Checks Before Finishing A PR

Run the relevant smallest tests first. For final validation, run as much of this as feasible:

```bash
./script/generate-api-types.sh
corepack pnpm --dir frontend typecheck
corepack pnpm --dir frontend lint
corepack pnpm --dir frontend test
corepack pnpm --dir frontend build:macos
./.venv/bin/python -m ruff check ai services evals tests main.py db.py routes api_models.py benchmarks
./.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
```

## PR Response Format

- Summary
- Files changed
- Tests run with exact commands
- Risks and rollback
- Follow-up work
