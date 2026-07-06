"""Integration: cross-document conflicts ride their own envelope channel.

Wired 2026-07-07 (Foundry campaign, first multi-document detector). A defined term
bound to irreconcilable values across two or more SOURCE documents (the doc_ids under
audit) surfaces as a FLAGGED cross_document_conflict on the envelope's
``cross_document_findings`` key -- NOT structural_findings, because the finding is
inherently multi-document (each figure names its own document + offsets). Consistent
sources, a single document, and a chunks-path DB (no conn) all surface NOTHING (the
no-false-accusation guard + backward compatibility). Every finding must satisfy
CrossDocumentFindingItem or /api/verify's response_model 500s. The detector's own logic
is in tests/test_cross_document.py.
"""

import sqlite3
import unittest

from api_models import CrossDocumentFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

DRAFT = "The Purchase Price is as stated in the governing agreements."
DOC_A = 'The "Purchase Price" means Five Thousand Dollars ($5,000).'
DOC_B_CONFLICT = 'The "Purchase Price" means Six Thousand Dollars ($6,000).'
DOC_B_AGREE = 'The parties reaffirm the "Purchase Price" of Five Thousand Dollars ($5,000).'


def _conn_with(docs: dict[str, str]) -> sqlite3.Connection:
    """An in-memory DB whose nodes table carries each document's text, one node per
    line in reading order (so the reconstructed text equals the original)."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE nodes (doc_id TEXT, verbatim_text TEXT, reading_order INTEGER)")
    for doc_id, text in docs.items():
        for i, line in enumerate(text.split("\n")):
            conn.execute("INSERT INTO nodes VALUES (?, ?, ?)", (doc_id, line, i))
    conn.commit()
    return conn


def _cd(draft: str, conn=None, doc_ids=None) -> list[dict]:
    env = build_deterministic_envelope(draft, conn=conn, doc_ids=doc_ids)
    return list(env.get("cross_document_findings", []))


class CrossDocumentEnvelopeWiring(unittest.TestCase):
    def test_conflicting_sources_are_flagged(self):
        conn = _conn_with({"docA.pdf": DOC_A, "docB.pdf": DOC_B_CONFLICT})
        fs = _cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"])
        self.assertEqual(len(fs), 1)
        self.assertEqual(fs[0]["kind"], "cross_document_conflict")
        self.assertEqual(fs[0]["disposition"], "flagged")

    def test_finding_names_both_documents_and_their_offsets(self):
        conn = _conn_with({"docA.pdf": DOC_A, "docB.pdf": DOC_B_CONFLICT})
        fs = _cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"])
        figures = fs[0]["figures"]
        self.assertGreaterEqual(len(figures), 2)
        self.assertEqual({f["document"] for f in figures}, {"docA.pdf", "docB.pdf"})
        # Each figure's snippet is the located line from its OWN document.
        reconstructed = {"docA.pdf": DOC_A, "docB.pdf": DOC_B_CONFLICT}
        for f in figures:
            self.assertIn(f["surface"], reconstructed[f["document"]])
            self.assertIn(f["snippet"], reconstructed[f["document"]])

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: each finding must validate against CrossDocumentFindingItem.
        conn = _conn_with({"docA.pdf": DOC_A, "docB.pdf": DOC_B_CONFLICT})
        for f in _cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"]):
            CrossDocumentFindingItem.model_validate(f)

    def test_consistent_sources_never_accuse(self):
        # HONESTY GUARD: two sources that agree on the term produce no finding.
        conn = _conn_with({"docA.pdf": DOC_A, "docB.pdf": DOC_B_AGREE})
        self.assertEqual(_cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"]), [])

    def test_single_document_skips_the_pass(self):
        conn = _conn_with({"docA.pdf": DOC_A})
        self.assertEqual(_cd(DRAFT, conn=conn, doc_ids=["docA.pdf"]), [])

    def test_no_conn_is_backward_compatible(self):
        # The chunks-path / LLM-path verify (no conn, no doc_ids) is untouched.
        self.assertEqual(_cd(DRAFT), [])

    def test_missing_nodes_table_is_inert(self):
        # A chunks-path DB with no nodes table must not raise into the sealed path.
        conn = sqlite3.connect(":memory:")
        self.assertEqual(_cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"]), [])

    def test_adds_no_green(self):
        conn = _conn_with({"docA.pdf": DOC_A, "docB.pdf": DOC_B_CONFLICT})
        for f in _cd(DRAFT, conn=conn, doc_ids=["docA.pdf", "docB.pdf"]):
            self.assertIn(f["disposition"], ("flagged", "could_not_check"))


if __name__ == "__main__":
    unittest.main()
