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
from services.legal.deterministic_envelope import build_deterministic_envelope
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
        flags = {
            "CACHET_DETERMINISTIC_VERIFY": "1",
            "CACHET_LOCAL_CASELAW": "1",
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
        self.assertFalse(env["claims"][0]["case_verdicts"][0]["verdicts"][0].get("caption_mismatch"))

    def test_bare_citation_without_caption_is_not_flagged(self) -> None:
        env = self._build("The rule in 347 U.S. 483 controls this dispute.")
        self.assertFalse(env["claims"][0]["case_verdicts"][0]["verdicts"][0].get("caption_mismatch"))


class AlteredQuoteTests(unittest.TestCase):
    """L4: a quoted run attributed to a cited case must appear verbatim in it."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_altered_quote_is_flagged(self) -> None:
        env = self._build(
            'The Court said "separate facilities are inherently equal," '
            "Brown v. Board of Education, 347 U.S. 483."
        )
        claim = env["claims"][0]
        self.assertIn("quote_altered_reason", claim)
        self.assertEqual("unsupported", _claim_dict_to_verdict(claim, 0).verdict)

    def test_correct_quote_is_not_flagged(self) -> None:
        env = self._build(
            'The Court held that "Separate educational facilities are inherently '
            'unequal." Brown v. Board of Education, 347 U.S. 483.'
        )
        claim = env["claims"][0]
        self.assertNotIn("quote_altered_reason", claim)
        self.assertEqual("verified", _claim_dict_to_verdict(claim, 0).verdict)

    def test_bare_cite_without_a_quote_is_not_flagged(self) -> None:
        env = self._build("Brown v. Board of Education, 347 U.S. 483, controls this dispute.")
        self.assertNotIn("quote_altered_reason", env["claims"][0])


if __name__ == "__main__":
    unittest.main()
