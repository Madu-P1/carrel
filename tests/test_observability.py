"""Smoke tests for the observability layer.

The module is small but it sits in the request hot path, so the
contract is worth pinning:
  * Every response carries an X-Request-ID header
  * Inbound X-Request-ID is honored (idempotent across retries)
  * Metrics endpoint is reachable + parseable
  * Counters increment after a request
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.local_api_security import HEADER_NAME, get_local_api_token
from services.observability import REQUEST_ID_HEADER

HEX32 = re.compile(r"^[0-9a-f]{32}$")


class ObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        # Snapshot original paths so the test doesn't leak state.
        self._orig = (
            main.BASE_DIR, main.DATA_DIR, main.UPLOAD_DIR,
            main.DB_PATH, main.SCHEMA_PATH,
        )
        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self._orig[4]
        main.initialize_database()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        (
            main.BASE_DIR, main.DATA_DIR, main.UPLOAD_DIR,
            main.DB_PATH, main.SCHEMA_PATH,
        ) = self._orig
        self.temp_dir.cleanup()

    def test_response_carries_generated_request_id(self) -> None:
        response = self.client.get("/api/health")

        self.assertIn(REQUEST_ID_HEADER, response.headers)
        rid = response.headers[REQUEST_ID_HEADER]
        self.assertTrue(HEX32.match(rid), f"expected 32-hex id, got {rid!r}")

    def test_inbound_request_id_is_propagated(self) -> None:
        # When the macOS shell or a logging proxy injects a request-id,
        # we must echo it back so traces stitch together end-to-end.
        injected = "abc123-trace"
        response = self.client.get(
            "/api/health",
            headers={REQUEST_ID_HEADER: injected},
        )
        self.assertEqual(injected, response.headers[REQUEST_ID_HEADER])

    def test_metrics_endpoint_returns_json_snapshot(self) -> None:
        # Hit health a couple of times so the counter has something.
        self.client.get("/api/health")
        self.client.get("/api/health")
        response = self.client.get("/api/metrics")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertIn("uptime_seconds", body)
        self.assertIn("requests", body)
        self.assertIn("duration_ms", body)
        # The two health hits we just made should be counted.
        health_counts = [
            item for item in body["requests"]
            if item["route"] == "/api/health" and item["status"] == 200
        ]
        self.assertTrue(health_counts, "no /api/health 200 in metrics")

    def test_metrics_endpoint_does_not_require_token(self) -> None:
        # Liveness/readiness probes need to work without a token.
        response = self.client.get("/api/metrics")
        self.assertEqual(200, response.status_code)

    def test_403_responses_are_still_counted(self) -> None:
        # Failed-auth requests must show up in metrics — a flood of
        # 403s is a real signal we want visibility on.
        before = self.client.get("/api/metrics").json()
        self.client.get("/api/documents")  # no token → 403
        after = self.client.get("/api/metrics").json()

        def count_403(snapshot: dict) -> int:
            return sum(
                item["count"] for item in snapshot["requests"]
                if item["status"] == 403
            )

        self.assertGreater(count_403(after), count_403(before))

    def test_request_id_header_does_not_break_authed_path(self) -> None:
        response = self.client.get(
            "/api/documents",
            headers={
                HEADER_NAME: get_local_api_token(),
                REQUEST_ID_HEADER: "trace-7",
            },
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("trace-7", response.headers[REQUEST_ID_HEADER])


if __name__ == "__main__":
    unittest.main()
