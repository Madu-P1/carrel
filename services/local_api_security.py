from __future__ import annotations

import os
import secrets

from fastapi import Request


HEADER_NAME = "X-Carrel-Local-Token"
# Paths the local-API token middleware must NOT gate. `/api/health` is the
# liveness probe the Swift BackendSupervisor and the frontend boot check
# both poll. It has no body and leaks no state, so requiring a token there
# would (a) force the WKWebView bootstrap into a chicken-and-egg before
# the user script can inject the token, and (b) break the Swift
# supervisor's 60s health-monitor loop with 403s.
EXEMPT_PATHS = {"/api/health"}

_LOCAL_API_TOKEN = os.getenv("CARREL_LOCAL_API_TOKEN") or secrets.token_urlsafe(32)


def get_local_api_token() -> str:
    return _LOCAL_API_TOKEN


def requires_local_api_token(request: Request) -> bool:
    path = request.url.path
    if not path.startswith("/api/"):
        return False
    if request.method.upper() == "OPTIONS":
        return False  # CORS preflight, no body
    if path in EXEMPT_PATHS:
        return False
    return True


def has_valid_local_api_token(request: Request) -> bool:
    # EventSource cannot set custom headers, so the SSE path
    # (services/sse.ts -> withLocalApiToken) appends ?token=<value>.
    # Loopback-only, so query-string leakage via shared logs is not a
    # cross-origin concern.
    supplied = request.headers.get(HEADER_NAME) or request.query_params.get("token")
    if not supplied:
        return False
    return secrets.compare_digest(supplied, _LOCAL_API_TOKEN)


# Backward-compat alias. Pre-PR-S1 the predicate was named for the
# narrower "mutating methods only" gate; we keep the old name pointed at
# the broader predicate so any out-of-tree imports keep working without
# silently reverting to the laxer rule.
is_mutating_api_request = requires_local_api_token
