from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services import tutor as tutor_service
from services.note_sanitizer import sanitize_existing_notes, sanitize_note_html

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class NoteSanitizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (
            db.BASE_DIR,
            db.DATA_DIR,
            db.UPLOAD_DIR,
            db.DB_PATH,
            db.SCHEMA_PATH,
        )
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        data_dir.mkdir(parents=True, exist_ok=True)
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
        self._conn = db.get_db()
        db.apply_migrations(self._conn)

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0],
            data_dir=self._original[1],
            upload_dir=self._original[2],
            db_path=self._original[3],
            schema_path=self._original[4],
        )

    def test_sanitize_note_html_drops_executable_markup(self) -> None:
        clean = sanitize_note_html(
            """
            <p onclick="steal()">Keep <strong>this</strong></p>
            <img src=x onerror="fetch('//evil')">
            <svg onload="alert(1)"><text>bad</text></svg>
            <script>alert(window.__CARREL_LOCAL_API_TOKEN)</script>
            <a href="javascript:alert(1)">link text</a>
            """
        )

        self.assertIn("<strong>this</strong>", clean)
        self.assertIn("link text", clean)
        self.assertNotIn("onclick", clean)
        self.assertNotIn("onerror", clean)
        self.assertNotIn("<img", clean)
        self.assertNotIn("<svg", clean)
        self.assertNotIn("<script", clean)
        self.assertNotIn("javascript:", clean)

    def test_note_upsert_and_fetch_return_sanitized_content(self) -> None:
        note = tutor_service.upsert_note_record(
            self._conn,
            note_id=None,
            doc_id=None,
            concept_id=None,
            title="Unsafe note",
            content='<p>safe</p><img src=x onerror="steal()"><script>bad()</script>',
            source_snippet=None,
            note_type="session_note",
        )

        self.assertEqual(note["content"], "<p>safe</p>")
        stored = self._conn.execute(
            "SELECT content FROM notes WHERE id = ?", (note["id"],)
        ).fetchone()
        self.assertEqual(stored["content"], "<p>safe</p>")
        fetched = tutor_service.fetch_notes(self._conn, limit=10)
        self.assertEqual(fetched[0]["content"], "<p>safe</p>")

    def test_sanitize_existing_notes_repairs_legacy_rows(self) -> None:
        self._conn.executemany(
            """
            INSERT INTO notes (id, title, content, note_type)
            VALUES (?, 'Legacy', ?, 'session_note')
            """,
            [
                ("legacy-xss-1", '<p>ok</p><img src=x onerror="steal()">'),
                ("legacy-xss-2", "<p>also ok</p><script>bad()</script>"),
            ],
        )
        self._conn.commit()

        changed = sanitize_existing_notes(self._conn, batch_size=1)

        self.assertEqual(changed, 2)
        rows = self._conn.execute("SELECT id, content FROM notes ORDER BY id").fetchall()
        self.assertEqual(
            [(row["id"], row["content"]) for row in rows],
            [
                ("legacy-xss-1", "<p>ok</p>"),
                ("legacy-xss-2", "<p>also ok</p>"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
