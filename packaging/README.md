# Cachet desktop bundle

Package Cachet as a single double-click app so a lawyer can run it with no Python,
no Node, no terminal. The bundled app starts the backend in-process, serves the UI
over loopback, and opens the browser. Its database lives in the OS user-data dir
(`%APPDATA%\Cachet` on Windows, `~/Library/Application Support/Cachet` on macOS).

## Scope (what's in the bundle)

The **deterministic core**: DOCX / digital-PDF source ingestion, CourtListener
cite-existence, and the verbatim-quote check. The heavy ML stack (Docling OCR,
fastembed embeddings + onnxruntime, ~2-3 GB) is excluded, so:

- retrieval falls back to FTS5 (keyword), no vector search;
- scanned / image-only PDF OCR is unavailable (DOCX and digital PDFs are fine).

Bundle size is ~30 MB instead of multiple GB. This matches the demo value (the
deterministic catch needs no model).

## Build it

You can only build for the OS you run on (PyInstaller does not cross-compile).

**Windows** (needs Python 3.11+ and Node 20+ on PATH):

```
packaging\build.bat
```

→ `dist\Cachet.exe`. Double-click it.

**macOS / Linux** (needs python3 and Node 20+):

```
bash packaging/build.sh
```

→ `dist/Cachet`. Run it.

Either script builds the frontend, makes a clean build venv with only the core
deps, and freezes with PyInstaller.

## Or let CI build it (for distribution)

Push a tag to build both Windows + macOS binaries and publish a GitHub Release:

```
git tag cachet-v0.1.0 && git push origin cachet-v0.1.0
```

The workflow (`.github/workflows/cachet-package.yml`) also runs on demand
(Actions → "Cachet desktop package" → Run workflow) and uploads the binaries as
artifacts without a release.

## First-launch warning (it's unsigned)

The binary is **not code-signed yet**, so the first launch shows a security prompt:

- **Windows:** "Windows protected your PC" → **More info** → **Run anyway**.
- **macOS:** "unidentified developer" → right-click the app → **Open** → **Open**.

Real signing (Apple Developer ID + a Windows code-signing cert) removes this. It is
the unstarted Phase 4; fine to click through for a supervised demo, worth doing
before cold distribution to lawyers.

## Files

| File | Role |
|---|---|
| `cachet_frozen.py` | Frozen entry: in-process uvicorn, user-data dir, opens the browser |
| `cachet.spec` | PyInstaller spec (onefile; bundles the frontend + migrations + sqlite-vec; excludes the ML stack) |
| `requirements-package.txt` | Core deps for the build venv (no Docling/fastembed) |
| `build.sh` / `build.bat` | One-command local build (macOS-Linux / Windows) |

CI workflow: `../.github/workflows/cachet-package.yml`. Plan:
`../docs/plans/cachet-localhost-browser-2026-06-05.md`.
