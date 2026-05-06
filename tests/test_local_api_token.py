from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.local_api_security import HEADER_NAME, QUERY_NAME, get_local_api_token


class LocalAPITokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.original_base_dir = main.BASE_DIR
        self.original_data_dir = main.DATA_DIR
        self.original_upload_dir = main.UPLOAD_DIR
        self.original_db_path = main.DB_PATH
        self.original_schema_path = main.SCHEMA_PATH

        main.BASE_DIR = self.base_dir
        main.DATA_DIR = self.base_dir / "data"
        main.UPLOAD_DIR = main.DATA_DIR / "uploads"
        main.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.SCHEMA_PATH = self.original_schema_path
        main.initialize_database()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    def test_health_remains_public(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(200, response.status_code)

    def test_local_token_is_not_readable_from_public_origins(self) -> None:
        response = self.client.get(
            "/api/local-token",
            headers={"Origin": "https://example.com"},
        )

        self.assertEqual(200, response.status_code)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_localhost_origin_can_read_local_token(self) -> None:
        response = self.client.get(
            "/api/local-token",
            headers={"Origin": "http://127.0.0.1:5173"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("http://127.0.0.1:5173", response.headers.get("access-control-allow-origin"))

    def test_mutating_request_rejects_missing_token(self) -> None:
        response = self.client.post("/api/goal", json={"goal": "Study finance"})

        self.assertEqual(403, response.status_code)
        self.assertEqual("missing_or_invalid_local_api_token", response.json()["detail"]["code"])

    def test_mutating_request_rejects_wrong_token(self) -> None:
        response = self.client.post(
            "/api/goal",
            headers={HEADER_NAME: "wrong"},
            json={"goal": "Study finance"},
        )

        self.assertEqual(403, response.status_code)

    def test_mutating_request_accepts_correct_token(self) -> None:
        response = self.client.post(
            "/api/goal",
            headers={HEADER_NAME: get_local_api_token()},
            json={"goal": "Study finance"},
        )

        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("Study finance", response.json()["goal"])

    def test_get_request_rejects_missing_token(self) -> None:
        # The audit's main complaint: GET endpoints used to be world-
        # readable on the local machine. The gate now covers them too.
        response = self.client.get("/api/documents")

        self.assertEqual(403, response.status_code)
        self.assertEqual(
            "missing_or_invalid_local_api_token",
            response.json()["detail"]["code"],
        )

    def test_get_request_accepts_correct_token(self) -> None:
        response = self.client.get(
            "/api/documents",
            headers={HEADER_NAME: get_local_api_token()},
        )

        self.assertEqual(200, response.status_code, response.text)

    def test_get_request_accepts_query_token(self) -> None:
        # SSE / EventSource fallback path — header-less auth via
        # ?token= query param.
        response = self.client.get(
            f"/api/documents?{QUERY_NAME}={get_local_api_token()}"
        )

        self.assertEqual(200, response.status_code, response.text)

    def test_query_token_does_not_authenticate_mutating_verb(self) -> None:
        # Defence-in-depth: a malicious page that only controls the
        # URL (e.g., an <img src> ping) shouldn't be able to mutate.
        response = self.client.post(
            f"/api/goal?{QUERY_NAME}={get_local_api_token()}",
            json={"goal": "Study finance"},
        )

        self.assertEqual(403, response.status_code)

    def test_cors_preflight_options_bypasses_auth_gate(self) -> None:
        # Regression: browsers send `OPTIONS` preflights automatically
        # for cross-origin requests; they CAN'T carry custom auth
        # headers. Pre-fix, the new full-/api gate 403'd every
        # preflight, which broke every endpoint from the WebView's
        # file:// origin. The fix exempts OPTIONS from the gate; the
        # actual request that follows still gets checked.
        response = self.client.options(
            "/api/documents",
            headers={
                "Origin": "file://",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-carrel-local-token",
            },
        )
        # Should NOT be 403 — let the CORS middleware respond. Status
        # is typically 200 for an accepted preflight.
        self.assertNotEqual(403, response.status_code)
        self.assertIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
