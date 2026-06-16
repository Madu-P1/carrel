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

import json
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
# NOTE on subject binding: CARREL_SUBJECT_LABELER stays OFF here on purpose. The
# regex floor only binds a figure when a qualified noun sits adjacent to it; real
# contract phrasing ("capped at $X", "shall not exceed $Y") uses bare role words,
# so the floor binds nothing and does NOT stop a cross-subject false-RED ("$1M
# indemnification cap" vs "$500k liability cap"). Turning it on adds no guard and
# the code keeps it off until the AFM semantic labeler is validated (ADR-0013).
# The demo protection is the curated on-script corpus (one value per sentence, no
# cross-subject figure pairs), not this flag. Bare figures are never AFFIRMED
# regardless (ADR-0013 scope-out), so there are no false greens.
# Fast ingest: the deterministic quote/cite catch reads full document text, not
# vectors, so skip per-chunk embedding on upload. Cuts a huge contract from
# ~8.7 min to ~2s (ce74049d0). Cachet-ingested docs have no vectors (FTS +
# deterministic catch still work; vectors are backfillable); Carrel keeps true.
os.environ.setdefault("EMBED_ON_INGEST", "false")
# Pin the embedder weights cache so the offline contract path loads the pre-cached
# bge-small weights instead of failing "the offline embedding model is not cached".
# Provision once online (network on) before the demo:
#   CARREL_FASTEMBED_CACHE_DIR=~/.cache/carrel-fastembed HF_HUB_OFFLINE=0 \
#     .venv/bin/python -c "from fastembed import TextEmbedding; \
#       TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='$CARREL_FASTEMBED_CACHE_DIR')"
os.environ.setdefault(
    "CARREL_FASTEMBED_CACHE_DIR", str(Path.home() / ".cache" / "carrel-fastembed")
)

import uvicorn
from fastapi import Response
from fastapi.staticfiles import StaticFiles

import main as backend
from services import revision as _rev

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
# json.dumps + the close-tag escape keep the injected value inert as HTML: a
# token containing </script> (operator-set env) must not break out of the tag.
_TOKEN_JS = json.dumps(TOKEN).replace("</", "<\\/")
_INDEX_HTML = _RAW.replace(
    "</head>",
    f"    <script>window.__CARREL_LOCAL_API_TOKEN = {_TOKEN_JS};</script>\n  </head>",
    1,
)

# Drop the study-app root ("/" -> Carrel index.html) so the Cachet shell wins at
# the origin root. Every /api/* route stays untouched.
app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]


def _stale_overlay() -> str:
    """A small always-on 'running <commit>' pill, plus a loud banner when the
    server BOOTED on an older commit than the repo now holds. This is the
    stale-build guard: a frozen server (the exact failure that made the engine
    look broken) now announces itself instead of silently serving old code.
    Computed per '/' request (a cold path, not a hot one) so it reflects the
    repo's live HEAD against the process's boot commit."""
    boot = _rev.BOOT_COMMIT
    head = _rev.current_head()
    pill = (
        '<div style="position:fixed;left:8px;bottom:8px;z-index:99998;'
        "font:11px/1.4 ui-monospace,SFMono-Regular,monospace;color:#8a7f72;"
        "background:rgba(245,242,237,.88);border:1px solid #d8cfc2;border-radius:6px;"
        'padding:2px 7px;pointer-events:none">running ' + boot + "</div>"
    )
    stale = boot != "unknown" and head != "unknown" and head != boot
    if not stale:
        return pill
    banner = (
        '<div style="position:fixed;top:0;left:0;right:0;z-index:99999;'
        "background:#7c1d1d;color:#fff;font:13px/1.5 ui-sans-serif,system-ui;"
        'text-align:center;padding:7px 12px">'
        "This server booted on commit "
        + boot
        + " but the repo is now at "
        + head
        + ". It is serving stale code. Restart it: "
        '<code style="background:rgba(255,255,255,.2);padding:1px 5px;border-radius:4px">'
        "lsof -ti tcp:8000 | xargs kill; python script/serve-cachet.py</code></div>"
    )
    return banner + pill


@app.get("/")
def cachet_root() -> Response:
    overlay = _stale_overlay()
    html = (
        _INDEX_HTML.replace("</body>", overlay + "</body>", 1)
        if "</body>" in _INDEX_HTML
        else _INDEX_HTML + overlay
    )
    return Response(html, media_type="text/html")


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
