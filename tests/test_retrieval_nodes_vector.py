"""Integration tests for vec0 kNN search against `node_embeddings`.

Uses a deterministic embedder (no fastembed dependency) so the tests
are fast and reproducible. Skips wholesale when sqlite-vec isn't
loaded at runtime — the migration is gated the same way.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services.ingestion.persistence import (
    embed_and_index_nodes,
    insert_typed_nodes,
)
from services.ingestion.typed_walker import TypedNode
from services.retrieval.nodes_vector import (
    node_vector_table_exists,
    search_node_vectors,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _DeterministicEmbedder:
    """Hashed bag-of-tokens embedder so retrieval is repeatable.

    Maps each token to a 384-dim signature derived from its sha256
    digest, then averages signatures across the input string and
    L2-normalises. Cosine distance ranks matching texts close
    together without any model download.
    """

    dim = 384

    def _vec_for(self, text: str) -> list[float]:
        tokens = [t.lower() for t in text.split() if t]
        if not tokens:
            return [0.0] * self.dim
        accum = [0.0] * self.dim
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(self.dim):
                accum[i] += ((digest[i % len(digest)] / 255.0) * 2.0) - 1.0
        norm = math.sqrt(sum(v * v for v in accum)) or 1.0
        return [v / norm for v in accum]

    def embed_passages(self, texts):
        return [self._vec_for(t) for t in texts]

    def embed_query(self, text):
        return self._vec_for(text)


def _node(order: int, *, node_type: str = "body", text: str = "") -> TypedNode:
    return TypedNode(
        node_type=node_type,
        heading_path="Topic",
        page=1,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


@unittest.skipUnless(db.sqlite_vec_runtime_supported(), "sqlite-vec runtime not available")
class NodesVectorSearchTests(unittest.TestCase):
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
        self._embedder = _DeterministicEmbedder()
        self._seed_corpus()

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

    def _seed_corpus(self) -> None:
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-1', 'a.md', 'md', 'ready', 'manual_text', 'Topic')"
        )
        nodes = [
            _node(0, node_type="body", text="photosynthesis happens in chloroplasts"),
            _node(1, node_type="body", text="rivers carve canyons over geological timescales"),
            _node(2, node_type="footer", text="page 14 of textbook"),
        ]
        ids = insert_typed_nodes(self._conn, "doc-1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def test_node_embeddings_table_present_after_migrations(self) -> None:
        self.assertTrue(node_vector_table_exists(self._conn))

    def test_query_returns_typed_metadata(self) -> None:
        hits = search_node_vectors(
            self._conn,
            "photosynthesis chloroplasts",
            embedder=self._embedder,
        )
        self.assertTrue(hits)
        top = hits[0]
        # Top hit should be the photosynthesis body row, not the river row.
        self.assertIn("chloroplasts", top.verbatim_text)
        self.assertEqual(top.heading_path, "Topic")
        self.assertEqual(top.page, 1)

    def test_returns_empty_for_blank_query(self) -> None:
        self.assertEqual(search_node_vectors(self._conn, "  ", embedder=self._embedder), [])

    def test_node_type_filter_excludes_footers(self) -> None:
        # Footers were never embedded (the persistence helper excludes
        # them) but the filter is still in the SQL. Pass an explicit
        # allowlist that includes only body — footer must not appear.
        hits = search_node_vectors(
            self._conn,
            "page",
            embedder=self._embedder,
            node_types=["body"],
        )
        for hit in hits:
            self.assertEqual(hit.node_type, "body")

    def test_doc_id_filter_scopes_to_specified_document(self) -> None:
        hits = search_node_vectors(
            self._conn,
            "photosynthesis",
            embedder=self._embedder,
            doc_ids=["doc-1"],
        )
        for hit in hits:
            self.assertEqual(hit.doc_id, "doc-1")

    def test_empty_node_type_allowlist_returns_no_hits(self) -> None:
        self.assertEqual(
            search_node_vectors(
                self._conn,
                "photosynthesis",
                embedder=self._embedder,
                node_types=[],
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
