from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main


class UsageEventsRouteTests(unittest.TestCase):
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

    def test_event_route_records_only_privacy_safe_properties(self) -> None:
        response = self.client.post(
            "/api/usage-events",
            json={
                "event_name": "reader.find_used",
                "surface": "Reader",
                "properties": {
                    "result_count": 3,
                    "mode": "keyboard",
                    "duration_ms": 12.5,
                    "query": "capital expenditure",
                    "filename": "finance.pdf",
                    "document_text": "raw source text",
                    "api_key": "secret",
                },
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual("reader.find_used", body["event_name"])
        self.assertEqual("reader", body["surface"])
        self.assertEqual(
            {"duration_ms": 12.5, "mode": "keyboard", "result_count": 3},
            body["properties"],
        )

        recent = self.client.get("/api/usage-events/recent").json()
        self.assertEqual(1, len(recent))
        self.assertEqual(body["id"], recent[0]["id"])

    def test_event_route_rejects_unknown_event_names(self) -> None:
        response = self.client.post(
            "/api/usage-events",
            json={"event_name": "reader.raw_query", "properties": {}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual("invalid_usage_event", response.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
