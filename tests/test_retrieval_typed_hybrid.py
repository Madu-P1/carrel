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
    _apply_rerank,
    retrieval_use_nodes_enabled,
    retrieval_use_reranker_enabled,
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


def _node(
    order: int, *, node_type: str = "body", text: str = "", heading_path: str = "Topic"
) -> TypedNode:
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


class RetrievalUseRerankerFlagTests(unittest.TestCase):
    """RETRIEVAL_USE_RERANKER is independent of RETRIEVAL_USE_NODES."""

    @mock.patch.dict("os.environ", {}, clear=False)
    def test_flag_defaults_off_when_unset(self) -> None:
        os.environ.pop("RETRIEVAL_USE_RERANKER", None)
        self.assertFalse(retrieval_use_reranker_enabled())

    @mock.patch.dict("os.environ", {"RETRIEVAL_USE_RERANKER": "true"}, clear=False)
    def test_true_string_enables_flag(self) -> None:
        self.assertTrue(retrieval_use_reranker_enabled())

    @mock.patch.dict(
        "os.environ",
        {"RETRIEVAL_USE_NODES": "true", "RETRIEVAL_USE_RERANKER": "false"},
        clear=False,
    )
    def test_use_nodes_does_not_imply_use_reranker(self) -> None:
        # Operators must opt into the reranker explicitly — the model is
        # 1 GB heavier than the embedder so coupling the two flags would
        # surprise users who only wanted typed-node retrieval.
        self.assertTrue(retrieval_use_nodes_enabled())
        self.assertFalse(retrieval_use_reranker_enabled())


class TypedHybridSearchTests(unittest.TestCase):
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
            _node(0, node_type="heading", text="Photosynthesis"),
            _node(1, node_type="body", text="Plants use chlorophyll to capture light energy"),
            _node(2, node_type="caption", text="Figure 1: The Calvin cycle and ATP regeneration"),
            _node(3, node_type="table_cell", text="Light intensity 200 lux"),
            _node(4, node_type="body", text="Cell division separates chromosomes during mitosis"),
        ]
        ids = insert_typed_nodes(self._conn, "doc-1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def test_blank_query_returns_empty(self) -> None:
        self.assertEqual(search_typed_hybrid(self._conn, "  "), [])

    def test_returns_RetrievedNode_with_full_metadata(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
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
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
        )
        for hit in hits:
            self.assertAlmostEqual(
                hit.score,
                sum(hit.components.values()),
                places=6,
            )

    def test_components_record_each_source(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
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
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
        )
        for hit in hits:
            self.assertIn(hit.node_type, {"heading", "body", "list_item"})

    def test_table_keyword_pulls_in_table_cells(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "table light intensity",
            embedder=self._embedder,
        )
        node_types = {hit.node_type for hit in hits}
        self.assertIn("table_cell", node_types)

    def test_explicit_node_types_override_router(self) -> None:
        # Even though the query lacks "figure", we can force captions
        # by passing an explicit allowlist.
        hits = search_typed_hybrid(
            self._conn,
            "Calvin",
            embedder=self._embedder,
            node_types=["caption"],
        )
        self.assertTrue(hits)
        for hit in hits:
            self.assertEqual(hit.node_type, "caption")

    def test_doc_id_filter_propagates_through_both_lists(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            doc_ids=["doc-1"],
        )
        for hit in hits:
            self.assertEqual(hit.doc_id, "doc-1")

    def test_results_are_score_descending(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "Plants chlorophyll cell division",
            embedder=self._embedder,
            limit=10,
        )
        scores = [hit.score for hit in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


class _StubReranker:
    """Reranker test double that returns scores from a per-doc lookup."""

    def __init__(self, scores_by_text: dict[str, float]) -> None:
        self._lookup = scores_by_text
        self.calls: list[tuple[str, list[str]]] = []

    def rerank_pairs(self, query: str, documents):
        self.calls.append((query, list(documents)))
        # Default to 0.5 (sigmoid(0)) for unknown documents — matches
        # the contract from rerank.py: scores must already be in [0, 1].
        return [self._lookup.get(doc, 0.5) for doc in documents]


class RerankIntegrationTests(TypedHybridSearchTests):
    """Inherit the seeded corpus + db from TypedHybridSearchTests."""

    def test_use_reranker_off_returns_pure_rrf_score(self) -> None:
        hits = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
        )
        for hit in hits:
            self.assertIsNone(hit.rerank_score)
            self.assertAlmostEqual(hit.score, sum(hit.components.values()), places=6)

    def test_use_reranker_on_populates_rerank_score(self) -> None:
        hits_no_rerank = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
        )
        candidate_texts = {h.verbatim_text for h in hits_no_rerank}
        # Force the reranker to flip ordering: pick a non-top RRF hit
        # and give it the highest rerank score.
        chosen = sorted(hits_no_rerank, key=lambda h: h.score)[0].verbatim_text
        stub = _StubReranker({chosen: 0.95})
        hits = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
            use_reranker=True,
            reranker=stub,
        )
        # Stub was called once with all candidates.
        self.assertEqual(len(stub.calls), 1)
        called_query, called_docs = stub.calls[0]
        self.assertEqual(called_query, "chlorophyll")
        self.assertTrue(set(called_docs).issuperset(candidate_texts))
        # Every returned hit carries a populated rerank_score.
        for hit in hits:
            self.assertIsNotNone(hit.rerank_score)
            self.assertGreaterEqual(hit.rerank_score, 0.0)
            self.assertLessEqual(hit.rerank_score, 1.0)

    def test_blended_score_pulls_top_to_reranker_choice(self) -> None:
        # Run baseline without rerank to see who the RRF top hit is.
        baseline = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
        )
        self.assertTrue(baseline)
        baseline_top = baseline[0].verbatim_text
        # Pick the lowest-RRF candidate and give it 1.0 from the reranker.
        target = baseline[-1].verbatim_text
        self.assertNotEqual(target, baseline_top)
        stub = _StubReranker(
            {text: (1.0 if text == target else 0.0) for text in [b.verbatim_text for b in baseline]}
        )
        rescored = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
            use_reranker=True,
            reranker=stub,
            rerank_blend=0.7,
        )
        # 0.7 weight on rerank, 0.3 on RRF — the stubbed-1.0 doc must
        # come out on top even though it had the lowest RRF score.
        self.assertEqual(rescored[0].verbatim_text, target)

    def test_rerank_blend_zero_collapses_to_pure_rrf(self) -> None:
        # rerank_blend=0 means we keep the RRF ordering even with rerank on.
        baseline = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
        )
        stub = _StubReranker({h.verbatim_text: (1.0 - i * 0.1) for i, h in enumerate(baseline)})
        rescored = search_typed_hybrid(
            self._conn,
            "chlorophyll",
            embedder=self._embedder,
            limit=5,
            use_reranker=True,
            reranker=stub,
            rerank_blend=0.0,
        )
        # Same top hit as the baseline.
        self.assertEqual(rescored[0].verbatim_text, baseline[0].verbatim_text)

    def test_rerank_top_caps_how_many_candidates_get_reranked(self) -> None:
        baseline = search_typed_hybrid(
            self._conn,
            "chlorophyll Plants Calvin",
            embedder=self._embedder,
            limit=10,
        )
        if len(baseline) < 2:
            self.skipTest("seeded corpus too small to assert rerank_top truncation")
        stub = _StubReranker({})
        search_typed_hybrid(
            self._conn,
            "chlorophyll Plants Calvin",
            embedder=self._embedder,
            limit=10,
            use_reranker=True,
            reranker=stub,
            rerank_top=1,
        )
        called_docs = stub.calls[0][1]
        self.assertEqual(len(called_docs), 1)


class ApplyRerankUnitTests(unittest.TestCase):
    """Direct tests of _apply_rerank without spinning up the DB."""

    def _node(self, node_id: int, text: str, rrf: float) -> RetrievedNode:
        return RetrievedNode(
            node_id=node_id,
            doc_id="doc-1",
            node_type="body",
            heading_path="",
            page=None,
            char_start=0,
            char_end=len(text),
            verbatim_text=text,
            snippet=text,
            score=rrf,
            components={"fts": rrf},
            sources=("fts",),
        )

    def test_blend_formula_matches_spec(self) -> None:
        a = self._node(1, "alpha", rrf=2.0)
        b = self._node(2, "beta", rrf=4.0)
        c = self._node(3, "gamma", rrf=6.0)
        # Reranker scores: alpha=0.0, beta=0.5, gamma=1.0.
        # After min-max norm of RRF: a=0.0, b=0.5, c=1.0
        # After min-max norm of rerank: a=0.0, b=0.5, c=1.0
        # blend=0.7 → a=0.0, b=0.5, c=1.0 (unchanged) — both sides agree.
        stub = _StubReranker({"alpha": 0.0, "beta": 0.5, "gamma": 1.0})
        rescored = _apply_rerank([a, b, c], "q", stub, blend=0.7)
        self.assertEqual([r.node_id for r in rescored], [3, 2, 1])
        self.assertAlmostEqual(rescored[0].score, 1.0, places=6)
        self.assertAlmostEqual(rescored[1].score, 0.5, places=6)
        self.assertAlmostEqual(rescored[2].score, 0.0, places=6)

    def test_blend_with_disagreement_uses_weighted_sum(self) -> None:
        a = self._node(1, "alpha", rrf=10.0)  # RRF top
        b = self._node(2, "beta", rrf=0.0)  # RRF bottom
        # Reranker disagrees: beta=1.0, alpha=0.0
        stub = _StubReranker({"alpha": 0.0, "beta": 1.0})
        rescored = _apply_rerank([a, b], "q", stub, blend=0.7)
        # alpha: 0.7 * 0 + 0.3 * 1 = 0.3
        # beta:  0.7 * 1 + 0.3 * 0 = 0.7
        # beta wins.
        self.assertEqual(rescored[0].node_id, 2)
        self.assertAlmostEqual(rescored[0].score, 0.7, places=6)
        self.assertAlmostEqual(rescored[1].score, 0.3, places=6)

    def test_empty_candidates_returns_empty(self) -> None:
        stub = _StubReranker({})
        self.assertEqual(_apply_rerank([], "q", stub, blend=0.7), [])

    def test_misbehaving_reranker_raises_value_error(self) -> None:
        class _BadReranker:
            def rerank_pairs(self, query, documents):
                return [0.5]  # only one score, regardless of input length

        a = self._node(1, "a", 1.0)
        b = self._node(2, "b", 2.0)
        with self.assertRaises(ValueError):
            _apply_rerank([a, b], "q", _BadReranker(), blend=0.7)


if __name__ == "__main__":
    unittest.main()
