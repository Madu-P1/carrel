"""Phase 10: prove the demo corpus is honest, not curated-fake.

Runs the real deterministic engine over the pre-vetted corpus in demo/ and
asserts the catch genuinely fires: a fabricated cite is not found, a real cite
exists, a money contradiction fires, a matching term reads present, and an
anchor-free claim is untreated (no card; it reads as plain draft text).
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

    def test_motion_refuses_the_doctored_quote(self) -> None:
        # The doctored Brown quote is not verbatim in the held opinion text, so the
        # engine REFUSES (could-not-check) rather than confirming it or accusing the
        # author of fabrication. The refusal is the honest state, not a silent pass.
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(
                _body(DEMO / "litigator-motion.md"), client=local_caselaw_client()
            )
        unverified = [c for c in env["claims"] if "quote_could_not_check_reason" in c]
        self.assertEqual(1, len(unverified))  # the doctored Brown quote
        self.assertIn("could not be verified", unverified[0]["quote_could_not_check_reason"])

    def test_fabricated_caption_with_a_quote_stays_unsupported_not_unknown(self) -> None:
        # Finding 8 (xhigh review): a fabricated caption on a REAL reporter number
        # ("Smith v. Jones, 347 U.S. 483", which resolves to Brown) that ALSO carries an
        # unverifiable quote must read "unsupported" (the fabrication catch), not soften
        # to "unknown" because the quote-could-not-check reason won the precedence. The
        # reason must name the caption mismatch, not the quote.
        from services import verify as verify_service

        draft = (
            'The Court observed that "separate facilities are inherently equal" in '
            "Smith v. Jones, 347 U.S. 483."
        )
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(draft, client=local_caselaw_client())
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("resolves to", card.unsupported_reason or "")


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
        verdict = claim["contract_verdict"]
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        # Filing-grade: the detail names the section and both values.
        self.assertIn("Section 8", verdict["detail"])
        self.assertIn("$500,000", verdict["detail"])

    def test_wrong_execution_date_is_a_contradiction(self) -> None:
        claim = self._verdict_for("executed on March 11, 2024")
        self.assertEqual("parametric_contradiction", claim["contract_verdict"]["disposition"])

    def test_matching_term_is_not_affirmed(self) -> None:
        # ADR-0013 scope-out: a matching term (duration) is could-not-check, not affirmed.
        claim = self._verdict_for("term of the agreement")
        self.assertEqual("not_found", claim["contract_verdict"]["disposition"])

    def test_exclusivity_flip_is_a_contradiction(self) -> None:
        # The summary upgrades the non-exclusive Section 3 grant to exclusive:
        # the canonical single-token contract-summary error, caught with both
        # qualifiers quoted.
        claim = self._verdict_for("exclusive license")
        verdict = claim["contract_verdict"]
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertIn("Section 3", verdict["detail"])
        self.assertIn("non-exclusive", verdict["detail"])

    def test_governing_law_flip_is_a_contradiction(self) -> None:
        # The summary flips the choice of law to the VENUE state (Section 14
        # chooses Delaware law but New York courts): the classic AI confusion,
        # and the venue jurisdiction must not mask the catch.
        claim = self._verdict_for("governed by New York law")
        verdict = claim["contract_verdict"]
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertIn("New York", verdict["detail"])
        self.assertIn("Delaware", verdict["detail"])

    def test_venue_quote_is_present(self) -> None:
        # The one AFFIRMED verdict in the demo (council 2026-06-16): a verbatim
        # quote of Section 14's venue clause greens via the provably-safe quote
        # anchor, so the buyer can calibrate what a refusal means. Same two words
        # "New York" as the governing-law contradiction above, opposite verdicts:
        # the choice of law is wrong (red), the venue quote is verbatim-correct
        # (green). A green here is character-for-character, never a rubber stamp.
        claim = self._verdict_for("exclusive jurisdiction of the courts of New York")
        verdict = claim["contract_verdict"]
        self.assertEqual("present", verdict["disposition"])
        self.assertEqual("quote", verdict["anchor_type"])

    def test_best_efforts_claim_is_untreated(self) -> None:
        # "The vendor must use best efforts to protect confidential information." carries
        # no checkable anchor (the source's defined term is "Confidential Information",
        # capitalized; the lowercase prose does not match the case-sensitive detector),
        # so it is untreated: no card, no could-not-check reason. It reads as plain text.
        claim = self._verdict_for("best efforts")
        self.assertTrue(claim.get("untreated"))
        self.assertNotIn("could_not_check_reason", claim)


if __name__ == "__main__":
    unittest.main()
