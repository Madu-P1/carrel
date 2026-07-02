"""HTTP-level tests for the vault routes (routes/documents.py).

The service layer (create_vault / delete_vault / list_vault_names) is unit-tested
in test_document_vaults.py; these cover what only the HTTP layer adds. The
regression that matters: a vault named after a caption containing a slash (e.g.
"Apex / Northwind") must round-trip create -> delete. The delete name travels as a
query parameter, not a path segment, because the {name} path converter 404s on the
encoded slash, leaving such a vault undeletable.

TestClient is used without a `with` block so app startup events (which would
reconfigure paths) do not fire.
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


class DocumentVaultsRouteTests(unittest.TestCase):
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

    def test_slash_named_vault_round_trips_create_and_delete(self) -> None:
        name = "Apex / Northwind"
        created = self.client.post("/api/vaults", json={"name": name})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertIn(name, created.json()["vaults"])

        # The name travels as a query param; the client URL-encodes the slash.
        deleted = self.client.delete("/api/vaults", params={"name": name})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), {"deleted": True})
        self.assertNotIn(name, self.client.get("/api/vaults").json()["vaults"])

    def test_delete_refuses_a_vault_that_still_holds_records(self) -> None:
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
                "VALUES ('d1', 'contract.pdf', 'pdf', 'ready', 'upload', 'Occupied')"
            )
            conn.commit()
        refused = self.client.delete("/api/vaults", params={"name": "Occupied"})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("Occupied", self.client.get("/api/vaults").json()["vaults"])

    def test_delete_of_a_never_registered_vault_is_404_not_a_crash(self) -> None:
        response = self.client.delete("/api/vaults", params={"name": "Never Existed"})
        self.assertEqual(response.status_code, 404, response.text)

    def test_create_rejects_a_whitespace_only_name_with_400(self) -> None:
        response = self.client.post("/api/vaults", json={"name": "   "})
        self.assertEqual(response.status_code, 400, response.text)

    def test_create_rejects_a_traversal_sequence_with_400(self) -> None:
        response = self.client.post("/api/vaults", json={"name": "../etc"})
        self.assertEqual(response.status_code, 400, response.text)

    def test_create_rejects_a_leading_dot_with_400(self) -> None:
        response = self.client.post("/api/vaults", json={"name": ".hidden"})
        self.assertEqual(response.status_code, 400, response.text)

    def test_create_rejects_an_over_long_name(self) -> None:
        # CreateVaultRequest.name caps at 120 chars; FastAPI/Pydantic rejects
        # this before it ever reaches create_vault, with a 422 (still a clear
        # 4xx, never a 500).
        response = self.client.post("/api/vaults", json={"name": "x" * 121})
        self.assertEqual(response.status_code, 422, response.text)

    def test_create_list_delete_happy_path_round_trip(self) -> None:
        name = "Roundtrip Matter"
        created = self.client.post("/api/vaults", json={"name": name})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertIn(name, created.json()["vaults"])

        listed = self.client.get("/api/vaults")
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertIn(name, listed.json()["vaults"])

        deleted = self.client.delete("/api/vaults", params={"name": name})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), {"deleted": True})
        self.assertNotIn(name, self.client.get("/api/vaults").json()["vaults"])

    def test_list_vaults_is_a_well_formed_empty_result_when_none_exist(self) -> None:
        response = self.client.get("/api/vaults")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"vaults": []})

    def test_create_of_a_duplicate_name_is_idempotent_not_an_error(self) -> None:
        # Duplicate create is a deliberate no-op (see create_vault's docstring),
        # never a 500 and never a blank body: the second call answers 200 with
        # the same well-formed vault list, not a new entry and not a crash.
        name = "Repeat Matter"
        first = self.client.post("/api/vaults", json={"name": name})
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post("/api/vaults", json={"name": name})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(
            [v for v in second.json()["vaults"] if v == name],
            [name],
        )


if __name__ == "__main__":
    unittest.main()
