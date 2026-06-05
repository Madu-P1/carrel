"""Phase 6 wiring: the contract path end to end over a real ingested contract.

Seeds a small executed contract into the nodes table, then runs
build_deterministic_envelope over an AI-drafted summary and asserts the
parametric contradiction and present verdicts fire via real retrieval. No
LLM, no network. Uses a deterministic stub embedder so no model is downloaded.
"""

from __future__ import annotations

import hashlib
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import db
from services import verify as verify_service
from services.ingestion.persistence import embed_and_index_nodes, insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.legal.deterministic_envelope import build_deterministic_envelope

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


def _node(order: int, text: str, *, node_type: str = "body") -> TypedNode:
    return TypedNode(
        node_type=node_type,
        heading_path="Agreement",
        page=1,
        char_start=order * 200,
        char_end=order * 200 + len(text),
        verbatim_text=text,
        parent_block_id=None,
        reading_order=order,
    )


class ContractPathIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
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
        self._seed_contract()

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

    def _seed_contract(self) -> None:
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-1', 'msa.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(0, "The aggregate liability of the parties shall not exceed $500,000."),
            _node(1, "This Agreement shall continue for a confidentiality term of two (2) years."),
            _node(2, "The parties shall cooperate in good faith on all matters."),
        ]
        ids = insert_typed_nodes(self._conn, "contract-1", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._conn.commit()

    def _verdict_for(self, env: dict, needle: str) -> dict:
        claim = next(c for c in env["claims"] if needle in c["text"])
        return claim["contract_verdict"]

    def test_money_claim_contradicts_the_clause(self) -> None:
        env = build_deterministic_envelope(
            "The aggregate liability is capped at $1,000,000.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        verdict = self._verdict_for(env, "liability")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertEqual("money", verdict["anchor_type"])

    def test_matching_duration_is_present(self) -> None:
        env = build_deterministic_envelope(
            "The confidentiality term lasts two (2) years.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        verdict = self._verdict_for(env, "confidentiality term")
        self.assertEqual("present", verdict["disposition"])

    def test_contradiction_renders_as_unsupported_card(self) -> None:
        draft = "The aggregate liability is capped at $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        result = verify_service._verify_result_from_envelope(draft, env, 0.0)
        card = result.claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("contradict", (card.unsupported_reason or "").lower())

    def test_anchor_free_claim_goes_to_unsupported(self) -> None:
        env = build_deterministic_envelope(
            "The vendor is solely responsible for all defects.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        self.assertEqual([], env["claims"])
        self.assertEqual(1, len(env["unsupported_spans"]))


if __name__ == "__main__":
    unittest.main()
