# Rebuild Carrel After a System Reset

This guide rebuilds Carrel from the GitHub repository after a clean macOS reset. It restores the app code, dependencies, database schema, frontend bundle, and macOS shell. Local study data and secrets need to be restored separately from backup.

## What the Repo Restores

- FastAPI backend in `main.py`, `routes/`, `services/`, and `ai/`
- SQLite schema and migrations in `migrations/`
- Preact/Vite frontend in `frontend/`
- Swift macOS shell in `macos-app/`
- test, eval, and benchmark harnesses

## What Needs a Separate Backup

- `.env` and API keys
- `data/einstein_tutor.db`
- `data/uploads/`
- any local logs or generated reports you care about

The repo intentionally ignores those local data files.

## Prerequisites

Install these first:

- macOS 14 or newer
- Xcode Command Line Tools: `xcode-select --install`
- Python 3.11 or 3.12
- one JavaScript runner: `bun`, `pnpm`, `corepack pnpm`, or `npm`
- GitHub access to `https://github.com/Madu-P1/carrel`

Optional:

- Ollama, if you want a local LLM fallback
- Anthropic API key, if you want Claude-backed tutor answers

## Fresh Checkout

```bash
git clone https://github.com/Madu-P1/carrel.git
cd carrel
```

If GitHub CLI is installed and authenticated, this equivalent form also works:

```bash
gh repo clone Madu-P1/carrel
cd carrel
```

## Python Environment

Create and install the backend environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt
```

## Environment File

Create `.env` from the template and fill in the values you have:

```bash
cp .env.example .env
```

Minimum useful options:

```bash
ANTHROPIC_API_KEY=...
EINSTEIN_AI_PROVIDER=auto
```

For an offline or no-key rebuild, use:

```bash
EINSTEIN_AI_PROVIDER=off
```

For Ollama:

```bash
EINSTEIN_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

## Restore Local Data

If you backed up local data, restore these paths before first launch:

```text
data/einstein_tutor.db
data/uploads/
```

If you do not restore a database, Carrel creates a fresh one at first backend startup and applies migrations automatically.

## Frontend Dependencies

Use pnpm when you want to match CI exactly:

```bash
cd frontend
pnpm install --frozen-lockfile
cd ..
```

If you only have Bun and are doing local app work:

```bash
cd frontend
bun install
cd ..
```

## Build and Launch the macOS App

From the repo root:

```bash
./script/build_and_run.sh
```

The script builds the Vite frontend bundle, builds the Swift shell, starts FastAPI on `127.0.0.1:8000`, and launches `dist/EinsteinDesktop.app`.

Useful variants:

```bash
./script/build_and_run.sh --verify
./script/build_and_run.sh --logs
```

## Backend-Only Development

```bash
. .venv/bin/activate
python -m uvicorn main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Frontend Development Server

In one terminal:

```bash
. .venv/bin/activate
python -m uvicorn main:app --reload
```

In another terminal:

```bash
cd frontend
pnpm dev
```

Then open:

```text
http://localhost:5173
```

## Verification

Run the same core checks CI runs:

```bash
. .venv/bin/activate
ruff check .
mypy --config-file mypy.ini
python -m unittest \
  tests.test_ai_router \
  tests.test_einstein_tutor \
  tests.test_evals_runner \
  tests.test_phase0_foundation \
  tests.test_phase0_batch_b \
  tests.test_tutor_grounded \
  -v
```

Frontend:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

Smoke eval:

```bash
python -m evals.run_evals --suite smoke --mode smoke
```

## Common Recovery Notes

- If port `8000` is already in use, stop the old backend process before launching.
- If frontend install fails in CI mode, update `frontend/pnpm-lock.yaml` with `pnpm install`.
- If the tutor has no model access, set `EINSTEIN_AI_PROVIDER=off` to keep the app usable.
- First vector-enabled ingestion can download the `BAAI/bge-small-en-v1.5` embedding model to `~/.cache/fastembed/`.
- The app is now called Carrel, but some system-level names still use `EinsteinDesktop` and `einstein_tutor.db` by design.
