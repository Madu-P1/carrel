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
        self._seed_percent_contract()
        self._conn.commit()

    def _seed_percent_contract(self) -> None:
        # A separate one-clause document for the percent cases: the legacy
        # contract-1 tests keep their exact pre-percent retrieval ranking (the
        # top-3 clause window over near-tie hash-RRF scores shifts when any
        # node is added), and the percent tests still run the full
        # envelope -> retrieval -> clause-verdict path.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-2', 'license.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(
                0,
                "Section 9.2. The royalty equals 50% of the net fees received "
                "in the twelve (12) months preceding each report.",
            ),
        ]
        ids = insert_typed_nodes(self._conn, "contract-2", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._seed_conflict_contract()

    def _seed_conflict_contract(self) -> None:
        # Two clauses carrying the SAME value type with different values, as
        # its own document (the fixture-isolation lesson): the adjudication
        # tests need both clauses retrievable for one claim, rank-independent.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-3', 'license-amended.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(
                0,
                "Section 4. The royalty equals 50% of net fees received each quarter.",
            ),
            _node(
                1,
                "Section 9. The marketing discount equals 40% of net fees received each quarter.",
            ),
        ]
        ids = insert_typed_nodes(self._conn, "contract-3", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._seed_governing_law_contract()

    def _seed_governing_law_contract(self) -> None:
        # Its own document (fixture isolation): a standard choice-of-law clause
        # that also selects a DIFFERENT forum, the venue-vs-governing-law trap.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-4', 'spa.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(
                0,
                "Section 11. This Agreement shall be governed by and construed "
                "in accordance with the laws of the State of Delaware; the "
                "parties submit to the exclusive jurisdiction of the courts of "
                "New York.",
            ),
        ]
        ids = insert_typed_nodes(self._conn, "contract-4", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._seed_polarity_contract()

    def _seed_polarity_contract(self) -> None:
        # Its own document (fixture isolation): a grant clause whose qualifiers
        # an AI summary classically flips.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-5', 'license-grant.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(
                0,
                "Section 2.1. Licensor hereby grants Licensee a non-exclusive, "
                "non-transferable license to use the Software during the Term.",
            ),
        ]
        ids = insert_typed_nodes(self._conn, "contract-5", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)
        self._seed_multi_value_carrier_contract()

    def _seed_multi_value_carrier_contract(self) -> None:
        # Its own document (fixture isolation): the live Kellogg false-
        # contradiction shape (2026-06-11). The clause that verbatim-supports
        # the claim bundles a SECOND money value, so its own verdict is
        # multi_value_unverifiable; a neighboring passage states a different
        # lone amount. The old presents-only veto accused the verbatim-correct
        # draft from the neighbor.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('contract-6', 'launch-plan.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        nodes = [
            _node(
                0,
                "Section 3. The advertising expenses for the product launch "
                "will generate operating losses of $20 million next year, "
                "against pre-tax income of $460 million.",
            ),
            _node(
                1,
                "Section 7. The marketing expenses for the legacy product "
                "will generate operating losses of $500 million next year.",
            ),
        ]
        ids = insert_typed_nodes(self._conn, "contract-6", nodes)
        embed_and_index_nodes(self._conn, nodes, ids, embedder=self._embedder)

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

    def test_percent_contradiction_survives_a_matching_duration(self) -> None:
        # THE laundering case from the 2026-06-10 plan, end to end over real
        # retrieval: pre-percent, the matching 12-month duration carried a green
        # "present" over a falsified 99% cap. The percent anchor must win with a
        # filing-grade reason quoting both rates.
        env = build_deterministic_envelope(
            "The royalty equals 99% of the net fees received in the preceding twelve (12) months.",
            conn=self._conn,
            doc_ids=["contract-2"],
            embedder=self._embedder,
        )
        verdict = self._verdict_for(env, "99%")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertEqual("percent", verdict["anchor_type"])
        self.assertIn("99%", verdict["detail"])
        self.assertIn("50%", verdict["detail"])

    def test_matching_percent_is_present(self) -> None:
        env = build_deterministic_envelope(
            "The royalty equals 50% of the net fees received in the preceding twelve (12) months.",
            conn=self._conn,
            doc_ids=["contract-2"],
            embedder=self._embedder,
        )
        verdict = self._verdict_for(env, "50%")
        self.assertEqual("present", verdict["disposition"])

    def test_fabricated_section_cannot_ride_a_matching_percent(self) -> None:
        # The review's live finding: a clause-checkable anchor used to suppress
        # the section-absent check entirely, so a draft citing a section the
        # contract does not contain, paired with a value that matches some
        # clause, read VERIFIED. The fabricated section is an affirmative
        # independent finding; it must demote the present to unsupported.
        draft = (
            "Under Section 99, the royalty equals 50% of the net fees received "
            "in the preceding twelve (12) months."
        )
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-2"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("Section 99", card.unsupported_reason or "")

    def test_fabricated_section_cannot_ride_a_matching_money(self) -> None:
        # The same class pre-existed for money/date/duration; the fix covers it.
        draft = "Under Section 99, the aggregate liability shall not exceed $500,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("Section 99", card.unsupported_reason or "")

    def test_a_contradiction_keeps_its_reason_over_a_fabricated_section(self) -> None:
        # Both findings are hard unsupported verdicts; the contradiction's
        # both-values detail is the more actionable filing-grade reason, so it
        # wins the reason slot.
        draft = (
            "Under Section 99, the royalty equals 99% of the net fees received "
            "in the preceding twelve (12) months."
        )
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-2"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("99%", card.unsupported_reason or "")
        self.assertIn("50%", card.unsupported_reason or "")

    def test_percent_only_sentence_routes_to_the_clause_check(self) -> None:
        # Mutant killer: percent's membership in _CLAUSE_CHECKABLE was pinned by
        # zero tests (the other percent cases co-carry a duration anchor that
        # satisfies the set on its own). A percent-only sentence must reach the
        # clause check and keep the contradiction, not fall to the grounding
        # path's could-not-check.
        draft = "The royalty equals 99% of net fees."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-2"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "99%")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

    def test_governing_law_only_sentence_routes_to_the_clause_check(self) -> None:
        # The summary flips the choice of law to the VENUE state (the classic
        # AI confusion: New York courts, Delaware law). The sentence's only
        # anchor is governing_law, so this also pins its membership in
        # _CLAUSE_CHECKABLE: it must reach the clause check and contradict, not
        # fall to the grounding path's could-not-check.
        draft = "The agreement is governed by New York law."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-4"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "governed")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertEqual("governing_law", verdict["anchor_type"])
        self.assertIn("New York", verdict["detail"])
        self.assertIn("Delaware", verdict["detail"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

    def test_governing_law_match_is_present_end_to_end(self) -> None:
        draft = "The agreement is governed by Delaware law."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-4"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "governed")
        self.assertEqual("present", verdict["disposition"])
        self.assertEqual("governing_law", verdict["anchor_type"])

    def test_polarity_flip_contradicts_end_to_end(self) -> None:
        # The classic summary error: "exclusive" claimed from a non-exclusive
        # grant. The sentence's only checkable anchor is polarity, which also
        # pins its membership in _CLAUSE_CHECKABLE.
        draft = "The agreement grants Licensee an exclusive license to use the Software."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-5"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "exclusive")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        self.assertEqual("polarity:exclusive:license", verdict["anchor_type"])
        self.assertIn("non-exclusive", verdict["detail"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

    def test_polarity_match_is_present_end_to_end(self) -> None:
        draft = "The agreement grants Licensee a non-exclusive license to use the Software."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-5"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "non-exclusive")
        self.assertEqual("present", verdict["disposition"])
        self.assertEqual("polarity:exclusive:license", verdict["anchor_type"])

    def test_same_type_conflict_refuses_instead_of_accusing_or_greenlighting(self) -> None:
        # The topicality decision, end to end: the claim's 50% is verbatim in
        # Section 4 while Section 9 carries a different percent. Whatever the
        # retrieval rank, the engine must neither accuse (the old
        # first-contradiction break) nor greenlight (present-wins would mask
        # an amended-contract conflict); it refuses with both clauses named.
        draft = "The royalty equals 50% of net fees received each quarter."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-3"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "royalty")
        self.assertEqual("conflicting_clauses", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        reason = card.unsupported_reason or ""
        self.assertIn("Section 4", reason)
        self.assertIn("Section 9", reason)
        self.assertIn("40%", reason)

    def test_verbatim_correct_claim_against_multi_value_carrier_refuses_not_accuses(self) -> None:
        # The live Kellogg false contradiction, end to end. The claim's $20
        # million is verbatim in Section 3, but that clause bundles a second
        # amount (its own verdict is multi_value_unverifiable, never a green),
        # and Section 7 states $500 million. The old presents-only veto let
        # Section 7 accuse a verbatim-correct draft; the carrier veto must
        # refuse with both clauses named instead. Never "unsupported", never
        # "verified".
        draft = (
            "The advertising expenses for the product launch will generate "
            "operating losses of $20 million next year."
        )
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-6"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "advertising expenses")
        self.assertEqual("conflicting_clauses", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)
        reason = card.unsupported_reason or ""
        self.assertIn("$20 million", reason)
        self.assertIn("$500 million", reason)
        self.assertIn("not independently checked", reason)

    def test_wrong_claim_near_multi_value_clause_still_catches_with_review_note(self) -> None:
        # Recall preserved, evidence made honest: $75 million appears nowhere
        # in contract-6, so the contradiction stands; and because Section 3 is
        # a same-type multi-value passage the engine could not align, the
        # reason says so instead of presenting the accusing clause as the
        # claim's one true counterpart.
        draft = (
            "The advertising expenses for the product launch will generate "
            "operating losses of $75 million next year."
        )
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-6"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "advertising expenses")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("could not align", card.unsupported_reason or "")

    def test_uncontested_contradiction_still_catches(self) -> None:
        # No clause in contract-3 carries 99%: the falsified value stays a
        # hard catch. The conflict rule must never soften a true contradiction.
        draft = "The royalty equals 99% of net fees received each quarter."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-3"], embedder=self._embedder
        )
        verdict = self._verdict_for(env, "royalty")
        self.assertEqual("parametric_contradiction", verdict["disposition"])
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

    def test_matching_duration_is_not_affirmed(self) -> None:
        # ADR-0013 scope-out: a matching duration is could-not-check, not affirmed.
        env = build_deterministic_envelope(
            "The confidentiality term lasts two (2) years.",
            conn=self._conn,
            doc_ids=["contract-1"],
            embedder=self._embedder,
        )
        verdict = self._verdict_for(env, "confidentiality term")
        self.assertEqual("not_found", verdict["disposition"])

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

    def test_matching_money_without_a_quote_is_could_not_check(self) -> None:
        # ADR-0013 scope-out: a matching figure with no quoted holding is no longer a
        # green "verified"; figures are never affirmed, so it is could-not-check (unknown).
        draft = "The aggregate liability shall not exceed $500,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unknown", card.verdict)

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

    def test_offtopic_clause_sharing_only_the_contract_name_is_could_not_check(self) -> None:
        # C3 (stronger than the sibling off-topic test): a contract's own name
        # ("Services Agreement") recurs in clause boilerplate across the whole
        # document, so a signing-bonus clause that shares ONLY "Services" plus a
        # coincidental $42,000 is not topically relevant to a liability-cap
        # claim. The PR #166 adjudicator vetoes an off-topic present; this pins
        # that the contract structural-name word is treated as boilerplate (a
        # _TOPIC_STOPWORDS entry), so the value cannot launder into a verified
        # present. The safe direction is could-not-check, never a false present.
        self._conn.execute(
            "INSERT INTO documents (id, filename, file_type, status, source_kind, subject_name) "
            "VALUES ('offtopic-2', 'comp2.pdf', 'pdf', 'ready', 'upload', 'Agreement')"
        )
        off = [_node(0, "The signing bonus payable under this Services Agreement is $42,000.")]
        ids = insert_typed_nodes(self._conn, "offtopic-2", off)
        embed_and_index_nodes(self._conn, off, ids, embedder=self._embedder)
        self._conn.commit()
        draft = "The liability cap under the Services Agreement is $42,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["offtopic-2"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual(
            "unknown",
            card.verdict,
            "one shared generic word must not launder an off-topic value into present",
        )

    def test_on_topic_contradiction_still_fires(self) -> None:
        # Control: the gold contradiction (shared topic words with the clause)
        # is unaffected by the topic gate.
        draft = "The aggregate liability is capped at $1,000,000."
        env = build_deterministic_envelope(
            draft, conn=self._conn, doc_ids=["contract-1"], embedder=self._embedder
        )
        card = verify_service._verify_result_from_envelope(draft, env, 0.0).claim_verdicts[0]
        self.assertEqual("unsupported", card.verdict)

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
