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

    def test_traversal_segment_rejected_but_dotted_caption_survives(self) -> None:
        # '..' is rejected only as a path SEGMENT (the delete-route traversal
        # risk), not as a raw substring, so a real caption with an ellipsis or
        # trailing dots survives while an actual traversal is refused.
        for legit in ("Estate of Smith, et al...", "Acme v. Beta ...continued", "Version 2.1..2.3"):
            # Must not raise; returns a non-empty canonical name.
            self.assertTrue(create_vault(self.conn, legit))
        for traversal in ("..", "../secrets", "vault/../etc", "a\\..\\b"):
            with self.assertRaises(ValueError):
                create_vault(self.conn, traversal)

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
        # delete of "   " would silently forget the General vault. It must refuse
        # loudly (ValueError -> 400 at the route), distinct from the in-use 409.
        create_vault(self.conn, "General")
        with self.assertRaises(ValueError):
            delete_vault(self.conn, "   ")
        with self.assertRaises(ValueError):
            delete_vault(self.conn, "")
        self.assertIn("General", list_vault_names(self.conn))

    def test_delete_is_case_insensitive_like_the_rest_of_vault_identity(self) -> None:
        # A record filed under a case-variant must still block the delete: the
        # binary compare missed it, removed the registry row, and reported True
        # past the "never forget a vault that holds records" invariant.
        create_vault(self.conn, "Client Files")
        self._file_doc("d3", "client files")
        self.assertFalse(delete_vault(self.conn, "Client Files"))
        self.assertIn("Client Files", list_vault_names(self.conn))

        # And deleting an EMPTY vault by a case-variant removes the registry row
        # instead of silently missing it while reporting success.
        create_vault(self.conn, "Archives")
        self.assertTrue(delete_vault(self.conn, "archives"))
        self.assertNotIn("Archives", list_vault_names(self.conn))

    def test_delete_of_an_unknown_vault_is_a_lookup_error_not_a_false_success(self) -> None:
        # The old code reported {"deleted": true} for a name that was never
        # registered and holds nothing; the route now answers 404.
        with self.assertRaises(LookupError):
            delete_vault(self.conn, "Never Existed")

    def test_create_rejects_an_empty_string_name(self) -> None:
        with self.assertRaises(ValueError):
            create_vault(self.conn, "")

    def test_create_rejects_a_traversal_sequence(self) -> None:
        with self.assertRaises(ValueError):
            create_vault(self.conn, "..")
        with self.assertRaises(ValueError):
            create_vault(self.conn, "Case/../../etc")

    def test_create_rejects_a_leading_dot(self) -> None:
        with self.assertRaises(ValueError):
            create_vault(self.conn, ".hidden")

    def test_create_rejects_a_name_over_the_length_bound(self) -> None:
        from services.documents import VAULT_NAME_MAX_LENGTH

        with self.assertRaises(ValueError):
            create_vault(self.conn, "x" * (VAULT_NAME_MAX_LENGTH + 1))
        # The bound itself is still accepted.
        at_bound = "x" * VAULT_NAME_MAX_LENGTH
        self.assertEqual(create_vault(self.conn, at_bound), at_bound)

    def test_create_permits_a_slash_because_vault_names_are_not_filesystem_paths(self) -> None:
        # 'Apex / Northwind' is a real consolidated-case caption, not a path
        # traversal attempt; document_vaults.name is a DB column, never a path
        # segment. Locks the deliberate decision NOT to reject '/' or '\'.
        name = "Apex / Northwind"
        self.assertEqual(create_vault(self.conn, name), name)
        self.assertIn(name, list_vault_names(self.conn))

    def test_create_still_treats_a_duplicate_name_as_idempotent_not_an_error(self) -> None:
        # create_vault is documented as idempotent on an existing name; the
        # new validation must not turn that into a rejection.
        self.assertEqual(create_vault(self.conn, "Repeat"), "Repeat")
        self.assertEqual(create_vault(self.conn, "Repeat"), "Repeat")
        self.assertEqual([v for v in list_vault_names(self.conn) if v == "Repeat"], ["Repeat"])

    def test_create_list_delete_happy_path_round_trip(self) -> None:
        name = "Roundtrip Matter"
        self.assertEqual(create_vault(self.conn, name), name)
        self.assertIn(name, list_vault_names(self.conn))
        self.assertTrue(delete_vault(self.conn, name))
        self.assertNotIn(name, list_vault_names(self.conn))

    def test_list_vault_names_is_a_well_formed_empty_list_when_none_exist(self) -> None:
        # No registry rows, no filed documents: the union is empty, not None
        # and not an error, so the UI can render an empty state cleanly.
        self.assertEqual(list_vault_names(self.conn), [])


if __name__ == "__main__":
    unittest.main()
