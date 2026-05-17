# Carrel

Local-first, source-grounded AI study and research workspace for macOS. Drop in PDFs, notes, slides. Get a concept graph, SRS cards, grounded tutor answers that cite back to page-level spans, and a coach that proposes study blocks against your real calendar.

> A "carrel" is a small enclosed study booth in a library. The product is named after the room it tries to feel like.

> **Renamed from Einstein Tutor.** Some internal identifiers (the macOS app bundle `EinsteinDesktop.app`, `com.madu.EinsteinDesktop` bundle ID, and the `data/einstein_tutor.db` SQLite file) are still on the old names because renaming them is a system-level / data-migration concern. See `docs/notes/2026-04-29-carrel-rename.md` for the full deferral list.

**Trying Carrel for the first time?** One paste with your Anthropic key:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | \
  ANTHROPIC_API_KEY=sk-ant-api03-your-key-here bash
```

Or local-Ollama instead of Claude:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | \
  EINSTEIN_AI_PROVIDER=ollama bash
```

On macOS 26+ Apple Silicon with Apple Intelligence enabled and en_US primary locale, no key is needed. `install.sh` detects the eligibility and selects Apple's on-device 3B model:

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | bash
```

Any of the three forms clones the repo, installs `uv` (which brings standalone Python 3.12), creates a venv, installs deps, fetches `pnpm` + Node, writes the credential to `.env`, builds, and launches the app. ~5-10 minutes the first run.

Without the env var, install runs fine but stops short of launching and tells you to edit `.env` and run `./script/build_and_run.sh` yourself. Full walkthrough + troubleshooting: [`docs/install-beta.md`](docs/install-beta.md).

Architecture overview: [CLAUDE.md](CLAUDE.md). Design system: [DESIGN.md](DESIGN.md).

## Quick start — macOS app

```bash
./script/build_and_run.sh
```

Builds the Swift shell + Vite frontend bundle, starts the FastAPI backend on `127.0.0.1:8000`, and launches `EinsteinDesktop.app`.

## Quick start — backend only

```bash
python3 -m uvicorn main:app --reload
# then http://127.0.0.1:8000
```

Useful for iterating on routes, ingestion, or the legacy web shell without rebuilding the Swift app.

## AI provider

Carrel routes LLM calls through a provider abstraction at `ai/providers.py`. The `auto` (default) resolution order is:

1. **Claude** (paid Pro tier) when `ANTHROPIC_API_KEY` is set.
2. **Apple Foundation Models** (free, on-device) on macOS 26+ Apple Silicon with Apple Intelligence enabled and `en_US` primary locale.
3. **Ollama** as legacy fallback for macOS 14/15 or Intel.

Override with `EINSTEIN_AI_PROVIDER=claude|afm|ollama|off` in `.env`.

The free tier uses Apple's on-device 3B model via the `EinsteinAFMBridge` Swift sidecar. Model weights ship with macOS 26; first enable in System Settings can stream a model variant from Apple's CDN (1-30 min one-time), after which subsequent launches are instant.

## Configuration

Copy `.env.example` to `.env` and fill in:

- `ANTHROPIC_API_KEY` — required for grounded tutor answers via Claude.
- `EINSTEIN_AI_PROVIDER` — `auto` (default), `claude`, `afm`, `ollama`, or `off`. Picks the LLM backend used by `ai/providers.py`. See **AI provider** above for the `auto` resolution order. Ollama runs the Einstein tier on `llama3.2:3b` (fast) and `llama3.1:8b` (balanced) by default.
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
