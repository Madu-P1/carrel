"""HTTP-level tests for pagination-param validation on GET /api/documents.

Malformed limit/offset must return 422 with a structured error body whose
"field" key names the offending param. Valid params must return 200 and a
list-shaped body.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import db
import main
from services.local_api_security import HEADER_NAME, get_local_api_token

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class ListPaginationGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_paths = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=upload_dir,
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        with db.get_db() as conn:
            db.apply_migrations(conn)

        from fastapi.testclient import TestClient

        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        db.configure_paths(
            base_dir=self._original_paths[0],
            data_dir=self._original_paths[1],
            upload_dir=self._original_paths[2],
            db_path=self._original_paths[3],
            schema_path=self._original_paths[4],
        )
        self._temp.cleanup()

    # --- invalid cases ---
    # FastAPI's Query(ge=.., le=..) validation returns the standard 422
    # {"detail": [...]} body. Each error entry names the offending param in
    # its "loc" tuple, e.g. ["query", "limit"].

    def _offending_params(self, body: dict) -> set[str]:
        detail = body.get("detail", [])
        params: set[str] = set()
        for entry in detail:
            loc = entry.get("loc", []) if isinstance(entry, dict) else []
            if loc:
                params.add(str(loc[-1]))
        return params

    def test_non_integer_limit_returns_422(self) -> None:
        resp = self.client.get("/api/documents", params={"limit": "banana"})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("limit", self._offending_params(resp.json()))

    def test_negative_offset_returns_422(self) -> None:
        resp = self.client.get("/api/documents", params={"offset": "-5"})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("offset", self._offending_params(resp.json()))

    def test_over_max_limit_returns_422(self) -> None:
        resp = self.client.get("/api/documents", params={"limit": "999"})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("limit", self._offending_params(resp.json()))

    # --- valid case ---

    def test_valid_pagination_returns_200_and_list(self) -> None:
        resp = self.client.get("/api/documents", params={"limit": "10", "offset": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)


if __name__ == "__main__":
    unittest.main()
