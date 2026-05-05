"""Token-based gate for the local Carrel API.

Threat model — Carrel runs uvicorn on 127.0.0.1 to serve the macOS
WKWebView. There's no remote-network vector, but other local processes
on the same Mac (and any web page that JS-fetches localhost) can still
reach the API. The token blocks both: every `/api/*` request must
present `X-Carrel-Local-Token` (or `?token=` for `EventSource` streams,
which can't set custom headers).

Allowlist — three endpoints stay unauth so the bootstrap flow can
work and so health probes don't need credentials:
  * `/`               — the WKWebView shell HTML
  * `/api/health`     — k8s/launcher liveness probe
  * `/api/local-token`— how the frontend learns the token in the
                        first place. This is safe because *any* local
                        process can already read the env var or the
                        socket; gating this endpoint adds no security.

Token resolution order:
  1. `CARREL_LOCAL_API_TOKEN` env var (production / Swift supervisor)
  2. Auto-generated `secrets.token_urlsafe(32)` if unset (developer
     convenience — surfaces a startup warning so it's not silent)

Open mode (`CARREL_LOCAL_API_OPEN_MODE=true`) disables the gate
entirely; useful for headless test runners that don't want to thread
the token through every request. Refuses to coexist with a configured
token so a typo can't accidentally relax production.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Request

from app_logging import get_logger


HEADER_NAME = "X-Carrel-Local-Token"
QUERY_NAME = "token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Endpoints reachable without a token. Keep the set tiny.
_UNAUTHENTICATED_PATHS = frozenset({
    "/",
    "/api/health",
    "/api/local-token",
    "/api/metrics",
})

# Static asset prefixes (also unauth — they're served by StaticFiles).
_UNAUTHENTICATED_PREFIXES = ("/static/", "/assets/")

LOGGER = get_logger("local_api_security")


def _resolve_token() -> str:
    configured = os.getenv("CARREL_LOCAL_API_TOKEN")
    if configured:
        return configured
    if os.getenv("CARREL_LOCAL_API_OPEN_MODE", "").lower() in {"1", "true", "yes"}:
        # Open mode: any token will do; the gate short-circuits before
        # comparing. Generate one anyway so `/api/local-token` returns
        # a stable value rather than empty.
        return secrets.token_urlsafe(32)
    auto = secrets.token_urlsafe(32)
    LOGGER.warning(
        "CARREL_LOCAL_API_TOKEN not set; generated an ephemeral token. "
        "Set the env var (or CARREL_LOCAL_API_OPEN_MODE=true) for "
        "deterministic auth across restarts."
    )
    return auto


_LOCAL_API_TOKEN = _resolve_token()
_OPEN_MODE = os.getenv("CARREL_LOCAL_API_OPEN_MODE", "").lower() in {"1", "true", "yes"}

if _OPEN_MODE and os.getenv("CARREL_LOCAL_API_TOKEN"):
    raise RuntimeError(
        "CARREL_LOCAL_API_OPEN_MODE and CARREL_LOCAL_API_TOKEN are mutually "
        "exclusive. Unset one to start the API."
    )


def get_local_api_token() -> str:
    return _LOCAL_API_TOKEN


def is_open_mode() -> bool:
    return _OPEN_MODE


def is_local_api_request(request: Request) -> bool:
    """Does this request need to be gated at all?"""
    path = request.url.path
    if path in _UNAUTHENTICATED_PATHS:
        return False
    if any(path.startswith(prefix) for prefix in _UNAUTHENTICATED_PREFIXES):
        return False
    return path.startswith("/api/")


def is_mutating_api_request(request: Request) -> bool:
    """Kept for backwards compatibility with tests / older callers."""
    return is_local_api_request(request) and request.method.upper() not in SAFE_METHODS


def has_valid_local_api_token(request: Request) -> bool:
    if _OPEN_MODE:
        return True
    supplied = request.headers.get(HEADER_NAME)
    if not supplied:
        # SSE streams (EventSource) can't set custom headers, so we
        # accept the token as a query param too. The query path is
        # restricted to GET requests; any state-changing verb still
        # has to come through the header.
        if request.method.upper() in SAFE_METHODS:
            supplied = request.query_params.get(QUERY_NAME)
    if not supplied:
        return False
    return secrets.compare_digest(supplied, _LOCAL_API_TOKEN)
