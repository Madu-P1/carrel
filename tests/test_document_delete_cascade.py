"""Regression: deleting a document leaves no orphaned rows.

The Vault upgrade (2026-06-08) exposes document deletion in the UI, so the
cascade has to be correct: `PRAGMA foreign_keys` is OFF on these connections
(db.py sets WAL/busy_timeout/synchronous only), which means the schema's
`ON DELETE CASCADE` never fires and every child must be removed by hand. This
test inserts a document plus one row in each document-scoped child table, deletes
it, and asserts the tables are swept clean and a sibling's `duplicate_of` pointer
is cleared without the sibling itself being touched.

Scope note: the Carrel tutor concept-graph (concepts -> questions/cards/notes and
their junction tables: quiz_log, review_events, flashcard_evidence, ...) is a
separate, pre-existing cascade that a Cachet-ingested record never populates (it
carries no concepts), so it is intentionally out of scope here. See the comment
in services.documents.delete_document_record.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.documents import delete_document_record
from services.ingestion.persistence import node_embeddings_table_exists

MIGRATIONS_SOURCE = Path(__file__).resolve().parents[1] / "migrations"


class DeleteDocumentCascadeTest(unittest.TestCase):
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

    def _count(self, sql: str, *params: object) -> int:
        return int(self.conn.execute(sql, params).fetchone()[0])

    def test_delete_sweeps_every_document_scoped_child(self) -> None:
        c = self.conn
        c.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('d1', 'contract.pdf', 'pdf', 'ready', 'upload', 'Vault')"
        )
        # A second document whose duplicate_of points at the one we delete.
        c.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name, duplicate_of) "
            "VALUES ('d2', 'dup.pdf', 'pdf', 'ready', 'upload', 'Vault', 'd1')"
        )
        c.execute("INSERT INTO chunks (id, doc_id, content) VALUES ('ch1', 'd1', 'hello world')")
        c.execute(
            "INSERT INTO nodes (doc_id, node_type, char_start, char_end, verbatim_text, reading_order) "
            "VALUES ('d1', 'body', 0, 11, 'hello world', 0)"
        )
        node_id = int(c.execute("SELECT id FROM nodes WHERE doc_id = 'd1'").fetchone()[0])
        c.execute(
            "INSERT INTO anchors (id, document_id, quote_text, origin) "
            "VALUES ('an1', 'd1', 'hello', 'manual')"
        )
        c.execute(
            "INSERT INTO evidence_references (id, source_id, anchor_text) VALUES ('ev1', 'd1', 'hello')"
        )
        c.execute(
            "INSERT INTO stale_dependencies (id, source_id, dependent_kind, dependent_id, source_snapshot_hash) "
            "VALUES ('st1', 'd1', 'chunk', 'ch1', 'snap-abc')"
        )
        # These two carry a doc pointer the schema marks ON DELETE SET NULL. With FK
        # off, the delete must null the pointer by hand WITHOUT deleting the row.
        c.execute(
            "INSERT INTO study_suggestions "
            "(id, kind, start_at, end_at, doc_id, reason_code, reason_text) "
            "VALUES ('ss1', 'study_block', '2026-06-08T10:00', '2026-06-08T11:00', 'd1', "
            "'free_block_overdue_srs', 'reason')"
        )
        c.execute(
            "INSERT INTO ingestion_jobs (id, status, stage, filename, document_id) "
            "VALUES ('ij1', 'ready', 'ready', 'contract.pdf', 'd1')"
        )
        has_vec = node_embeddings_table_exists(c)
        if has_vec:
            c.execute(
                "INSERT INTO node_embeddings (node_id, embedding) VALUES (?, ?)",
                (node_id, json.dumps([0.0] * 384)),
            )
        c.commit()

        self.assertTrue(delete_document_record(c, "d1"))

        # The document and every child scoped to it are gone.
        self.assertEqual(self._count("SELECT COUNT(*) FROM documents WHERE id = 'd1'"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM chunks WHERE doc_id = 'd1'"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM nodes WHERE doc_id = 'd1'"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM anchors WHERE document_id = 'd1'"), 0)
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM evidence_references WHERE source_id = 'd1'"), 0
        )
        self.assertEqual(
            self._count("SELECT COUNT(*) FROM stale_dependencies WHERE source_id = 'd1'"), 0
        )
        # node_fts is trigger-maintained off `nodes`; it must follow the delete.
        self.assertEqual(self._count("SELECT COUNT(*) FROM node_fts WHERE doc_id = 'd1'"), 0)
        if has_vec:
            self.assertEqual(
                self._count("SELECT COUNT(*) FROM node_embeddings WHERE node_id = ?", node_id), 0
            )

        # The sibling survives, but its dangling duplicate pointer is cleared.
        self.assertEqual(self._count("SELECT COUNT(*) FROM documents WHERE id = 'd2'"), 1)
        self.assertIsNone(
            c.execute("SELECT duplicate_of FROM documents WHERE id = 'd2'").fetchone()[0]
        )

        # The SET NULL rows survive with their doc pointer cleared, not deleted.
        self.assertEqual(self._count("SELECT COUNT(*) FROM study_suggestions WHERE id = 'ss1'"), 1)
        self.assertIsNone(
            c.execute("SELECT doc_id FROM study_suggestions WHERE id = 'ss1'").fetchone()[0]
        )
        self.assertEqual(self._count("SELECT COUNT(*) FROM ingestion_jobs WHERE id = 'ij1'"), 1)
        self.assertIsNone(
            c.execute("SELECT document_id FROM ingestion_jobs WHERE id = 'ij1'").fetchone()[0]
        )

    def test_delete_missing_document_returns_false(self) -> None:
        self.assertFalse(delete_document_record(self.conn, "does-not-exist"))


if __name__ == "__main__":
    unittest.main()
