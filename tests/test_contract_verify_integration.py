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
            _node(
                0, "Section 8. The aggregate liability of the parties shall not exceed $500,000."
            ),
            _node(1, "This Agreement shall continue for a confidentiality term of two (2) years."),
            _node(2, "The parties shall cooperate in good faith on all matters."),
            _node(
                3,
                'Acme Inc. (the "Buyer") is the recipient. "Confidential Information" '
                "means all non-public information disclosed under this Agreement.",
            ),
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

    def test_present_money_with_absent_quoted_holding_is_could_not_check(self) -> None:
        # C2 (anchor-laundering guard): a sentence whose money value matches a clause
        # ($500,000 is in Section 8) MUST NOT launder a fabricated quoted holding that
        # is absent from that clause into a green "present". It downgrades to the honest
        # could-not-check; it never accuses (no "altered"/"unsupported").
        draft = (
            "The aggregate liability shall not exceed $500,000, and the parties agreed "
            'that "either party may terminate for convenience on thirty days notice."'
        )
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual(
            "unknown",
            card.verdict,
            "a fabricated quote must not ride a matching figure into a verified present",
        )

    def test_present_money_without_a_quote_stays_verified(self) -> None:
        # Control (no recall regression): the same matching figure with NO quoted
        # holding is still a clean present -> verified.
        draft = "The aggregate liability shall not exceed $500,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("verified", card.verdict)

    def test_offtopic_clause_sharing_a_value_is_could_not_check(self) -> None:
        # C3 (relevance floor): a claim whose money value coincidentally matches an
        # OFF-TOPIC clause (a signing bonus, not a liability cap) must read
        # could-not-check, never a false "present". Scope retrieval to the off-topic
        # doc so no on-topic clause exists for that value.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('offtopic-1', 'comp.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        off = [_node(0, "The signing bonus payable to the executive is $42,000.")]
        ids = insert_typed_nodes(self._conn, "offtopic-1", off)
        embed_and_index_nodes(self._conn, off, ids, embedder=self._embedder)
        self._conn.commit()
        draft = "The aggregate liability is capped at $42,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["offtopic-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual(
            "unknown",
            card.verdict,
            "an off-topic value coincidence must not read a verified present",
        )

    def test_present_quote_agrees_between_card_and_quote_panel(self) -> None:
        # D1 (consistency): a contract claim whose quoted language is verbatim in a
        # clause reads verified AND the brief-level QuotePanel reads that same quote as
        # "verbatim" (confirmed), never the contradictory "could_not_check". The card
        # and the panel must agree.
        draft = 'The agreement requires that "The parties shall cooperate in good faith on all matters."'
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        result = verify_service._verify_result_from_envelope(draft, env, 0.0)
        self.assertEqual("verified", result.claim_verdicts[0].verdict)
        statuses = [q["status"] for q in result.quote_results]
        self.assertIn(
            "verbatim", statuses, "the confirmed quote must read verbatim in the QuotePanel"
        )
        self.assertNotIn("could_not_check", statuses)

    def test_contradiction_renders_as_unsupported_card(self) -> None:
        draft = "The aggregate liability is capped at $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        result = verify_service._verify_result_from_envelope(draft, env, 0.0)
        card = result.claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        # The reason is filing-grade: it quotes both values.
        self.assertIn("$1,000,000", card.unsupported_reason or "")
        self.assertIn("$500,000", card.unsupported_reason or "")

    def test_multi_value_sentence_is_could_not_check_not_a_guess(self) -> None:
        # A summary sentence carrying two money values cannot be aligned to the clause
        # deterministically. The card must read could-not-check (unknown) with an honest
        # reason, never a masked "verified" or a guessed "unsupported".
        draft = "The aggregate liability caps are $500,000 and $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "aggregate liability caps")
        self.assertEqual("multi_value_unverifiable", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        self.assertIn("not independently checked", card.unsupported_reason or "")

    def test_anchor_free_claim_is_untreated(self) -> None:
        # Even in contract mode, a sentence with no checkable anchor (no money / date /
        # party / section / defined term) is UNTREATED: no card, no could-not-check
        # reason. It renders as plain draft text. (With T1 dark, no promotion.)
        env = build_deterministic_envelope(
            "The vendor is solely responsible for all defects.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        self.assertEqual([], env["unsupported_spans"])
        self.assertEqual(1, len(env["claims"]))
        claim = env["claims"][0]
        self.assertTrue(claim.get("untreated"))
        self.assertNotIn("could_not_check_reason", claim)
        result = verify_service._verify_result_from_envelope(claim["text"], env, 0.0)
        self.assertEqual((), result.claim_verdicts)

    def test_source_alias_table_reads_definitions_from_nodes(self) -> None:
        # PR-1: build_alias_table is now reached in production (was dead code). The
        # source's own definitions, the parenthetical alias and the "X" means form,
        # become the table; no source / no nodes / no term all stay inert (None).
        from services.legal.deterministic_envelope import _source_alias_table

        self.assertEqual(
            {"Buyer": "Buyer", "Confidential Information": "Confidential Information"},
            _source_alias_table(self._conn, ["contract-1"]),
        )
        self.assertIsNone(_source_alias_table(None, ["contract-1"]))
        self.assertIsNone(_source_alias_table(self._conn, []))

    def test_defined_term_only_claim_is_grounded_could_not_check(self) -> None:
        # A sentence whose only checkable signal is a defined term gets an honest
        # term-grounded could-not-check that NAMES the term, never the misleading
        # "language does not appear" (the term IS defined in the source).
        env = build_deterministic_envelope(
            "The Buyer must safeguard Confidential Information at all times.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        claim = env["claims"][0]
        self.assertIn("could_not_check_reason", claim)
        reason = claim["could_not_check_reason"]
        self.assertIn("defined term", reason.lower())
        self.assertIn("Confidential Information", reason)
        self.assertNotIn("does not appear", reason.lower())
        card = verify_service._verify_result_from_envelope(claim["text"], env, 0.0).claim_verdicts[
            0
        ]
        self.assertEqual("unknown", card.verdict)

    def test_source_party_section_sets_reads_from_nodes(self) -> None:
        # PR-2: party + section detectors are now collected from the source, offline,
        # via the same extract_anchors the draft uses. Normalized: "Acme Inc." -> acme,
        # (the "Buyer") -> buyer, "Section 8." -> 8.
        from services.legal.deterministic_envelope import _source_party_section_sets

        parties, sections = _source_party_section_sets(self._conn, ["contract-1"])
        self.assertIn("acme", parties)
        self.assertIn("buyer", parties)
        self.assertIn("8", sections)
        self.assertEqual(
            (frozenset(), frozenset()), _source_party_section_sets(None, ["contract-1"])
        )

    def test_party_named_in_draft_is_grounded_could_not_check(self) -> None:
        # A party that IS in the source contract grounds the sentence without claiming
        # its assertion is verified: an honest could-not-check that names the party.
        env = build_deterministic_envelope(
            "Acme Inc. shall indemnify the counterparty for any breach.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        claim = env["claims"][0]
        self.assertIn("could_not_check_reason", claim)
        self.assertIn("party to the source contract", claim["could_not_check_reason"])
        self.assertEqual(
            "unknown",
            verify_service._verify_result_from_envelope(claim["text"], env, 0.0)
            .claim_verdicts[0]
            .verdict,
        )

    def test_unmatched_party_is_could_not_check_never_accused(self) -> None:
        # The never-accuse guarantee: a party NOT found in the source is reported as a
        # could-not-check ("could not be matched"), never as unsupported, because a
        # name-form difference must not become a false accusation.
        draft = "Globex LLC shall be solely liable for all damages."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        claim = env["claims"][0]
        self.assertIn("could not be matched to a party", claim["could_not_check_reason"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        self.assertNotEqual("unsupported", card.verdict)

    def test_section_reference_found_is_grounded(self) -> None:
        env = build_deterministic_envelope(
            "The cap is governed by Section 8 of the agreement.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        claim = env["claims"][0]
        self.assertIn("exists in the source contract", claim["could_not_check_reason"])
        self.assertEqual(
            "unknown",
            verify_service._verify_result_from_envelope(claim["text"], env, 0.0)
            .claim_verdicts[0]
            .verdict,
        )

    def test_missing_section_is_unsupported(self) -> None:
        # A draft citing a section the source contract does not contain is a hard
        # unsupported verdict (the source yielded Section 8, so source_sections is
        # non-empty and the precision gate is satisfied). Unlike a party, section
        # numbering is regular enough that an absent number is genuinely absent, not
        # name-form variance, so it earns a verdict rather than a could-not-check.
        draft = "The obligations of Section 99 are incorporated by reference."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        claim = env["claims"][0]
        self.assertNotIn("could_not_check_reason", claim)
        self.assertEqual("section_absent", claim["section_verdict"]["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("could not be located", (card.unsupported_reason or "").lower())

    def test_grounding_never_overrides_a_contradiction(self) -> None:
        # ADR-0012 invariant 2 across all grounding types: a party/section present
        # alongside a contradicted value must not soften the verdict. The $1M
        # contradicts the $500K cap; the card stays unsupported, no grounding reason.
        draft = "Under Section 8, Acme Inc.'s aggregate liability is capped at $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        claim = env["claims"][0]
        self.assertNotIn("could_not_check_reason", claim)
        self.assertEqual("parametric_contradiction", claim["contract_verdict"]["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

    def test_defined_term_never_overrides_a_contradiction(self) -> None:
        # ADR-0012 invariant 2: a defined term must not manufacture or soften a
        # verdict. "Buyer" is a defined term AND the $1M contradicts the $500K cap;
        # the contradiction wins and the card stays unsupported with both values.
        draft = "The Buyer's aggregate liability is capped at $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        claim = env["claims"][0]
        self.assertNotIn("could_not_check_reason", claim)
        self.assertEqual("parametric_contradiction", claim["contract_verdict"]["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("$1,000,000", card.unsupported_reason or "")
        self.assertIn("$500,000", card.unsupported_reason or "")


if __name__ == "__main__":
    unittest.main()
