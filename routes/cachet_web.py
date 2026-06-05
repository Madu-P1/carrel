"""Serve the built Cachet frontend over loopback (the localhost-browser delivery
path) so Windows + Mac lawyers can run Cachet without the macOS WKWebView shell.

Registered ONLY in CACHET_ONLY mode (see routes/__init__.register_cachet_routes).
The backend serves the production `build:cachet` output and injects the local-API
token into the served HTML, replacing the Swift WKUserScript injection the .app
uses. The served page is same-origin with the API, so the token rides the request
header with no CORS preflight, and the frontend talks to its own origin
(``window.__CARREL_API_BASE = ""``) so the launcher can pick any free port.

Security: the HTML + assets are non-/api/ paths, so the token middleware leaves
them ungated (the page must load before it can read the token). DNS-rebinding
token theft is closed by the loopback Host guard installed in main.py
(services.local_api_security.install_loopback_host_guard).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from services.local_api_security import get_local_api_token


def _default_dist_dir() -> Path:
    """The `pnpm --dir frontend build:cachet` output. Override with CACHET_WEB_DIST
    (e.g. when the backend runs from a different cwd than the repo root)."""
    override = os.getenv("CACHET_WEB_DIST")
    if override:
        return Path(override)
    # routes/cachet_web.py -> repo root is two parents up.
    return Path(__file__).resolve().parent.parent / "frontend" / "dist-cachet"


def inject_local_api_bootstrap(html: str, token: str, api_base: str) -> str:
    """Insert a classic <script> setting the window globals the frontend reads
    (``__CARREL_LOCAL_API_TOKEN`` + ``__CARREL_API_BASE``). It goes right after
    <head> so it runs at parse time, before the deferred type=module app bundle.
    json.dumps escapes the values safely."""
    script = (
        "<script>"
        f"window.__CARREL_LOCAL_API_TOKEN={json.dumps(token)};"
        f"window.__CARREL_API_BASE={json.dumps(api_base)};"
        "</script>"
    )
    lowered = html.lower()
    idx = lowered.find("<head>")
    if idx != -1:
        pos = idx + len("<head>")
        return html[:pos] + script + html[pos:]
    # No <head> (unexpected): prepend so the globals still exist before the bundle.
    return script + html


def register_cachet_web_routes(app: FastAPI, dist_dir: Path | None = None) -> None:
    dist = dist_dir or _default_dist_dir()
    assets = dist / "assets"
    # Mount the hashed JS/CSS/font assets. Guarded: a missing build must not crash
    # boot (StaticFiles raises if the dir is absent); the index route below then
    # returns a clear 503 instead.
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="cachet-assets")

    @app.get("/", response_class=HTMLResponse)
    def serve_cachet_index() -> HTMLResponse:
        index = dist / "cachet.html"
        if not index.is_file():
            return HTMLResponse(
                "<h1>Cachet build missing</h1>"
                "<p>Run <code>pnpm --dir frontend build:cachet</code>, then relaunch.</p>",
                status_code=503,
            )
        html = index.read_text(encoding="utf-8")
        # api_base "" -> same-origin relative calls, so the launcher's chosen port
        # never has to be baked into the bundle.
        # no-store: this page carries the per-run local-API token. Caching it would
        # (a) persist the token to the browser's disk cache and (b) serve a stale
        # token after a relaunch (the token is regenerated each run), which then
        # 403s every API call. The token must never outlive the process.
        return HTMLResponse(
            inject_local_api_bootstrap(html, get_local_api_token(), ""),
            headers={"Cache-Control": "no-store"},
        )
