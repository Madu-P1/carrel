"""Regression tests pinning the /api/health liveness contract.

The /api/health endpoint MUST stay cheap and DB-free. A previous
implementation called fetch_documents() (one query + N+1 detail
fetches), which made probes take 30+ seconds under load, causing
BackendSupervisor.swift and BackendBootCheck.tsx to surface a
false "backend down" overlay even though uvicorn was alive.

If anyone re-introduces a DB query here, these tests fail loudly.
"""

from __future__ import annotations

import time
from unittest import TestCase, mock

from fastapi.testclient import TestClient

import main


class HealthEndpointContractTests(TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_returns_200_and_status_ok(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")

    def test_response_shape_is_stable(self) -> None:
        body = self.client.get("/api/health").json()
        # status + mode + paths are the documented liveness fields.
        self.assertIn("status", body)
        self.assertIn("mode", body)
        self.assertIn("paths", body)
        self.assertIn("base_dir", body["paths"])
        self.assertIn("db_path", body["paths"])

    def test_does_not_open_a_database_connection(self) -> None:
        # The single load-bearing assertion. If anyone adds a DB query
        # back into /api/health, get_db() will be called and this
        # test will fail. The error message points at the prior
        # regression so future contributors know why this exists.
        import db

        with mock.patch.object(db, "get_db", wraps=db.get_db) as spy:
            response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            spy.call_count,
            0,
            msg=(
                "/api/health opened a database connection. The endpoint "
                "must stay DB-free — see the comment in routes/workspace.py "
                "for the regression this guards against (BackendSupervisor "
                "false-respawn loop, 'Couldn't connect to local backend' "
                "overlay sticking for 30+ seconds)."
            ),
        )

    def test_returns_fast_even_when_db_would_be_slow(self) -> None:
        # The endpoint should never wait on a DB lock. We assert a
        # generous 100ms budget on the response. Real-world probes
        # are <50ms; this leaves headroom for CI / cold caches.
        start = time.monotonic()
        response = self.client.get("/api/health")
        elapsed = time.monotonic() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(
            elapsed,
            0.1,
            msg=f"/api/health took {elapsed * 1000:.1f}ms; liveness budget is 100ms",
        )
