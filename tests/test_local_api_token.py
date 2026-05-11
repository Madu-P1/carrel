from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.local_api_security import HEADER_NAME, get_local_api_token


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

    def test_local_token_route_is_deleted(self) -> None:
        # PR-S1: the unauthenticated GET /api/local-token route was the
        # root vulnerability — any local browser tab could fetch the
        # token then issue any mutating request. The route is gone; any
        # remaining caller now gets the standard token gate (403) or a
        # 404 if no other handler matches.
        response = self.client.get(
            "/api/local-token",
            headers={"Origin": "http://127.0.0.1:5173"},
        )

        self.assertIn(response.status_code, {403, 404})

    def test_get_request_rejects_missing_token(self) -> None:
        # PR-S1: the token gate now covers every /api/* path (except
        # /api/health), not just mutating methods. A naked GET should
        # fail closed.
        response = self.client.get("/api/workspace")

        self.assertEqual(403, response.status_code)
        self.assertEqual("missing_or_invalid_local_api_token", response.json()["detail"]["code"])

    def test_get_request_accepts_correct_token(self) -> None:
        response = self.client.get(
            "/api/workspace",
            headers={HEADER_NAME: get_local_api_token()},
        )

        self.assertEqual(200, response.status_code, response.text)

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


if __name__ == "__main__":
    unittest.main()
