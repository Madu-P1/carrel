"""End-to-end tests for typed-node hybrid retrieval (BM25 + vector + RRF).

Exercises `search_typed_hybrid` against a seeded mini corpus. Verifies:
- RRF score sums across both lists.
- Default node_types are derived from the query when none passed.
- Explicit node_types override the router.
- The `RETRIEVAL_USE_NODES` flag reads correctly.
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
from services.ingestion.persistence import (
    embed_and_index_nodes,
    insert_typed_nodes,
)
from services.ingestion.typed_walker import TypedNode
from services.retrieval.typed_hybrid import (
    RetrievedNode,
    retrieval_use_nodes_enabled,
    search_typed_hybrid,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _DeterministicEmbedder:
    dim = 384

    def _vec(self, text: str) -> list[float]:
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
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _node(order: int, *, node_type: str = "body", text: str = "", heading_path: str = "Topic") -> TypedNode:
    return TypedNode(
        node_type=node_type,
        heading_path=heading_path,
        page=1,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


class RetrievalUseNodesFlagTests(unittest.TestCase):
    """Pure flag-reader tests — no DB setup required."""

    @mock.patch.dict("os.environ", {}, clear=False)
    def test_flag_defaults_off_when_unset(self) -> None:
        os.environ.pop("RETRIEVAL_USE_NODES", None)
        self.assertFalse(retrieval_use_nodes_enabled())

    @mock.patch.dict("os.environ", {"RETRIEVAL_USE_NODES": "true"}, clear=False)
    def test_true_string_enables_flag(self) -> None:
        self.assertTrue(retrieval_use_nodes_enabled())

    @mock.patch.dict("os.environ", {"RETRIEVAL_USE_NODES": "1"}, clear=False)
    def test_one_string_enables_flag(self) -> None:
        self.assertTrue(retrieval_use_nodes_enabled())

    @mock.patch.dict("os.environ", {"RETRIEVAL_USE_NODES": "no"}, clear=False)
    def test_other_strings_keep_flag_off(self) -> None:
        self.assertFalse(retrieval_use_nodes_enabled())


class TypedHybridSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (
            db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH,
        )
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        data_dir = root / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (root / "schema.sql").write_text("-- test\n", encoding="utf-8")
        shutil.copytree(MIGRATIONS_SOURCE, root / "migrations", dirs_exist_ok=True)
        db.configure_paths(
            base_dir=root, data_dir=data_dir, upload_dir=upload_dir,
            db_path=data_dir / "test.db", schema_path=root / "schema.sql",
        )
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._embedder = _DeterministicEmbedder()
        self._seed_corpus()

    def tearDown(self) -> None:
        self._conn.close()
        self._tmp.cleanup()
        db.configure_paths(
            base_dir=self._original[0], data_dir=self._original[1],
            upload_dir=self._original[2], db_path=self._original[3],
            schema_path=self._original[4],
        )

    def _seed_corpus(self) -> None:
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('doc-1', 'a.md', 'md', 'ready', 'manual_text', 'Topic')"
        )
        nodes = [
            _node(0, node_type="heading", text="Photosynthesis"),
            _node(1, node_type="body",
                  text="Plants use chlorophyll to capture light energy"),
            _node(2, node_type="caption",
                  text="Figure 1: The Calvin cycle and ATP regeneration"),
            _node(3, node_type="table_cell",
                  text="Light intensity 200 lux"),
            _node(4, node_type="body",
                  text="Cell division separates chromosomes during mitosis"),
        ]
        ids = insert_typed_nodes(self._conn, "doc-1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def test_blank_query_returns_empty(self) -> None:
        self.assertEqual(search_typed_hybrid(self._conn, "  "), [])

    def test_returns_RetrievedNode_with_full_metadata(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "chlorophyll", embedder=self._embedder,
        )
        self.assertTrue(hits)
        top = hits[0]
        self.assertIsInstance(top, RetrievedNode)
        self.assertEqual(top.doc_id, "doc-1")
        self.assertEqual(top.heading_path, "Topic")
        self.assertEqual(top.page, 1)
        self.assertGreater(top.char_end, top.char_start)
        self.assertGreater(top.score, 0.0)

    def test_score_is_sum_of_components(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "chlorophyll", embedder=self._embedder,
        )
        for hit in hits:
            self.assertAlmostEqual(
                hit.score,
                sum(hit.components.values()),
                places=6,
            )

    def test_components_record_each_source(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "chlorophyll", embedder=self._embedder,
        )
        # The matched body row appears in both BM25 and vector candidates,
        # so its components dict should record both sources.
        top = hits[0]
        self.assertIn("fts", top.components)
        self.assertIn("vec", top.components)
        self.assertEqual(set(top.sources), {"fts", "vec"})

    def test_default_query_excludes_table_cells_and_captions(self) -> None:
        # "chlorophyll" mentions no table/figure/formula keywords, so the
        # router returns the prose backbone only. The seeded `caption`
        # and `table_cell` rows must not surface.
        hits = search_typed_hybrid(
            self._conn, "chlorophyll", embedder=self._embedder,
        )
        for hit in hits:
            self.assertIn(hit.node_type, {"heading", "body", "list_item"})

    def test_table_keyword_pulls_in_table_cells(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "table light intensity", embedder=self._embedder,
        )
        node_types = {hit.node_type for hit in hits}
        self.assertIn("table_cell", node_types)

    def test_explicit_node_types_override_router(self) -> None:
        # Even though the query lacks "figure", we can force captions
        # by passing an explicit allowlist.
        hits = search_typed_hybrid(
            self._conn, "Calvin",
            embedder=self._embedder,
            node_types=["caption"],
        )
        self.assertTrue(hits)
        for hit in hits:
            self.assertEqual(hit.node_type, "caption")

    def test_doc_id_filter_propagates_through_both_lists(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "chlorophyll",
            embedder=self._embedder,
            doc_ids=["doc-1"],
        )
        for hit in hits:
            self.assertEqual(hit.doc_id, "doc-1")

    def test_results_are_score_descending(self) -> None:
        hits = search_typed_hybrid(
            self._conn, "Plants chlorophyll cell division",
            embedder=self._embedder,
            limit=10,
        )
        scores = [hit.score for hit in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
