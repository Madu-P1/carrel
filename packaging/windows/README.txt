CACHET - Windows package
========================

What this is
------------
Cachet running as a local app in your browser: the same UI and the same
deterministic verification engine as the macOS build, served from a private
local server at http://127.0.0.1:8000. Nothing leaves the machine: the verify
path is offline by construction (no LLM, no cloud calls).

Run it
------
1. Install Python 3.11+ from https://www.python.org/downloads/
   (tick "Add python.exe to PATH" during install)
2. Double-click run-cachet.bat
   First run installs dependencies (a few minutes, network needed once).
   Your browser opens to http://127.0.0.1:8000 automatically.
3. To stop: close the black console window (or Ctrl-C in it).

Optional, recommended: provision-models.bat
-------------------------------------------
One-time ~130 MB download that caches the local embedding model. After it,
contract verification (the in-house wedge) runs fully offline. Citation and
quote verification work without this step.

Honest notes
------------
- The verify engine is the deterministic one (CACHET_DETERMINISTIC_VERIFY is
  hard-pinned by the server script). No draft text is sent anywhere.
- Scanned/image-only PDFs will not OCR on Windows (that uses a macOS-only
  component). Born-digital PDFs, Word files, and pasted text work.
- Dependency install and the optional model download are the only two
  network-touching moments; both are one-time provisioning.
- Data lives in a local SQLite file under this folder (created on first run).
- If port 8000 is busy, close whatever holds it and re-run.

Built 2026-06-11 from the Carrel/Cachet repo (cross-platform loopback
delivery seam, script/serve-cachet.py).
