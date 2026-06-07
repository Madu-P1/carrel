"""Phase 5: the deterministic (no-LLM) verify envelope and its wiring.

Success criterion at the envelope/case-verdict level: a fabricated cite
yields exists=False, a real cite exists=True, anchor-free sentences route
to unsupported_spans, and the whole opener runs offline (the bundled
corpus answers via MockTransport, so no real network call is made).
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services import verify as verify_service
from services.legal.anchors import extract_anchors
from services.legal.deterministic_envelope import _grounding_verdict, build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client
from services.verify import (
    _claim_dict_to_verdict,
    _verdict_from_case_verdicts,
    _verdict_from_contract,
)


def _verdicts(claim: dict) -> list[dict]:
    return claim["case_verdicts"][0]["verdicts"]


class BuildEnvelopeTests(unittest.TestCase):
    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_fabricated_cite_is_not_found(self) -> None:
        env = self._build("As held in 999 U.S. 999, the rule applies.")
        self.assertEqual(1, len(env["claims"]))
        self.assertFalse(_verdicts(env["claims"][0])[0]["exists"])
        self.assertEqual(404, _verdicts(env["claims"][0])[0]["status"])

    def test_real_cite_exists(self) -> None:
        env = self._build("Segregation was rejected in 347 U.S. 483.")
        self.assertTrue(_verdicts(env["claims"][0])[0]["exists"])
        self.assertEqual("Brown v. Board of Education", _verdicts(env["claims"][0])[0]["case_name"])

    def test_anchor_free_sentence_is_could_not_check_not_dropped(self) -> None:
        env = self._build("The defendant acted in good faith throughout.")
        self.assertEqual([], env["unsupported_spans"])
        self.assertEqual(1, len(env["claims"]))
        self.assertIn("could_not_check_reason", env["claims"][0])
        self.assertEqual("unknown", _claim_dict_to_verdict(env["claims"][0], 0).verdict)

    def test_envelope_shape_is_deterministic(self) -> None:
        env = self._build("Per 410 F.3d 138, the rule is XYZ.")
        self.assertEqual("deterministic-v1", env["model"])
        self.assertEqual("deterministic", env["provider"])
        self.assertIsNone(env["error"])


class VerifyDraftWiringTests(unittest.TestCase):
    def test_flag_routes_verify_draft_through_the_offline_engine(self) -> None:
        # No CACHET_LOCAL_CASELAW: the engine is offline by construction, so the
        # no-client production path through verify_draft must stay local without it.
        flags = {
            "CACHET_DETERMINISTIC_VERIFY": "1",
            "COURTLISTENER_API_TOKEN": "local",
        }
        # If the LLM path were taken, this spy would be called; it must not be.
        with (
            mock.patch.dict(os.environ, flags, clear=False),
            mock.patch.object(
                verify_service.tutor_service,
                "grounded_tutor_envelope",
                side_effect=AssertionError("LLM path must not run when the flag is on"),
            ),
        ):
            result = verify_service.verify_draft(
                conn=None,
                draft="As held in 999 U.S. 999, the rule applies.",
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
        self.assertEqual("deterministic-v1", result.model)
        card = result.claim_verdicts[0]
        self.assertFalse(card.case_verdicts[0]["verdicts"][0]["exists"])

    def test_flag_off_keeps_the_llm_path(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(
                verify_service.tutor_service,
                "grounded_tutor_envelope",
                return_value={
                    "claims": [],
                    "unsupported_spans": [],
                    "model": "claude",
                    "error": None,
                },
            ) as spy,
        ):
            os.environ.pop("CACHET_DETERMINISTIC_VERIFY", None)
            verify_service.verify_draft(
                conn=None,
                draft="A claim under audit.",
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
        spy.assert_called_once()


class VerdictDerivationTests(unittest.TestCase):
    """Phase 7: derive the top-line verdict from case/contract results."""

    def test_existing_cite_is_verified(self) -> None:
        cv = ({"ok": True, "verdicts": [{"exists": True, "citation": "347 U.S. 483"}]},)
        self.assertEqual("verified", _verdict_from_case_verdicts(cv))

    def test_fabricated_cite_is_unsupported(self) -> None:
        cv = ({"ok": True, "verdicts": [{"exists": False, "citation": "999 U.S. 999"}]},)
        self.assertEqual("unsupported", _verdict_from_case_verdicts(cv))

    def test_failed_lookup_is_unknown(self) -> None:
        cv = ({"ok": False, "verdicts": []},)
        self.assertEqual("unknown", _verdict_from_case_verdicts(cv))

    def test_contract_dispositions_map(self) -> None:
        self.assertEqual("verified", _verdict_from_contract({"disposition": "present"}))
        self.assertEqual(
            "unsupported", _verdict_from_contract({"disposition": "parametric_contradiction"})
        )
        self.assertEqual("unknown", _verdict_from_contract({"disposition": "not_found"}))

    def test_contract_present_keeps_its_hedge(self) -> None:
        # A "present" finding is positive (verified) but must carry its hedge so the
        # card attests the value APPEARS in the clause, never that the claim is true.
        claim = {
            "text": "The term is two (2) years.",
            "citations": [],
            "case_verdicts": [],
            "contract_verdict": {
                "disposition": "present",
                "detail": "two (2) years appears in Section 12; review the full clause for context.",
            },
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("verified", card.verdict)
        self.assertIn("appears in", (card.unsupported_reason or "").lower())
        self.assertIn("section 12", (card.unsupported_reason or "").lower())

    def test_claim_card_fabricated_cite_unsupported_with_reason(self) -> None:
        claim = {
            "text": "Per 999 U.S. 999, X.",
            "citations": [],
            "case_verdicts": [
                {"ok": True, "verdicts": [{"exists": False, "citation": "999 U.S. 999"}]}
            ],
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("not found", (card.unsupported_reason or "").lower())

    def test_claim_card_real_cite_verified(self) -> None:
        claim = {
            "text": "Per 347 U.S. 483, X.",
            "citations": [],
            "case_verdicts": [
                {"ok": True, "verdicts": [{"exists": True, "citation": "347 U.S. 483"}]}
            ],
        }
        self.assertEqual("verified", _claim_dict_to_verdict(claim, 0).verdict)

    def test_llm_path_with_in_corpus_citations_still_verified(self) -> None:
        claim = {"text": "x", "citations": [{"content": "..."}], "case_verdicts": []}
        self.assertEqual("verified", _claim_dict_to_verdict(claim, 0).verdict)

    def test_no_anchor_claim_is_could_not_check_with_reason(self) -> None:
        claim = {
            "text": "The defendant acted in good faith.",
            "citations": [],
            "case_verdicts": [],
            "could_not_check_reason": "No verifiable anchor was found.",
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unknown", card.verdict)
        self.assertIn("anchor", (card.unsupported_reason or "").lower())


class CaptionMismatchTests(unittest.TestCase):
    """Gap fix: a fabricated caption on a real reporter number must be caught."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_fabricated_caption_on_real_number_is_flagged(self) -> None:
        env = self._build("As held in Fake v. Nobody, 347 U.S. 483, the rule applies.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(verdict["exists"])  # the number resolves
        self.assertTrue(verdict.get("caption_mismatch"))  # but to a different case
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("not the case named", (card.unsupported_reason or "").lower())

    def test_correct_caption_is_not_flagged(self) -> None:
        env = self._build("Segregation was rejected in Brown v. Board of Education, 347 U.S. 483.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(verdict["exists"])
        self.assertFalse(verdict.get("caption_mismatch"))

    def test_abbreviated_real_caption_is_not_false_flagged(self) -> None:
        env = self._build("Segregation was rejected in Brown v. Bd. of Educ., 347 U.S. 483.")
        self.assertFalse(
            env["claims"][0]["case_verdicts"][0]["verdicts"][0].get("caption_mismatch")
        )

    def test_bare_citation_without_caption_is_not_flagged(self) -> None:
        env = self._build("The rule in 347 U.S. 483 controls this dispute.")
        self.assertFalse(
            env["claims"][0]["case_verdicts"][0]["verdicts"][0].get("caption_mismatch")
        )


class AlteredQuoteTests(unittest.TestCase):
    """A quoted phrase verbatim in the cited opinion is confirmed; a phrase we cannot
    confirm is an honest could-not-check (the bundled opinion is not guaranteed
    complete), never an "altered" accusation."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_misquote_is_could_not_check_not_an_accusation(self) -> None:
        # A misquote we cannot confirm against the held opinion text is could-not-check,
        # never "altered/unsupported": the bundled opinion may be incomplete, so a
        # false "you fabricated this quote" is the malpractice direction we refuse.
        env = self._build(
            'The Court said "separate facilities are inherently equal," '
            "Brown v. Board of Education, 347 U.S. 483."
        )
        claim = env["claims"][0]
        self.assertIn("quote_could_not_check_reason", claim)
        self.assertEqual("unknown", _claim_dict_to_verdict(claim, 0).verdict)

    def test_correct_quote_is_verified(self) -> None:
        env = self._build(
            'The Court held that "Separate educational facilities are inherently '
            'unequal." Brown v. Board of Education, 347 U.S. 483.'
        )
        claim = env["claims"][0]
        self.assertNotIn("quote_could_not_check_reason", claim)
        self.assertEqual("verified", _claim_dict_to_verdict(claim, 0).verdict)

    def test_bare_cite_without_a_quote_is_verified(self) -> None:
        env = self._build("Brown v. Board of Education, 347 U.S. 483, controls this dispute.")
        self.assertNotIn("quote_could_not_check_reason", env["claims"][0])

    def test_cross_sentence_quote_is_not_attributed(self) -> None:
        # A quote whose cite is in a SEPARATE sentence is not attributed to it, so it
        # is not checked here at all (no false accusation across a sentence boundary).
        env = self._build(
            "The Court rejected segregation in unmistakable terms. "
            'It announced that separate facilities are "inherently equal" as a matter of law. '
            "The controlling authority is Brown v. Board of Education, 347 U.S. 483."
        )
        reasons = [c.get("quote_could_not_check_reason") for c in env["claims"]]
        self.assertFalse(any(reasons), "a quote was attributed across a sentence boundary")

    def test_cross_sentence_correct_quote_is_not_flagged(self) -> None:
        env = self._build(
            "The Court rejected segregation in unmistakable terms. "
            'It announced that "Separate educational facilities are inherently unequal" plainly. '
            "The controlling authority is Brown v. Board of Education, 347 U.S. 483."
        )
        reasons = [c.get("quote_could_not_check_reason") for c in env["claims"]]
        self.assertFalse(any(reasons), f"correct cross-sentence quote wrongly handled: {reasons}")

    def test_quote_with_no_nearby_cite_is_not_checked(self) -> None:
        # A quote from a non-cited source (a witness, the record) has no case cite
        # within reach and must never be accused or even checked against one.
        env = self._build('The witness testified, "I saw the defendant flee the scene."')
        reasons = [c.get("quote_could_not_check_reason") for c in env["claims"]]
        self.assertFalse(any(reasons), f"non-cited quote wrongly checked: {reasons}")

    def test_non_cited_source_quote_adjacent_to_a_cite_is_not_flagged(self) -> None:
        # The credibility-killer: a quote from a NON-cited source (a statute, the
        # record, a contract) in a sentence next to an unrelated case cite must NOT
        # be accused of being an altered quote of that case.
        env = self._build(
            "Brown v. Board of Education, 347 U.S. 483 (1954). "
            'The contract there defined the term as "any motor vehicle" for all purposes.'
        )
        reasons = [c.get("quote_could_not_check_reason") for c in env["claims"]]
        self.assertFalse(any(reasons), f"non-cited-source quote falsely accused: {reasons}")

    def test_two_verbatim_quotes_in_one_sentence_are_verified(self) -> None:
        # Lawyers routinely put two quoted phrases in one sentence. Both are verbatim
        # in Brown; the greedy span regex merges them into one run, which must NOT be
        # falsely flagged.
        env = self._build(
            'The doctrine of "separate but equal" failed because "Separate educational '
            'facilities are inherently unequal." Brown v. Board of Education, 347 U.S. 483.'
        )
        reasons = [c.get("quote_could_not_check_reason") for c in env["claims"]]
        self.assertFalse(any(reasons), f"two verbatim quotes wrongly flagged: {reasons}")


class GroundingVerdictTests(unittest.TestCase):
    """PR-2: a section reference absent from the source is a hard verdict; the
    positive direction and party anchors deliberately yield none."""

    _SRC = frozenset({"8", "7.2"})

    def test_absent_section_with_nonempty_source_is_section_absent(self) -> None:
        verdict = _grounding_verdict(
            extract_anchors("The obligations of Section 99 are incorporated."), self._SRC
        )
        self.assertIsNotNone(verdict)
        self.assertEqual("section_absent", verdict["disposition"])
        self.assertIn("Section 99", verdict["sections"])

    def test_present_section_yields_no_verdict(self) -> None:
        # Existence is not proof of the predicate; it stays could-not-check, never an
        # overclaiming "verified".
        self.assertIsNone(_grounding_verdict(extract_anchors("Per Section 8, X."), self._SRC))

    def test_glyph_form_matches_keyword_source(self) -> None:
        # A bare-glyph draft ref normalizes to the same key as a keyword source ref,
        # so "Section 7.2" in the source covers a draft "S 7.2"; only a truly absent
        # number is flagged.
        self.assertIsNone(_grounding_verdict(extract_anchors("See § 7.2 here."), self._SRC))
        self.assertEqual(
            "section_absent",
            _grounding_verdict(extract_anchors("See § 9.9 here."), self._SRC)["disposition"],
        )

    def test_empty_source_never_accuses(self) -> None:
        # The precision gate: no sections extracted from the source means the source
        # numbering may be in a form the detector misses, so we stay could-not-check.
        self.assertIsNone(_grounding_verdict(extract_anchors("Per Section 99, X."), frozenset()))

    def test_clause_checkable_anchor_suppresses_the_verdict(self) -> None:
        # ADR-0012 invariant 2: a parametric value wins, so a section ref riding
        # alongside money never produces a section_absent verdict.
        self.assertIsNone(
            _grounding_verdict(
                extract_anchors("Under Section 99, the cap is $5,000,000."), self._SRC
            )
        )

    def test_party_anchor_yields_no_verdict(self) -> None:
        # Party gets no verdict in either direction (positive overclaims; an unmatched
        # party is more often name-form variance than a fabrication).
        self.assertIsNone(_grounding_verdict(extract_anchors("Acme Inc. is liable."), self._SRC))

    def test_section_absent_card_is_unsupported_with_reason(self) -> None:
        claim = {
            "text": "The obligations of Section 99 are incorporated.",
            "citations": [],
            "case_verdicts": [],
            "section_verdict": {
                "disposition": "section_absent",
                "sections": ["Section 99"],
                "detail": "This statement references Section 99, which could not be located "
                "in the source contract.",
            },
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unsupported", card.verdict)
        self.assertIn("could not be located", (card.unsupported_reason or "").lower())


if __name__ == "__main__":
    unittest.main()
