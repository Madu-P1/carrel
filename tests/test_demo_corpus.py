"""Phase 10: prove the demo corpus is honest, not curated-fake.

Runs the real deterministic engine over the pre-vetted corpus in demo/ and
asserts the catch genuinely fires: a fabricated cite is not found, a real cite
exists, a money contradiction fires, a matching term reads present, and an
anchor-free claim lands in the honest could-not-check tray.
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
from services.ingestion.persistence import embed_and_index_nodes, insert_typed_nodes
from services.ingestion.typed_walker import TypedNode
from services.legal.deterministic_envelope import build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO = REPO_ROOT / "demo"
MIGRATIONS_SOURCE = REPO_ROOT / "migrations"


def _body(path: Path) -> str:
    """File text minus markdown heading lines (the verify input, not the title)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("#")).strip()


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


class LitigatorCorpusTests(unittest.TestCase):
    def test_motion_catches_the_fabricated_cite_and_confirms_the_real_one(self) -> None:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(
                _body(DEMO / "litigator-motion.md"), client=local_caselaw_client()
            )
        exists = {}
        for claim in env["claims"]:
            for batch in claim["case_verdicts"]:
                for v in batch["verdicts"]:
                    exists[v["citation"]] = v["exists"]
        self.assertTrue(exists.get("347 U.S. 483"))  # Brown, in the corpus
        self.assertFalse(exists.get("999 U.S. 999"))  # fabricated, the catch


class ContractCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original = (db.BASE_DIR, db.DATA_DIR, db.UPLOAD_DIR, db.DB_PATH, db.SCHEMA_PATH)
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
        self._conn = db.get_db()
        db.apply_migrations(self._conn)
        self._embedder = _DeterministicEmbedder()
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('msa', 'msa.md', 'md', 'ready', 'upload', 'Agreement')"
        )
        # Ingest the MSA as one clause node per non-empty paragraph.
        clauses = [c.strip() for c in _body(DEMO / "contract-msa.md").split("\n\n") if c.strip()]
        nodes = [
            TypedNode(
                node_type="body",
                heading_path="Agreement",
                page=1,
                char_start=i * 400,
                char_end=i * 400 + len(text),
                verbatim_text=text,
                parent_block_id=None,
                reading_order=i,
            )
            for i, text in enumerate(clauses)
        ]
        ids = insert_typed_nodes(self._conn, "msa", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
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

    def _verdict_for(self, needle: str) -> dict:
        env = build_deterministic_envelope(
            _body(DEMO / "contract-ai-summary.md"),
            conn=self._conn,
            doc_ids=["msa"],
            embedder=self._embedder,
        )
        claim = next(c for c in env["claims"] if needle in c["text"])
        return claim

    def test_inflated_liability_cap_is_a_contradiction(self) -> None:
        claim = self._verdict_for("capped at $1,000,000")
        self.assertEqual("parametric_contradiction", claim["contract_verdict"]["disposition"])

    def test_matching_term_is_present(self) -> None:
        claim = self._verdict_for("term of the agreement")
        self.assertEqual("present", claim["contract_verdict"]["disposition"])

    def test_best_efforts_claim_is_could_not_check(self) -> None:
        claim = self._verdict_for("best efforts")
        self.assertIn("could_not_check_reason", claim)


if __name__ == "__main__":
    unittest.main()
