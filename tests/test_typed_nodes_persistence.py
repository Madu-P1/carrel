"""Round-trip tests for the typed-node persistence helpers + FTS triggers.

Only exercises the SQL layer — no Docling required. Verifies that
migration 0016 lands the right shape, that the helpers respect it, and
that the FTS triggers stay in sync on insert / update / delete.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.documents import delete_document_record
from services.ingestion.persistence import (
    delete_typed_nodes,
    embed_and_index_nodes,
    insert_typed_nodes,
    node_embeddings_table_exists,
)
from services.ingestion.typed_walker import TypedNode

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _DeterministicEmbedder:
    """Deterministic 384-dim embedder so we don't drag fastembed into unit tests."""

    dim = 384

    def _vec(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text) or 1
        return [((seed + i) % 7) / 7.0 for i in range(self.dim)]

    def embed_passages(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _make_node(order: int, *, node_type: str = "body", text: str | None = None) -> TypedNode:
    body = text if text is not None else f"Body paragraph #{order}"
    return TypedNode(
        node_type=node_type,
        heading_path="",
        page=1,
        char_start=order * 100,
        char_end=order * 100 + len(body),
        verbatim_text=body,
        parent_block_id=None,
        reading_order=order,
    )


class TypedNodesPersistenceTests(unittest.TestCase):
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
        # Seed a documents row so the nodes FK has a target.
        self._doc_id = "doc-typed-nodes-test"
        self._conn.execute(
            """
            INSERT INTO documents (id, filename, file_type, status, source_kind)
            VALUES (?, 'fixture.md', 'md', 'ready', 'manual_text')
            """,
            (self._doc_id,),
        )
        self._conn.commit()

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

    def test_insert_returns_row_ids_in_reading_order(self) -> None:
        nodes = [_make_node(i) for i in range(3)]
        ids = insert_typed_nodes(self._conn, self._doc_id, nodes)
        self.assertEqual(len(ids), 3)
        self.assertEqual(ids, sorted(ids))  # SQLite issues monotonic rowids

        rows = self._conn.execute(
            "SELECT reading_order, verbatim_text FROM nodes WHERE doc_id = ? ORDER BY reading_order",
            (self._doc_id,),
        ).fetchall()
        self.assertEqual([r["reading_order"] for r in rows], [0, 1, 2])

    def test_fts_trigger_fires_on_insert_and_delete(self) -> None:
        nodes = [_make_node(0, text="photosynthesis splits water in chloroplasts")]
        insert_typed_nodes(self._conn, self._doc_id, nodes)
        # FTS5 MATCH against the inserted text — proves the insert trigger fired.
        hit = self._conn.execute(
            "SELECT id FROM node_fts WHERE node_fts MATCH 'chloroplasts'"
        ).fetchone()
        self.assertIsNotNone(hit)

        delete_typed_nodes(self._conn, self._doc_id)
        miss = self._conn.execute(
            "SELECT id FROM node_fts WHERE node_fts MATCH 'chloroplasts'"
        ).fetchone()
        self.assertIsNone(miss)

    def test_fts_trigger_fires_on_update(self) -> None:
        nodes = [_make_node(0, text="initial body content")]
        ids = insert_typed_nodes(self._conn, self._doc_id, nodes)
        self._conn.execute(
            "UPDATE nodes SET verbatim_text = ? WHERE id = ?",
            ("revised polymerase content", ids[0]),
        )
        miss = self._conn.execute(
            "SELECT id FROM node_fts WHERE node_fts MATCH 'initial'"
        ).fetchone()
        self.assertIsNone(miss)
        hit = self._conn.execute(
            "SELECT id FROM node_fts WHERE node_fts MATCH 'polymerase'"
        ).fetchone()
        self.assertIsNotNone(hit)

    def test_delete_typed_nodes_clears_orphan_embeddings(self) -> None:
        if not node_embeddings_table_exists(self._conn):
            self.skipTest("sqlite-vec not loaded in this runtime")
        nodes = [_make_node(0)]
        ids = insert_typed_nodes(self._conn, self._doc_id, nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=_DeterministicEmbedder())

        before = self._conn.execute("SELECT COUNT(*) AS n FROM node_embeddings").fetchone()["n"]
        self.assertEqual(before, 1)
        delete_typed_nodes(self._conn, self._doc_id)
        after = self._conn.execute("SELECT COUNT(*) AS n FROM node_embeddings").fetchone()["n"]
        self.assertEqual(after, 0)

    def test_delete_document_record_removes_typed_nodes_and_embeddings(self) -> None:
        nodes = [_make_node(0, text="private deletion sentinel")]
        ids = insert_typed_nodes(self._conn, self._doc_id, nodes)
        if node_embeddings_table_exists(self._conn):
            embed_and_index_nodes(self._conn, nodes, ids, embedder=_DeterministicEmbedder())

        self.assertTrue(delete_document_record(self._conn, self._doc_id))

        node_count = self._conn.execute(
            "SELECT COUNT(*) AS n FROM nodes WHERE doc_id = ?",
            (self._doc_id,),
        ).fetchone()["n"]
        self.assertEqual(node_count, 0)
        fts_hit = self._conn.execute(
            "SELECT id FROM node_fts WHERE node_fts MATCH 'sentinel'"
        ).fetchone()
        self.assertIsNone(fts_hit)
        if node_embeddings_table_exists(self._conn):
            embedding_count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM node_embeddings WHERE node_id IN (%s)"
                % ",".join("?" for _ in ids),
                ids,
            ).fetchone()["n"]
            self.assertEqual(embedding_count, 0)

    def test_embed_and_index_skips_excluded_node_types(self) -> None:
        if not node_embeddings_table_exists(self._conn):
            self.skipTest("sqlite-vec not loaded in this runtime")
        # `header` and `footer` are page chrome — never embedded.
        nodes = [
            _make_node(0, node_type="header", text="page 12"),
            _make_node(1, node_type="footer", text="copyright 2026"),
            _make_node(2, node_type="body", text="actual body content"),
        ]
        ids = insert_typed_nodes(self._conn, self._doc_id, nodes)
        embedded = embed_and_index_nodes(self._conn, nodes, ids, embedder=_DeterministicEmbedder())
        self.assertEqual(embedded, 1)  # only the body row
        rowids = {
            row["node_id"]
            for row in self._conn.execute("SELECT node_id FROM node_embeddings").fetchall()
        }
        self.assertEqual(rowids, {ids[2]})

    def test_inserting_invalid_node_type_is_rejected_by_check_constraint(self) -> None:
        # The CHECK constraint on `node_type` is the schema's safety net
        # against a future walker bug emitting a typo. Verify it fires.
        bogus = TypedNode(
            node_type="not-a-real-type",
            heading_path="",
            page=None,
            char_start=0,
            char_end=4,
            verbatim_text="halt",
            parent_block_id=None,
            reading_order=0,
        )
        with self.assertRaises(Exception):
            insert_typed_nodes(self._conn, self._doc_id, [bogus])


if __name__ == "__main__":
    unittest.main()
