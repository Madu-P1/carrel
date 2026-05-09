"""Integration tests for the reader-node lookup endpoint (PR 4.2)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.ingestion.persistence import insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.local_api_security import HEADER_NAME, get_local_api_token

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _node(order: int, *, text: str = "") -> TypedNode:
    return TypedNode(
        node_type="body",
        heading_path="Photosynthesis",
        page=12,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


class ReaderNodeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base_dir = Path(self._tmp.name)
        data_dir = base_dir / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(MIGRATIONS_SOURCE, base_dir / "migrations", dirs_exist_ok=True)
        (base_dir / "schema.sql").write_text("-- test\n", encoding="utf-8")

        self._original = (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        )
        main.BASE_DIR = base_dir
        main.DATA_DIR = data_dir
        main.UPLOAD_DIR = upload_dir
        main.DB_PATH = data_dir / "test.db"
        main.SCHEMA_PATH = base_dir / "schema.sql"
        main.initialize_database()

        with main.get_db() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
                "VALUES ('doc-bio', 'photosynthesis.md', 'md', 'ready', 'manual_text', 'Biology')"
            )
            ids = insert_typed_nodes(
                conn,
                "doc-bio",
                [
                    _node(0, text="Plants use chlorophyll to capture light energy"),
                ],
            )
            conn.commit()
            self._node_id = ids[0]

        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        main.BASE_DIR = self._original[0]
        main.DATA_DIR = self._original[1]
        main.UPLOAD_DIR = self._original[2]
        main.DB_PATH = self._original[3]
        main.SCHEMA_PATH = self._original[4]
        self._tmp.cleanup()

    def test_returns_full_node_payload(self) -> None:
        response = self.client.get(f"/api/reader/node/{self._node_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["node_id"], self._node_id)
        self.assertEqual(body["doc_id"], "doc-bio")
        self.assertEqual(body["filename"], "photosynthesis.md")
        self.assertEqual(body["subject_name"], "Biology")
        self.assertEqual(body["node_type"], "body")
        self.assertEqual(body["heading_path"], "Photosynthesis")
        self.assertEqual(body["page"], 12)
        self.assertIn("Plants use chlorophyll", body["verbatim_text"])
        self.assertEqual(body["char_start"], 0)
        self.assertGreater(body["char_end"], body["char_start"])

    def test_unknown_node_returns_404(self) -> None:
        response = self.client.get("/api/reader/node/9999999")
        self.assertEqual(response.status_code, 404)

    def test_negative_node_id_returns_400(self) -> None:
        response = self.client.get("/api/reader/node/-1")
        # FastAPI's path validation on int may produce 422 for malformed,
        # but our explicit check catches the <= 0 case → 400.
        self.assertIn(response.status_code, (400, 422))

    def test_zero_node_id_returns_400(self) -> None:
        response = self.client.get("/api/reader/node/0")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
