"""Tests for the Phase 2 global Notes page backend.

Covers migration 0020 (the schema bits), the folder CRUD route layer
(`/api/notes/folders` + the composite organization payload), and the
COALESCE-based subject resolution that powers the global page's rail.

These tests bootstrap a real SQLite database against a temporary
directory the way `test_learning_os.py` does so the migration runs end
to end and the queries hit actual rows.
"""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException

import main
from api_models import (
    NoteFolderCreateRequest,
    NoteFolderUpdateRequest,
    NoteMoveRequest,
    NoteUpsertRequest,
)
from routes.tutor import (
    create_note_folder,
    delete_note_folder,
    get_notes,
    get_notes_organization,
    list_note_folders,
    move_note,
    save_note,
    update_note_folder,
)


class NoteFoldersTests(unittest.TestCase):
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
        main.DB_PATH = main.DATA_DIR / "test.db"
        main.initialize_database()

    def tearDown(self) -> None:
        main.BASE_DIR = self.original_base_dir
        main.DATA_DIR = self.original_data_dir
        main.UPLOAD_DIR = self.original_upload_dir
        main.DB_PATH = self.original_db_path
        main.SCHEMA_PATH = self.original_schema_path
        self.temp_dir.cleanup()

    # ---- helpers ----------------------------------------------------

    def _seed_document(self, filename: str, subject: str) -> str:
        doc_id = str(uuid.uuid4())
        with main.get_db() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, filename, file_type, subject_name, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc_id, filename, "pdf", subject, "ready"),
            )
            conn.commit()
        return doc_id

    def _save_note(
        self,
        content: str,
        doc_id: str | None = None,
        folder_id: str | None = None,
    ) -> str:
        response = save_note(
            NoteUpsertRequest(
                doc_id=doc_id,
                title="Note",
                content=content,
                folder_id=folder_id,
                note_type="reader_note",
            )
        )
        return response["note"]["id"]

    # ---- migration shape -------------------------------------------

    def test_migration_creates_folder_table_and_column(self) -> None:
        with main.get_db() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            notes_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(notes)").fetchall()
            }
            folder_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(note_folders)").fetchall()
            }

        self.assertIn("note_folders", tables)
        self.assertIn("folder_id", notes_columns)
        self.assertTrue(
            {"id", "name", "subject_name", "sort_order", "created_at", "updated_at"}
            <= folder_columns
        )

    # ---- folder CRUD ------------------------------------------------

    def test_create_folder_persists_with_subject(self) -> None:
        result = create_note_folder(
            NoteFolderCreateRequest(name="Lecture notes", subject_name="Math")
        )
        folder = result["folder"]
        self.assertEqual("Lecture notes", folder["name"])
        self.assertEqual("Math", folder["subject_name"])
        self.assertEqual(0, folder["sort_order"])
        self.assertIsNotNone(folder["id"])

        listed = list_note_folders(subject_name="Math")["folders"]
        self.assertEqual(1, len(listed))
        self.assertEqual(folder["id"], listed[0]["id"])

    def test_create_folder_rejects_empty_name(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            create_note_folder(
                NoteFolderCreateRequest.model_construct(name="   ", subject_name="Math")
            )
        self.assertEqual(400, ctx.exception.status_code)

    def test_update_folder_renames_and_reclassifies(self) -> None:
        created = create_note_folder(NoteFolderCreateRequest(name="Lecture", subject_name="Math"))[
            "folder"
        ]
        # Rename + reclassify in one call so we know both fields patch.
        updated = update_note_folder(
            created["id"],
            NoteFolderUpdateRequest(name="Lecture notes", subject_name="Physics"),
        )["folder"]
        self.assertEqual("Lecture notes", updated["name"])
        self.assertEqual("Physics", updated["subject_name"])

    def test_update_folder_404_on_unknown_id(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            update_note_folder(
                "does-not-exist",
                NoteFolderUpdateRequest(name="Whatever"),
            )
        self.assertEqual(404, ctx.exception.status_code)

    def test_delete_folder_clears_folder_id_on_notes(self) -> None:
        doc_id = self._seed_document("biology.pdf", "Biology")
        folder = create_note_folder(
            NoteFolderCreateRequest(name="Open questions", subject_name="Biology")
        )["folder"]
        note_id = self._save_note(
            content="Why is osmosis spontaneous?",
            doc_id=doc_id,
            folder_id=folder["id"],
        )

        result = delete_note_folder(folder["id"])
        self.assertTrue(result["deleted"])

        # The note survives and falls back to the document's subject.
        notes = get_notes(limit=50)["notes"]
        match = next(n for n in notes if n["id"] == note_id)
        self.assertIsNone(match["folder_id"])
        self.assertEqual("Biology", match["subject"])

    # ---- subject resolution + filters -------------------------------

    def test_subject_resolves_via_folder_then_document_then_unfiled(self) -> None:
        math_doc = self._seed_document("calc.pdf", "Math")
        physics_folder = create_note_folder(
            NoteFolderCreateRequest(name="Lab notes", subject_name="Physics")
        )["folder"]

        # Three notes covering the COALESCE rule's three branches.
        foldered = self._save_note("Foldered note", doc_id=math_doc, folder_id=physics_folder["id"])
        doc_only = self._save_note("Doc-only note", doc_id=math_doc)
        orphan = self._save_note("Orphan note")

        by_id = {n["id"]: n for n in get_notes(limit=50)["notes"]}

        # Folder wins over document — note moved into a Physics folder
        # from a Math document reads as Physics.
        self.assertEqual("Physics", by_id[foldered]["subject"])
        self.assertEqual("Math", by_id[doc_only]["subject"])
        self.assertEqual("Unfiled", by_id[orphan]["subject"])

    def test_subject_filter_returns_only_matching_notes(self) -> None:
        math_doc = self._seed_document("calc.pdf", "Math")
        bio_doc = self._seed_document("bio.pdf", "Biology")
        self._save_note("Math 1", doc_id=math_doc)
        self._save_note("Math 2", doc_id=math_doc)
        self._save_note("Bio 1", doc_id=bio_doc)
        self._save_note("Orphan")

        math_notes = get_notes(subject_name="Math", limit=50)["notes"]
        self.assertEqual({"Math 1", "Math 2"}, {n["content"] for n in math_notes})

        unfiled = get_notes(subject_name="Unfiled", limit=50)["notes"]
        self.assertEqual({"Orphan"}, {n["content"] for n in unfiled})

    def test_folder_id_none_filter_returns_only_unfoldered_notes(self) -> None:
        math_doc = self._seed_document("calc.pdf", "Math")
        folder = create_note_folder(
            NoteFolderCreateRequest(name="Cards to make", subject_name="Math")
        )["folder"]
        self._save_note("In folder", doc_id=math_doc, folder_id=folder["id"])
        self._save_note("Loose Math note", doc_id=math_doc)

        unfoldered = get_notes(folder_id="none", limit=50)["notes"]
        self.assertEqual({"Loose Math note"}, {n["content"] for n in unfoldered})

    def test_move_note_updates_folder_and_subject(self) -> None:
        bio_doc = self._seed_document("bio.pdf", "Biology")
        math_folder = create_note_folder(
            NoteFolderCreateRequest(name="Lectures", subject_name="Math")
        )["folder"]

        note_id = self._save_note("Cell membranes", doc_id=bio_doc)

        # Move into a Math folder. Folder subject overrides doc subject.
        moved = move_note(note_id, NoteMoveRequest(folder_id=math_folder["id"]))["note"]
        self.assertEqual(math_folder["id"], moved["folder_id"])
        self.assertEqual("Math", moved["subject"])

        # Unfile: folder_id back to None, subject falls back to the doc.
        unfiled = move_note(note_id, NoteMoveRequest(folder_id=None))["note"]
        self.assertIsNone(unfiled["folder_id"])
        self.assertEqual("Biology", unfiled["subject"])

    def test_move_note_rejects_unknown_folder(self) -> None:
        note_id = self._save_note("Orphan note")
        with self.assertRaises(HTTPException) as ctx:
            move_note(note_id, NoteMoveRequest(folder_id="ghost"))
        self.assertEqual(400, ctx.exception.status_code)

    def test_move_note_404_on_unknown_note(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            move_note("nope", NoteMoveRequest(folder_id=None))
        self.assertEqual(404, ctx.exception.status_code)

    def test_save_note_rejects_invalid_folder_id(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            save_note(
                NoteUpsertRequest(
                    content="Will fail",
                    folder_id="not-a-real-folder",
                    note_type="reader_note",
                )
            )
        self.assertEqual(400, ctx.exception.status_code)

    # ---- organization payload --------------------------------------

    def test_organization_payload_groups_subjects_with_folder_counts(self) -> None:
        math_doc = self._seed_document("calc.pdf", "Math")
        bio_doc = self._seed_document("bio.pdf", "Biology")
        math_folder = create_note_folder(
            NoteFolderCreateRequest(name="Lectures", subject_name="Math")
        )["folder"]
        # 2 in Math folder, 1 unfoldered Math note, 1 Biology note, 1 orphan.
        self._save_note("M1", doc_id=math_doc, folder_id=math_folder["id"])
        self._save_note("M2", doc_id=math_doc, folder_id=math_folder["id"])
        self._save_note("M3", doc_id=math_doc)
        self._save_note("B1", doc_id=bio_doc)
        self._save_note("Orphan")

        payload = get_notes_organization()
        by_name = {s["name"]: s for s in payload["subjects"]}

        self.assertEqual({"Biology", "Math", "Unfiled"}, set(by_name.keys()))
        self.assertEqual(3, by_name["Math"]["note_count"])
        self.assertEqual(1, by_name["Biology"]["note_count"])
        self.assertEqual(1, by_name["Unfiled"]["note_count"])

        math_folders = by_name["Math"]["folders"]
        self.assertEqual(1, len(math_folders))
        self.assertEqual("Lectures", math_folders[0]["name"])
        self.assertEqual(2, math_folders[0]["note_count"])

        # Unfiled always sorts to the end so it doesn't get lost between
        # real subjects alphabetically.
        self.assertEqual("Unfiled", payload["subjects"][-1]["name"])


if __name__ == "__main__":
    unittest.main()
