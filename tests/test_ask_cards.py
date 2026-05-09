"""Integration tests for the Free-tier Ask cards endpoint (PR 4).

Drives `/api/ask/cards` end-to-end through FastAPI's TestClient against
a temp SQLite DB seeded with typed nodes. Verifies the request
validation, filter propagation, response shape, and rerank kill-switch
behavior. The reranker isn't invoked here — `use_reranker=false` is
passed explicitly so the test suite never downloads the model.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.ingestion.persistence import (
    embed_and_index_nodes,
    insert_typed_nodes,
)
from services.ingestion.typed_walker import TypedNode
from services.local_api_security import HEADER_NAME, get_local_api_token

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


class _DeterministicEmbedder:
    """Hashed-bag embedder so the test never touches fastembed."""

    dim = 384

    def _vec(self, text: str) -> list[float]:
        import hashlib
        import math

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


class AskCardsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base_dir = Path(self._tmp.name)
        data_dir = base_dir / "data"
        upload_dir = data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        # The migrations directory must be reachable from the temp base.
        shutil.copytree(MIGRATIONS_SOURCE, base_dir / "migrations", dirs_exist_ok=True)
        # `db._list_migration_files` walks `SCHEMA_PATH.parent / "migrations"`,
        # so anchor schema_path inside the temp base.
        (base_dir / "schema.sql").write_text("-- test\n", encoding="utf-8")

        self._original = (
            main.BASE_DIR,
            main.DATA_DIR,
            main.UPLOAD_DIR,
            main.DB_PATH,
            main.SCHEMA_PATH,
        )
        main.BASE_DIR = base_dir
        main.DATA_DIR = data_dir
        main.UPLOAD_DIR = upload_dir
        main.DB_PATH = data_dir / "test.db"
        main.SCHEMA_PATH = base_dir / "schema.sql"
        main.initialize_database()

        # Seed two documents under different subjects + a small typed-node
        # corpus so the filter assertions have something to discriminate on.
        with main.get_db() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
                "VALUES ('doc-bio', 'photosynthesis.md', 'md', 'ready', 'manual_text', 'Biology')"
            )
            conn.execute(
                "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
                "VALUES ('doc-chem', 'combustion.md', 'md', 'ready', 'manual_text', 'Chemistry')"
            )
            bio_nodes = [
                _node(0, node_type="heading", text="Photosynthesis", heading_path="Photosynthesis"),
                _node(
                    1,
                    node_type="body",
                    text="Plants use chlorophyll to capture light energy",
                    heading_path="Photosynthesis",
                ),
            ]
            chem_nodes = [
                _node(0, node_type="heading", text="Combustion", heading_path="Combustion"),
                _node(
                    1,
                    node_type="body",
                    text="Methane reacts with oxygen producing carbon dioxide and water",
                    heading_path="Combustion",
                ),
            ]
            embedder = _DeterministicEmbedder()
            bio_ids = insert_typed_nodes(conn, "doc-bio", bio_nodes)
            chem_ids = insert_typed_nodes(conn, "doc-chem", chem_nodes)
            embed_and_index_nodes(conn, bio_nodes, bio_ids, embedder=embedder)
            embed_and_index_nodes(conn, chem_nodes, chem_ids, embedder=embedder)
            conn.commit()

        # Default-embedder swap so `routes/ask_cards.py::ask_cards`
        # doesn't load fastembed during tests.
        import services.retrieval.embeddings as emb_module

        self._original_default = emb_module._default
        emb_module._default = _DeterministicEmbedder()

        self.client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})

    def tearDown(self) -> None:
        import services.retrieval.embeddings as emb_module

        emb_module._default = self._original_default
        main.BASE_DIR = self._original[0]
        main.DATA_DIR = self._original[1]
        main.UPLOAD_DIR = self._original[2]
        main.DB_PATH = self._original[3]
        main.SCHEMA_PATH = self._original[4]
        self._tmp.cleanup()

    # ---------------------------------------------------------------- 400s

    def test_empty_query_returns_400(self) -> None:
        response = self.client.get("/api/ask/cards?q=&use_reranker=false")
        self.assertEqual(response.status_code, 400)
        self.assertIn("empty", response.json()["detail"].lower())

    def test_query_too_long_returns_400(self) -> None:
        long_q = "a" * 600
        response = self.client.get(f"/api/ask/cards?q={long_q}&use_reranker=false")
        self.assertEqual(response.status_code, 400)
        self.assertIn("500 characters", response.json()["detail"])

    def test_limit_out_of_range_returns_400(self) -> None:
        response = self.client.get("/api/ask/cards?q=hello&limit=99&use_reranker=false")
        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.json()["detail"].lower())

    def test_limit_zero_returns_400(self) -> None:
        response = self.client.get("/api/ask/cards?q=hello&limit=0&use_reranker=false")
        self.assertEqual(response.status_code, 400)

    # ---------------------------------------------------------------- 200s

    def test_basic_query_returns_card_envelope(self) -> None:
        response = self.client.get("/api/ask/cards?q=chlorophyll&use_reranker=false")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "chlorophyll")
        self.assertIn("library", body)
        self.assertEqual(body["library"]["total_nodes"], 4)
        self.assertFalse(body["rerank_used"])
        self.assertIsInstance(body["cards"], list)
        self.assertTrue(body["cards"], "expected at least one card hit")

    def test_card_carries_full_metadata_for_citation_chip(self) -> None:
        response = self.client.get("/api/ask/cards?q=chlorophyll&use_reranker=false")
        cards = response.json()["cards"]
        top = cards[0]
        # Every field the citation chip + reader pane will need.
        for key in (
            "node_id",
            "doc_id",
            "filename",
            "subject_name",
            "node_type",
            "heading_path",
            "page",
            "char_start",
            "char_end",
            "verbatim_text",
            "snippet",
            "score",
            "rerank_score",
            "sources",
        ):
            self.assertIn(key, top, f"card missing {key}")
        self.assertEqual(top["doc_id"], "doc-bio")
        self.assertEqual(top["filename"], "photosynthesis.md")
        self.assertEqual(top["subject_name"], "Biology")
        self.assertIsNone(top["rerank_score"])  # rerank disabled

    def test_doc_id_filter_propagates(self) -> None:
        # The deterministic embedder used here is hash-based noise — it
        # doesn't carry semantic meaning, so vector search will return
        # whatever rows survive the filter. The contract this test pins
        # is: when doc_id is set, ONLY that doc's rows come back. (BM25
        # exclusivity is covered by tests/test_retrieval_nodes_fts.py.)
        response = self.client.get("/api/ask/cards?q=Methane&doc_id=doc-bio&use_reranker=false")
        self.assertEqual(response.status_code, 200)
        cards = response.json()["cards"]
        for card in cards:
            self.assertEqual(card["doc_id"], "doc-bio")

    def test_subject_name_filter_propagates(self) -> None:
        response = self.client.get(
            "/api/ask/cards?q=oxygen&subject_name=Chemistry&use_reranker=false"
        )
        cards = response.json()["cards"]
        self.assertTrue(cards)
        for card in cards:
            self.assertEqual(card["subject_name"], "Chemistry")

    def test_empty_corpus_returns_empty_envelope_not_error(self) -> None:
        # Wipe nodes — a never-ingested-via-docling library must not 500.
        with main.get_db() as conn:
            conn.execute("DELETE FROM nodes")
            conn.commit()
        response = self.client.get("/api/ask/cards?q=chlorophyll&use_reranker=false")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["cards"], [])
        self.assertEqual(body["library"]["total_nodes"], 0)

    def test_rerank_explicit_false_takes_precedence_over_env_flag(self) -> None:
        # Flag would normally trigger model download; explicit false
        # must short-circuit before any reranker import.
        import os

        prior = os.environ.get("RETRIEVAL_USE_RERANKER")
        os.environ["RETRIEVAL_USE_RERANKER"] = "true"
        try:
            response = self.client.get("/api/ask/cards?q=chlorophyll&use_reranker=false")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["rerank_used"])
        finally:
            if prior is None:
                os.environ.pop("RETRIEVAL_USE_RERANKER", None)
            else:
                os.environ["RETRIEVAL_USE_RERANKER"] = prior

    def test_query_whitespace_is_stripped_before_validation(self) -> None:
        response = self.client.get("/api/ask/cards?q=%20%20%20&use_reranker=false")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
