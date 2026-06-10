"""The document_vaults registry: vaults persist even when empty (folder-first
creation), the vault list is the union of filed subjects and the registry, and a
vault that still holds records cannot be forgotten."""

import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.documents import create_vault, delete_vault, list_vault_names

MIGRATIONS_SOURCE = Path(__file__).resolve().parents[1] / "migrations"


class DocumentVaultsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root,
            data_dir=data_dir,
            upload_dir=data_dir / "uploads",
            db_path=data_dir / "test.db",
            schema_path=root / "schema.sql",
        )
        self.conn = db.get_db()
        db.apply_migrations(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def _file_doc(self, doc_id: str, subject: str) -> None:
        self.conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES (?, ?, 'pdf', 'ready', 'upload', ?)",
            (doc_id, f"{doc_id}.pdf", subject),
        )
        self.conn.commit()

    def test_empty_vault_persists_and_lists_union_of_registry_and_filed_subjects(self) -> None:
        # A folder created before any record exists, persisted in the registry.
        self.assertEqual(create_vault(self.conn, "Apex v. Northwind"), "Apex v. Northwind")
        # A vault implied purely by a filed record, with no registry row.
        self._file_doc("d1", "Henderson Matter")

        vaults = list_vault_names(self.conn)
        self.assertIn("Apex v. Northwind", vaults)  # empty, from the registry
        self.assertIn("Henderson Matter", vaults)  # implied by a record

    def test_create_vault_is_idempotent_and_rejects_an_empty_name(self) -> None:
        create_vault(self.conn, "Same")
        create_vault(self.conn, "Same")
        self.assertEqual([v for v in list_vault_names(self.conn) if v == "Same"], ["Same"])
        with self.assertRaises(ValueError):
            create_vault(self.conn, "   ")

    def test_delete_forgets_an_empty_vault_but_refuses_one_that_holds_records(self) -> None:
        create_vault(self.conn, "Empty")
        self.assertTrue(delete_vault(self.conn, "Empty"))
        self.assertNotIn("Empty", list_vault_names(self.conn))

        # A vault with a record cannot be forgotten (records would be orphaned).
        self._file_doc("d2", "Occupied")
        self.assertFalse(delete_vault(self.conn, "Occupied"))
        self.assertIn("Occupied", list_vault_names(self.conn))

    def test_vault_identity_is_case_insensitive(self) -> None:
        # Creating a case-variant of an existing vault resolves to the existing
        # spelling rather than forking a duplicate folder.
        self.assertEqual(create_vault(self.conn, "General"), "General")
        self.assertEqual(create_vault(self.conn, "general"), "General")
        self.assertEqual(
            [v for v in list_vault_names(self.conn) if v.lower() == "general"], ["General"]
        )
        # A record filed under yet another casing still collapses under the
        # registry's canonical spelling in the list.
        self._file_doc("d9", "GENERAL")
        self.assertEqual(
            [v for v in list_vault_names(self.conn) if v.lower() == "general"], ["General"]
        )

    def test_delete_refuses_a_blank_name_rather_than_targeting_general(self) -> None:
        # normalize_subject_name defaults a blank to 'General', so an unguarded
        # delete of "   " would silently forget the General vault. It must refuse.
        create_vault(self.conn, "General")
        self.assertFalse(delete_vault(self.conn, "   "))
        self.assertFalse(delete_vault(self.conn, ""))
        self.assertIn("General", list_vault_names(self.conn))


if __name__ == "__main__":
    unittest.main()
