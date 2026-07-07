# Cachet

Cachet is an independent, local-first deterministic verification engine for high-stakes AI output. This repo is the Cachet engine + verify-source home. It also carries a source-grounded study/research frontend (drop in PDFs, notes, slides; get a concept graph, SRS cards, grounded answers that cite back to page-level spans) as the substrate the verification surfaces are built on.

> **Native shell extracted 2026-07-07.** The Einstein-era native macOS Swift shell (the app plus its PDF/OCR and Apple Foundation Models sidecars) was moved out of this repo; a full-history clone lives at `~/Desktop/Carrel`. This repo now builds a frontend bundle served under `file://` or by the local backend, not a packaged `.app`.

> **Descends from Einstein Tutor → Carrel.** Some internal identifiers (the legacy `com.madu.Einstein…` app bundle ID, the `data/einstein_tutor.db` SQLite file, the `X-Carrel-Local-Token` API header) are still on the old names because renaming them is a system-level / data-migration concern. See `docs/notes/2026-04-29-carrel-rename.md` for the full deferral list.

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

On macOS 26+ Apple Silicon with en_US primary locale, no key is needed. `install.sh` checks the three install-time conditions (architecture, OS version, primary locale) and selects Apple's on-device 3B model when they hold. The fourth condition, Apple Intelligence enabled in **System Settings, Apple Intelligence & Siri**, is a runtime check; the installer reminds you to confirm it before first launch.

```bash
curl -fsSL https://raw.githubusercontent.com/Madu-P1/carrel/main/install.sh | bash
```

Any of the three forms clones the repo, installs `uv` (which brings standalone Python 3.12), creates a venv, installs deps, fetches `pnpm` + Node, writes the credential to `.env`, builds, and launches the app. ~5-10 minutes the first run.

Without the env var, install runs fine but stops short of launching and tells you to edit `.env` and run `./script/build_and_run.sh` yourself. Full walkthrough + troubleshooting: [`docs/install-beta.md`](docs/install-beta.md).

Architecture overview: [CLAUDE.md](CLAUDE.md). Design system: [DESIGN.md](DESIGN.md).

## Quick start — frontend bundle + backend

```bash
./script/build_and_run.sh
```

Builds the Vite frontend bundle to `dist/app.new.html` and starts the FastAPI backend on `127.0.0.1:8000`. Open `dist/app.new.html` in a browser, or point the extracted native shell (`~/Desktop/Carrel`) at this backend.

## Quick start — backend only

```bash
python3 -m uvicorn main:app --reload
# then http://127.0.0.1:8000
```

Useful for iterating on routes, ingestion, or the verify engine without rebuilding the frontend.

## AI provider

Carrel routes LLM calls through a provider abstraction at `ai/providers.py`. The `auto` (default) resolution order is:

1. **Claude** (paid Pro tier) when `ANTHROPIC_API_KEY` is set.
2. **Apple Foundation Models** (free, on-device) on macOS 26+ Apple Silicon with Apple Intelligence enabled and `en_US` primary locale.
3. **Ollama** as legacy fallback for macOS 14/15 or Intel.

Override with `EINSTEIN_AI_PROVIDER=claude|afm|ollama|off` in `.env` (or `CARREL_AI_PROVIDER`, the canonical post-rename name; both are honored until the deferred-rename pass migrates the rest of the system identifiers).

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

CI also runs a dedicated `memory-pressure-ubuntu` matrix entry on `ubuntu-latest` with `CARREL_FORCE_PSUTIL_MEMORY=1` so the psutil dispatcher branch of `services/ingestion/memory_pressure.py` is exercised cross-platform (the macOS production path goes through `vm_stat` + `sysctl` shellouts and ships green under `swift-build` / `python-tests` / the local verify chain). See `.github/workflows/ci.yml`.
