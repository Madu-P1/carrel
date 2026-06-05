"""Frozen-app entry point for the bundled Cachet desktop build (PyInstaller).

This is the double-click target. Unlike script/serve-cachet.py (which shells out
to `python -m uvicorn` and assumes a dev checkout), a frozen exe has no `python`
to shell to, so this runs uvicorn IN-PROCESS and resolves all paths for a packaged
app: read-only resources come from the bundle (sys._MEIPASS), and the database +
uploads + logs go to the OS user-data dir so they're writable and survive updates.

Scope: the deterministic core (DOCX / digital-PDF ingest + CourtListener
cite-existence + verbatim-quote check). The heavy ML deps (Docling OCR, fastembed
embeddings) are lazy-imported in the backend and intentionally excluded from the
bundle (see packaging/cachet.spec), so retrieval falls back to FTS5 and scanned-PDF
OCR is unavailable. See docs/plans/cachet-localhost-browser-2026-06-05.md.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def _user_data_dir() -> Path:
    """Writable per-user dir for the DB / uploads / logs. Survives app updates and
    avoids writing next to a read-only / Program Files install."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "Cachet"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cachet"
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "Cachet"


def _resource_dir() -> Path:
    """Read-only bundled resources (frontend dist, migrations, schema). PyInstaller
    onefile unpacks them to sys._MEIPASS; in a dev run this file's repo root."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def _free_port(preferred: int) -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free loopback port available")


def _open_browser_when_ready(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"
    health = f"http://127.0.0.1:{port}/api/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health, timeout=2) as resp:  # noqa: S310 (loopback)
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)


def main() -> int:
    data_dir = _user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    resources = _resource_dir()

    # Configure the backend for packaged, standalone-Cachet operation BEFORE
    # importing it (main.py reads these at import time).
    os.environ.setdefault("CACHET_ONLY", "1")
    os.environ.setdefault("EINSTEIN_BASE_DIR", str(resources))  # bundled migrations/schema
    os.environ.setdefault("EINSTEIN_DATA_DIR", str(data_dir))  # writable DB/uploads/logs
    os.environ.setdefault("CACHET_WEB_DIST", str(resources / "dist-cachet"))
    # Fast ingest: the deterministic quote/cite catch reads full document text, not
    # vectors, so skip per-chunk embedding on upload. Cuts a huge contract from
    # minutes to seconds (measured 520s -> 2.2s on a 2000-section doc). Vectors are
    # marked backfill-pending and can be added later if semantic grounding is wired.
    os.environ.setdefault("EMBED_ON_INGEST", "false")
    # Never disable the token gate; the served HTML carries the per-run token.
    os.environ.pop("CARREL_API_OPEN_MODE", None)

    port = _free_port(int(os.environ.get("CACHET_PORT", "8000")))

    import uvicorn

    import main as backend  # imports the FastAPI app with the env above applied

    threading.Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()
    print(f"Cachet is running at http://127.0.0.1:{port}/  (close this window to quit)")
    uvicorn.run(backend.app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
