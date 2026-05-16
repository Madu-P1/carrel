"""Unit tests for ``services.local_api_security.requires_local_api_token``.

PR-S1: the predicate was broadened from "mutating methods only" to "all
/api/* paths except a small exempt set". These tests pin the contract so
a future regression that silently re-opens GET endpoints to unauthenticated
local-origin tabs fails loudly.
"""

from __future__ import annotations

import unittest

from starlette.requests import Request

from services import local_api_security
from services.local_api_security import (
    EXEMPT_PATHS,
    get_local_api_token,
    has_valid_local_api_token,
    is_mutating_api_request,
    is_open_mode,
    requires_local_api_token,
)


def _make_request(
    method: str,
    path: str,
    *,
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    """Build a minimal ASGI Request without spinning up the app.

    `requires_local_api_token` only inspects `request.url.path` and
    `request.method`. `has_valid_local_api_token` also reads headers and
    query params, so callers can override them.
    """
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": query_string,
        "headers": headers or [],
    }
    return Request(scope=scope)


class RequiresLocalApiTokenTests(unittest.TestCase):
    def test_requires_token_for_get_workspace(self) -> None:
        request = _make_request("GET", "/api/workspace")

        self.assertTrue(requires_local_api_token(request))

    def test_requires_token_for_post_documents(self) -> None:
        request = _make_request("POST", "/api/documents")

        self.assertTrue(requires_local_api_token(request))

    def test_exempts_health(self) -> None:
        request = _make_request("GET", "/api/health")

        self.assertFalse(requires_local_api_token(request))
        # And the exempt set is the source of truth — guard against a
        # typo that silently re-gates the liveness probe.
        self.assertIn("/api/health", EXEMPT_PATHS)

    def test_exempts_cors_preflight(self) -> None:
        # OPTIONS preflights carry no body and no caller-controlled state;
        # gating them would just break browsers that pre-flight before
        # the WKUserScript token injector has run.
        request = _make_request("OPTIONS", "/api/anything")

        self.assertFalse(requires_local_api_token(request))

    def test_non_api_paths_not_gated(self) -> None:
        # `/static/*` is served by StaticFiles, `/` returns index.html;
        # neither lives under `/api/` so the token middleware must
        # pass them straight through.
        request = _make_request("GET", "/static/foo")

        self.assertFalse(requires_local_api_token(request))

    def test_backward_compat_alias_works(self) -> None:
        # `is_mutating_api_request` is kept as a deprecated alias so any
        # out-of-tree callers don't break. The two names must resolve to
        # the same predicate.
        request = _make_request("POST", "/api/goal")

        self.assertEqual(
            is_mutating_api_request(request),
            requires_local_api_token(request),
        )


class HasValidLocalApiTokenTests(unittest.TestCase):
    """SSE / EventSource cannot set custom headers, so `?token=` is the only
    auth carrier on that path. `has_valid_local_api_token` must accept it."""

    def test_accepts_correct_header(self) -> None:
        token = get_local_api_token()
        request = _make_request(
            "POST",
            "/api/goal",
            headers=[(b"x-carrel-local-token", token.encode("utf-8"))],
        )
        self.assertTrue(has_valid_local_api_token(request))

    def test_accepts_correct_query_param_for_sse(self) -> None:
        token = get_local_api_token()
        request = _make_request(
            "GET",
            "/api/jobs/stream",
            query_string=f"token={token}".encode("utf-8"),
        )
        self.assertTrue(has_valid_local_api_token(request))

    def test_rejects_wrong_token_in_header(self) -> None:
        request = _make_request(
            "POST",
            "/api/goal",
            headers=[(b"x-carrel-local-token", b"wrong")],
        )
        self.assertFalse(has_valid_local_api_token(request))

    def test_rejects_wrong_token_in_query_param(self) -> None:
        request = _make_request(
            "GET",
            "/api/jobs/stream",
            query_string=b"token=wrong",
        )
        self.assertFalse(has_valid_local_api_token(request))

    def test_rejects_missing_token(self) -> None:
        request = _make_request("POST", "/api/goal")
        self.assertFalse(has_valid_local_api_token(request))


class OpenModeTests(unittest.TestCase):
    """CARREL_API_OPEN_MODE is the dev-mode escape hatch for Vite-dev
    work where Swift can't inject the local-API token. When on, every
    /api/* path skips the gate. Default is off — production stays
    gated by the bundled .app's WKUserScript token injection."""

    def setUp(self) -> None:
        self._previous = local_api_security._OPEN_MODE

    def tearDown(self) -> None:
        local_api_security._OPEN_MODE = self._previous

    def test_default_off(self) -> None:
        # is_open_mode() reflects the module-level constant; with no
        # env override the default is False.
        local_api_security._OPEN_MODE = False
        self.assertFalse(is_open_mode())

    def test_open_mode_skips_gate_for_post(self) -> None:
        local_api_security._OPEN_MODE = True
        request = _make_request("POST", "/api/notes")
        self.assertFalse(requires_local_api_token(request))

    def test_open_mode_skips_gate_for_get(self) -> None:
        local_api_security._OPEN_MODE = True
        request = _make_request("GET", "/api/workspace")
        self.assertFalse(requires_local_api_token(request))

    def test_open_mode_off_still_gates(self) -> None:
        local_api_security._OPEN_MODE = False
        request = _make_request("POST", "/api/notes")
        self.assertTrue(requires_local_api_token(request))


if __name__ == "__main__":
    unittest.main()
