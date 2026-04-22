# Einstein Tutor

Local-first, source-grounded AI study and research workspace for macOS. Drop in PDFs, notes, slides. Get a concept graph, SRS cards, and grounded tutor answers that cite back to page-level spans.

Architecture overview: [CLAUDE.md](CLAUDE.md). Design system: [DESIGN.md](DESIGN.md).

## Quick start — macOS app

```bash
./script/build_and_run.sh
```

Builds the Swift shell + Vite frontend bundle, starts the FastAPI backend on `127.0.0.1:8000`, and launches `Einstein.app`. Use `--frontend legacy` for the pre-PR-E8 bundle.

## Quick start — backend only

```bash
python3 -m uvicorn main:app --reload
# then http://127.0.0.1:8000
```

Useful for iterating on routes, ingestion, or the legacy web shell without rebuilding the Swift app.

## Configuration

Copy `.env.example` to `.env` and fill in:

- `ANTHROPIC_API_KEY` — required for grounded tutor answers via Claude.
- `EINSTEIN_AI_PROVIDER` — `auto` (default), `claude`, `ollama`, or `off`. Picks the LLM backend used by `ai/providers.py`. Ollama runs the Einstein tier on `llama3.2:3b` (fast) and `llama3.1:8b` (balanced) by default.
- `EINSTEIN_BASE_DIR`, `EINSTEIN_DB_PATH`, `EINSTEIN_SCHEMA_PATH` — optional path overrides.

Never commit `.env`. The gitignore excludes it; treat any past leak as a key to rotate.

## Data locations

- Uploads: `data/uploads/` (ignored).
- SQLite DB: `data/einstein_tutor.db` (ignored).
- Structured logs: `data/logs/` (ignored).
- Vector retrieval uses `sqlite-vec` + local `fastembed`. First vector-enabled run downloads `BAAI/bge-small-en-v1.5` to `~/.cache/fastembed/` (~120 MB once).

## Verify chain

Run before landing anything. Full list in [CLAUDE.md](CLAUDE.md#verify-chain-run-before-any-merge):

```bash
./script/generate-api-types.sh
./node_modules/.bin/tsc --noEmit          # inside frontend/
./node_modules/.bin/vitest run            # inside frontend/
./.venv/bin/python -m ruff check .
./.venv/bin/python -m unittest -v
```

Every PR lands green or it does not land.
