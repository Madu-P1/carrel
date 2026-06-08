#!/usr/bin/env python
"""Serve the standalone Cachet demo from one loopback process.

Restores the worktree launcher (lost when that worktree was deleted): runs the
FastAPI backend (deterministic verify is default-on and offline by
construction) and serves the built Cachet frontend (`frontend/dist`, built with
`--mode cachet`) from the SAME origin with the local-API token injected, so
POST /api/verify works in a plain browser (no WKWebView, no CORS dance).

Open:
    cd frontend && corepack pnpm vite build --mode cachet   # once, after FE changes
    ./.venv/bin/python script/serve-cachet.py               # prints the URL

Close:
    Ctrl-C.

See CACHET-DEMO-RUNBOOK.md for the full demo procedure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Run from anywhere: put the repo root (where main.py lives) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set BEFORE importing `main` so the backend reads them at construction time.
# - CARREL_LOCAL_API_TOKEN: a fixed token we also inject into the served HTML so
#   the browser's mutating calls (POST /api/verify) carry it.
# - CACHET_DETERMINISTIC_VERIFY=1: belt-and-suspenders. /api/verify already
#   defaults to the deterministic, no-LLM, offline engine; this HARD-PINS it
#   (assignment, not setdefault) so a stray CACHET_DETERMINISTIC_VERIFY=0 in a
#   dotfile can never flip the privacy demo onto the off-device cloud path while
#   the banner still says "offline". The promise must hold unconditionally.
os.environ.setdefault("CARREL_LOCAL_API_TOKEN", "cachet-demo-token")
os.environ["CACHET_DETERMINISTIC_VERIFY"] = "1"
# Sentinel CourtListener token. The deterministic path injects the bundled
# local-caselaw MockTransport (offline) and the case-existence guard now bypasses
# the token whenever a client is injected (courtlistener.py), so this is no longer
# load-bearing for the offline demo; kept as defence-in-depth and for the
# opt-out LLM path. This token never leaves the device.
os.environ.setdefault("COURTLISTENER_API_TOKEN", "local")
# Fast ingest: the deterministic quote/cite catch reads full document text, not
# vectors, so skip per-chunk embedding on upload. Cuts a huge contract from
# ~8.7 min to ~2s (ce74049d0). Cachet-ingested docs have no vectors (FTS +
# deterministic catch still work; vectors are backfillable); Carrel keeps true.
os.environ.setdefault("EMBED_ON_INGEST", "false")

import uvicorn
from fastapi import Response
from fastapi.staticfiles import StaticFiles

import main as backend

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
TOKEN = os.environ["CARREL_LOCAL_API_TOKEN"]
app = backend.app

if not (DIST / "index.html").exists():
    raise SystemExit(
        "frontend/dist/index.html not found. Build the Cachet frontend first:\n"
        "    cd frontend && corepack pnpm vite build --mode cachet"
    )

# Inject the token before </head> (reliably present) so it is set before any
# frontend JS runs. The deterministic path holds no secrets; this token only
# authorizes the local mutating call on the loopback API.
_RAW = (DIST / "index.html").read_text(encoding="utf-8")
_INDEX_HTML = _RAW.replace(
    "</head>",
    f"    <script>window.__CARREL_LOCAL_API_TOKEN = {TOKEN!r};</script>\n  </head>",
    1,
)

# Drop the study-app root ("/" -> Carrel index.html) so the Cachet shell wins at
# the origin root. Every /api/* route stays untouched.
app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]


@app.get("/")
def cachet_root() -> Response:
    return Response(_INDEX_HTML, media_type="text/html")


# Built JS/CSS (vite emits to dist/assets). Mounted after the /api routes so it
# never shadows them.
app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="cachet-assets")


def _port_is_free(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


if __name__ == "__main__":
    if not _port_is_free("127.0.0.1", 8000):
        raise SystemExit(
            "\n  Port 8000 is already in use - a Cachet instance is probably still running.\n"
            "  Either just open http://127.0.0.1:8000 in your browser, or free the port:\n"
            "      lsof -ti tcp:8000 | xargs kill\n"
            "  then run this command again.\n"
        )
    print(
        "\n  Cachet demo  ->  http://127.0.0.1:8000\n"
        "  (deterministic verify, offline; Ctrl-C to close)\n"
    )
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
