# Einstein Tutor

This workspace now includes a working local app:

- FastAPI backend
- SQLite persistence
- TXT/MD/PDF ingestion
- The original dashboard UI wired to live local endpoints
- Database schema and integration templates based on the original planning docs

## Quick Start

1. Start the server from the repo root:
   `python3 -m uvicorn main:app --reload`
2. Open `http://127.0.0.1:8000`
3. Upload a TXT, MD, or PDF file from the Upload tab.

## What Is Included

- `main.py` - FastAPI app wiring, runtime bootstrap, and route registration
- `index.html` - legacy browser shell served by FastAPI during frontend transition
- `static/` - active web assets used by `index.html`
- `macos-app/Resources/app.new.html` - bundled macOS app surface now loaded by default
- `macos-app/Resources/app.html.legacy` - legacy macOS bundle retained as an escape hatch
- `migrations/` - versioned SQLite schema source of truth
- `schema.sql` - historical SQLite schema reference retained during the migration transition
- `api-contracts.md` - REST endpoints for a future backend
- `benchmarks/` - Phase 0 benchmark harness and comparison logic
- `evals/` - local-first eval suite scaffolding and smoke runner
- `templates/make/` - Make HTTP payloads and workflow guide
- `templates/retool/` - Retool queries and JavaScript snippets
- `templates/notion/` - Notion database setup reference

## Notes

- The app resolves its runtime paths from the repo root by default and supports env overrides such as `EINSTEIN_BASE_DIR`, `EINSTEIN_DB_PATH`, and `EINSTEIN_SCHEMA_PATH`.
- The macOS shell now defaults to the new Preact frontend. Set `EINSTEIN_FRONTEND=legacy` or pass `--frontend legacy` to `script/build_and_run.sh` if you need the previous bundle for comparison.
- Copy `.env.example` to `.env` if you want to pin Anthropic model IDs or runtime paths locally.
- Uploaded files are stored under `data/uploads/`.
- Vector retrieval uses `sqlite-vec` and local `fastembed` embeddings when the runtime supports loadable SQLite extensions.
- The first vector-enabled run downloads the `BAAI/bge-small-en-v1.5` model to `~/.cache/fastembed/` once, which is roughly a 120 MB warm-up cost.
- The current tutoring, question generation, and explanations are deterministic local logic so phase 1 works without a live LLM.
- Make, Retool, and Notion templates are still included for later external integrations.
- Phase 0 status: Batch A is shipped (portable runtime paths, typed Claude router, structured backend logging). Batch B adds benchmarks, CI scaffolding, and eval smoke suites without changing product behavior.
