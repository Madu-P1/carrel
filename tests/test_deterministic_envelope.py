"""Phase 5: the deterministic (no-LLM) verify envelope and its wiring.

Success criterion at the envelope/case-verdict level: a fabricated cite
yields exists=False, a real cite exists=True, anchor-free sentences route
to unsupported_spans, and the whole opener runs offline (the bundled
corpus answers via MockTransport, so no real network call is made).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import unittest
from unittest import mock

from services import verify as verify_service
from services.legal.anchors import extract_anchors
from services.legal.deterministic_envelope import _grounding_verdict, build_deterministic_envelope
from services.legal.local_caselaw import CorpusManifest, local_caselaw_client
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

    def test_anchor_free_sentence_is_untreated_not_a_card(self) -> None:
        # An anchor-free sentence has nothing checkable, so it is UNTREATED: the claim
        # carries the untreated marker (never a could-not-check reason) and produces no
        # verdict card. "Nothing to check here" is not a finding; surfacing it as a
        # could-not-verify card was the alert fatigue this split removes.
        draft = "The defendant acted in good faith throughout."
        env = self._build(draft)
        self.assertEqual([], env["unsupported_spans"])
        self.assertEqual(1, len(env["claims"]))
        claim = env["claims"][0]
        self.assertTrue(claim.get("untreated"))
        self.assertNotIn("could_not_check_reason", claim)

    def test_pure_prose_draft_yields_zero_claim_cards(self) -> None:
        # The headline regression: a clean prose draft must NOT produce a wall of
        # could-not-verify cards. Every sentence is untreated, so the envelope ->
        # VerifyResult mapping emits zero cards (a successful run, not an engine
        # failure). The draft renders as plain text.
        draft = (
            "The defendant acted in good faith throughout. "
            "The parties cooperated at every stage of the dispute."
        )
        env = self._build(draft)
        self.assertTrue(all(c.get("untreated") for c in env["claims"]))
        result = verify_service._verify_result_from_envelope(draft, env, 0.0)
        self.assertEqual((), result.claim_verdicts)
        self.assertEqual(0, result.summary.total)
        self.assertTrue(result.ok)  # zero cards is success here, not failure

    def test_real_cite_plus_prose_yields_one_card_for_the_cite_only(self) -> None:
        # A mixed draft: the cited sentence becomes a card; the anchor-free prose
        # sentence beside it is untreated and contributes no card.
        draft = (
            "Segregation was rejected in 347 U.S. 483. "
            "The court reasoned carefully about the meaning of equality."
        )
        env = self._build(draft)
        self.assertEqual(2, len(env["claims"]))
        self.assertNotIn("untreated", env["claims"][0])  # the cite
        self.assertTrue(env["claims"][1].get("untreated"))  # the prose
        result = verify_service._verify_result_from_envelope(draft, env, 0.0)
        self.assertEqual(1, len(result.claim_verdicts))
        self.assertEqual("verified", result.claim_verdicts[0].verdict)

    def test_anchor_without_a_source_stays_a_could_not_check_card(self) -> None:
        # A sentence with a checkable value (a money anchor) but no contract loaded to
        # check it against: a check was warranted and could not complete, so it stays a
        # could-not-check card, never untreated. This is the half of the split that
        # MUST keep its card.
        env = self._build("The aggregate liability cap is $5,000,000.")
        self.assertEqual(1, len(env["claims"]))
        claim = env["claims"][0]
        self.assertNotIn("untreated", claim)
        self.assertIn("could_not_check_reason", claim)
        self.assertIn("no source", claim["could_not_check_reason"].lower())
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unknown", card.verdict)

    def test_law_citation_is_not_treated_as_a_missing_case(self) -> None:
        # A regulation/statute cite (C.F.R., U.S.C., an EU Directive) is not a case.
        # Case-existence must NOT run on it, or a real regulation reads "cited case
        # not found" (a false accusation). It is the honest could-not-check instead.
        env = self._build(
            "SEC registration is waived for accredited investors (17 C.F.R. §240.501)."
        )
        self.assertEqual(1, len(env["claims"]))
        claim = env["claims"][0]
        self.assertEqual([], claim["case_verdicts"])
        self.assertIn("could_not_check_reason", claim)
        self.assertEqual("unknown", _claim_dict_to_verdict(claim, 0).verdict)

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

    def test_bounded_corpus_absent_cite_is_could_not_check(self) -> None:
        # An absent cite from the BOUNDED offline corpus is "outside my coverage" --
        # an honest could-not-check -- NOT "does not exist". The bundled corpus is not
        # the national database, so calling a real-but-unbundled case fabricated is a
        # false accusation. The national path (no bounded_corpus flag) still reads
        # unsupported, because a 404 there genuinely means "does not exist".
        bounded = (
            {
                "ok": True,
                "verdicts": [
                    {
                        "exists": False,
                        "status": 404,
                        "citation": "999 U.S. 999",
                        "bounded_corpus": True,
                    }
                ],
            },
        )
        self.assertEqual("unknown", _verdict_from_case_verdicts(bounded))
        national = (
            {
                "ok": True,
                "verdicts": [{"exists": False, "status": 404, "citation": "999 U.S. 999"}],
            },
        )
        self.assertEqual("unsupported", _verdict_from_case_verdicts(national))

    def test_bounded_caption_mismatch_still_flags(self) -> None:
        # A number that resolves to a DIFFERENT case than named is an affirmative
        # mismatch, honest even offline, so it stays a hard flag (unsupported), never
        # downgraded to could-not-check by the bounded-corpus rule.
        cv = (
            {
                "ok": True,
                "verdicts": [
                    {
                        "exists": False,
                        "status": 200,
                        "citation": "347 U.S. 483",
                        "caption_mismatch": True,
                        "bounded_corpus": True,
                    }
                ],
            },
        )
        self.assertEqual("unsupported", _verdict_from_case_verdicts(cv))

    def test_claim_card_bounded_absent_cite_is_could_not_check_with_coverage_reason(self) -> None:
        claim = {
            "text": "Per 999 U.S. 999, X.",
            "citations": [],
            "case_verdicts": [
                {
                    "ok": True,
                    "verdicts": [
                        {
                            "exists": False,
                            "status": 404,
                            "citation": "999 U.S. 999",
                            "bounded_corpus": True,
                        }
                    ],
                }
            ],
        }
        card = _claim_dict_to_verdict(claim, 0)
        self.assertEqual("unknown", card.verdict)
        self.assertIn("offline corpus", (card.unsupported_reason or "").lower())

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

    def test_half_matching_caption_downgrades_to_could_not_check(self) -> None:
        # 'Smith v. Board' on Brown's number: one populated side (Board) matches,
        # the other (Smith) names nobody in the resolved caption. The old
        # any-token rule read this VERIFIED; the honest answer is the refusal:
        # the number resolves, but the tool cannot confirm the case named, and a
        # half-wrong caption is exactly the shape a hallucinated cite takes.
        # Never the accusatory mismatch flag: 'Board' may be a legitimate short
        # form the tool cannot prove.
        env = self._build("Smith v. Board, 347 U.S. 483, controls this question.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(verdict["exists"])  # the number resolves
        self.assertFalse(verdict.get("caption_mismatch"))  # not the hard flag
        self.assertTrue(verdict.get("caption_unconfirmed"))  # the honest refusal
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unknown", card.verdict)
        reason = (card.unsupported_reason or "").lower()
        self.assertIn("brown v. board of education", reason)
        self.assertIn("confirm", reason)

    def test_correct_caption_carries_no_unconfirmed_marker(self) -> None:
        env = self._build("Segregation was rejected in Brown v. Board of Education, 347 U.S. 483.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(verdict.get("caption_unconfirmed"))
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("verified", card.verdict)


class CorpusManifestTests(unittest.TestCase):
    """D13: bounded_corpus comes from the corpus's own manifest, not a constant.

    Only a corpus whose operator attests scope="complete" may let a citation
    miss read "no such case" (the flagship catch); a demo or unattested corpus
    folds every miss to the honest could-not-check, and the copy names the
    denominator (scope, size, snapshot date) so a lawyer knows what was
    actually checked.
    """

    def _build_default(self, draft: str) -> dict:
        # No client injected: the engine builds the demo client itself, so the
        # DEMO_MANIFEST travels with it (the production default path).
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft)

    def test_demo_manifest_rides_the_default_path(self) -> None:
        env = self._build_default("As held in 999 U.S. 999, the rule applies.")
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(v["bounded_corpus"])
        self.assertEqual("demo", v["corpus_scope"])
        self.assertEqual(3, v["corpus_case_count"])
        self.assertEqual("2026-06-05", v["corpus_as_of"])
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unknown", card.verdict)
        reason = card.unsupported_reason or ""
        self.assertIn("3-case demo corpus", reason)
        self.assertIn("2026-06-05", reason)
        self.assertIn("does not establish", reason)

    def test_injected_client_without_manifest_stays_bounded_and_unattested(self) -> None:
        # Conservative fold: an injected corpus that attests nothing is treated
        # as bounded, and the copy carries no scope it cannot vouch for.
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(
                "As held in 999 U.S. 999, the rule applies.", client=local_caselaw_client()
            )
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(v["bounded_corpus"])
        self.assertNotIn("corpus_scope", v)
        self.assertEqual("unknown", _claim_dict_to_verdict(env["claims"][0], 0).verdict)

    def test_complete_manifest_turns_a_miss_into_the_catch(self) -> None:
        # The flagship conversion: a corpus attesting completeness lets a 404
        # read "no such case as of <date>" (unsupported), not could-not-check.
        manifest = CorpusManifest(scope="complete", case_count=3, as_of="2026-06-01")
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(
                "As held in 999 U.S. 999, the rule applies.",
                client=local_caselaw_client(),
                corpus_manifest=manifest,
            )
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(v["bounded_corpus"])
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unsupported", card.verdict)
        reason = card.unsupported_reason or ""
        self.assertIn("not found", reason.lower())
        self.assertIn("complete as of 2026-06-01", reason)

    def test_real_cite_still_verifies_under_the_demo_manifest(self) -> None:
        env = self._build_default(
            "Segregation was rejected in Brown v. Board of Education, 347 U.S. 483."
        )
        self.assertEqual("verified", _claim_dict_to_verdict(env["claims"][0], 0).verdict)


class CiteParentheticalMismatchTests(unittest.TestCase):
    """A real number cited with a wrong year or court refuses, never verifies.

    A wrong court-year parenthetical on a real reporter number is a common
    hallucination shape (and a common typo), so the honest verdict is the
    could-not-check refusal naming both readings, never "verified" and never
    the fabrication accusation.
    """

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_wrong_year_downgrades_to_could_not_check(self) -> None:
        env = self._build(
            "Segregation was rejected in Brown v. Board of Education, 347 U.S. 483 (1990)."
        )
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(v["exists"])  # the number resolves
        self.assertTrue(v.get("year_mismatch"))
        self.assertEqual(1990, v.get("cited_year"))
        self.assertEqual(1954, v.get("resolved_year"))
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unknown", card.verdict)
        reason = card.unsupported_reason or ""
        self.assertIn("1954", reason)
        self.assertIn("1990", reason)

    def test_correct_year_carries_no_mismatch(self) -> None:
        env = self._build(
            "Segregation was rejected in Brown v. Board of Education, 347 U.S. 483 (1954)."
        )
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(v.get("year_mismatch"))
        self.assertEqual("verified", _claim_dict_to_verdict(env["claims"][0], 0).verdict)

    def test_wrong_court_downgrades_to_could_not_check(self) -> None:
        env = self._build(
            "Segregation was rejected in Brown v. Board of Education, 347 U.S. 483 (9th Cir. 1954)."
        )
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(v.get("court_mismatch"))
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unknown", card.verdict)
        self.assertIn("court", (card.unsupported_reason or "").lower())

    def test_bare_cite_without_parenthetical_is_unaffected(self) -> None:
        env = self._build("The rule in 347 U.S. 483 controls this dispute.")
        v = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertFalse(v.get("year_mismatch"))
        self.assertFalse(v.get("court_mismatch"))


class ShortTokenCaptionTests(unittest.TestCase):
    """A caption of dotted initials or two-letter surnames on a real number must
    refuse (could-not-check), never read verified: tokenizing to nothing is not
    the same as citing bare."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_initials_caption_on_a_real_number_downgrades_to_could_not_check(self) -> None:
        env = self._build("M.L.B. v. S.L.J., 347 U.S. 483, controls.")
        verdict = env["claims"][0]["case_verdicts"][0]["verdicts"][0]
        self.assertTrue(verdict["exists"])  # the number resolves
        self.assertFalse(verdict.get("caption_mismatch"))  # never the accusation
        self.assertTrue(verdict.get("caption_unconfirmed"))  # the refusal
        self.assertEqual("unknown", _claim_dict_to_verdict(env["claims"][0], 0).verdict)

    def test_two_letter_surnames_on_a_real_number_downgrade_too(self) -> None:
        env = self._build("Ng v. Li, 347 U.S. 483, controls.")
        self.assertEqual("unknown", _claim_dict_to_verdict(env["claims"][0], 0).verdict)


class TopicGateFoldTests(unittest.TestCase):
    """The stopword filter folds BOTH sides (regression: plural stopword forms
    like "agreements"/"sections" escaped the singular-form set and earned
    topic-overlap credit, weakening the off-topic value guard)."""

    def test_plural_stopwords_earn_no_topic_credit(self) -> None:
        from services.legal.deterministic_envelope import _clause_on_topic

        self.assertFalse(
            _clause_on_topic(
                "The agreements cover the sections fully.",
                "These agreements have sections regarding unrelated matters.",
            )
        )

    def test_real_topic_words_still_credit_across_singular_plural(self) -> None:
        from services.legal.deterministic_envelope import _clause_on_topic

        self.assertTrue(
            _clause_on_topic(
                "The liability caps for damages are aggregated.",
                "Aggregate liability cap for damage claims.",
            )
        )


class CourtFormatGuardTests(unittest.TestCase):
    """court_mismatch compares courts-db ids only. A corpus whose court field is
    CourtListener's URL or display-name form must make the check vacuous, not
    flag every correct parenthetical (a blanket recall collapse)."""

    def test_non_id_resolved_court_is_vacuous_not_a_mismatch(self) -> None:
        from services.legal.deterministic_envelope import _annotate_litigator_verdicts

        batch = {
            "verdicts": [
                {
                    "citation": "347 U.S. 483",
                    "status": 200,
                    "exists": True,
                    "case_name": "Brown v. Board of Education",
                    "court": "https://www.courtlistener.com/api/rest/v4/courts/scotus/",
                    "date_filed": "1954-05-17",
                }
            ]
        }
        _annotate_litigator_verdicts(
            "Brown v. Board of Education, 347 U.S. 483 (1954), controls.", [batch]
        )
        self.assertFalse(batch["verdicts"][0].get("court_mismatch"))


class CaptionMismatchBareCiteTests(unittest.TestCase):
    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

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

    def test_clause_checkable_anchor_does_not_suppress_the_verdict(self) -> None:
        # A fabricated section is an affirmative independent finding: the old
        # suppression let "Under Section 99, the royalty equals 50%" ride a
        # matching value into a green card (2026-06-10 adversarial review). The
        # verdict is computed regardless; precedence with the clause verdict is
        # the mapping layer's call (a parametric contradiction keeps its
        # both-values reason; everything else yields to the fabricated section).
        verdict = _grounding_verdict(
            extract_anchors("Under Section 99, the cap is $5,000,000."), self._SRC
        )
        self.assertIsNotNone(verdict)
        self.assertEqual("section_absent", verdict["disposition"])

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


class TokenGuardRegressionTests(unittest.TestCase):
    """The offline litigator path must verify a real cite with NO CourtListener
    token set: the egress token gates only the live-network path, and the demo
    injects an offline MockTransport. Regression for the bug where every launch
    path except serve-cachet.py (which sets a sentinel token) read every cite as
    could-not-check. The pre-existing _build helpers all set the token, which is
    exactly why this class clears it instead.
    """

    def test_real_cite_verifies_with_no_token(self) -> None:
        cleared = {k: v for k, v in os.environ.items() if k != "COURTLISTENER_API_TOKEN"}
        with mock.patch.dict(os.environ, cleared, clear=True):
            self.assertNotIn("COURTLISTENER_API_TOKEN", os.environ)
            env = build_deterministic_envelope(
                "Brown v. Board of Education, 347 U.S. 483 (1954).",
                client=local_caselaw_client(),
            )
        self.assertTrue(_verdicts(env["claims"][0])[0]["exists"])
        self.assertEqual("verified", _claim_dict_to_verdict(env["claims"][0], 0).verdict)

    def test_absent_cite_surfaced_could_not_check_with_no_token(self) -> None:
        # Token-guard regression: the bundled mock still answers with no CourtListener
        # token (exists=False for an absent cite). The cite is surfaced for review as
        # the honest could-not-check ("outside the offline corpus"), NOT the accusatory
        # "unsupported": the bounded corpus is not the national database, so it cannot
        # honestly call a real-but-unbundled cite fabricated.
        cleared = {k: v for k, v in os.environ.items() if k != "COURTLISTENER_API_TOKEN"}
        with mock.patch.dict(os.environ, cleared, clear=True):
            env = build_deterministic_envelope(
                "Smith v. Jones, 999 U.S. 999 (2020).", client=local_caselaw_client()
            )
        self.assertFalse(_verdicts(env["claims"][0])[0]["exists"])
        card = _claim_dict_to_verdict(env["claims"][0], 0)
        self.assertEqual("unknown", card.verdict)
        self.assertIn("offline corpus", (card.unsupported_reason or "").lower())


class LazyEmbedderRegressionTests(unittest.TestCase):
    """contract_mode must not eagerly load the embedder. A litigator-only draft on
    a box with no cached embedding weights must still verify its cites instead of
    crashing the whole request; a contract sentence degrades to an honest
    could-not-check rather than raising.
    """

    def _conn_with_ready_doc(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE documents (id TEXT, status TEXT)")
        conn.execute("INSERT INTO documents VALUES ('d1', 'ready')")
        conn.execute("CREATE TABLE nodes (doc_id TEXT, verbatim_text TEXT, reading_order INTEGER)")
        conn.commit()
        return conn

    def test_litigator_cite_verifies_when_embedder_unavailable(self) -> None:
        conn = self._conn_with_ready_doc()
        with (
            mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False),
            mock.patch(
                "services.legal.deterministic_envelope.offline_embedder",
                side_effect=RuntimeError("offline weights not cached"),
            ),
        ):
            env = build_deterministic_envelope(
                "Brown v. Board of Education, 347 U.S. 483 (1954).",
                conn=conn,
                client=local_caselaw_client(),
            )
        # The litigator branch never needs the embedder, so a cold cache cannot
        # crash it; the cite still verifies.
        self.assertTrue(_verdicts(env["claims"][0])[0]["exists"])

    def test_contract_sentence_degrades_when_embedder_unavailable(self) -> None:
        conn = self._conn_with_ready_doc()
        with (
            mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False),
            mock.patch(
                "services.legal.deterministic_envelope.offline_embedder",
                side_effect=RuntimeError("offline weights not cached"),
            ),
        ):
            env = build_deterministic_envelope(
                "The annual fee is $500,000 per year.", conn=conn, client=local_caselaw_client()
            )
        claim = env["claims"][0]
        self.assertIn("could_not_check_reason", claim)
        self.assertIn("unavailable", claim["could_not_check_reason"].lower())
        self.assertEqual("unknown", _claim_dict_to_verdict(claim, 0).verdict)


class ReporterCiteSplitRegressionTests(unittest.TestCase):
    """A spaced-reporter cite ("100 F. Supp. 2d 200 (S.D.N.Y. 2000)") must stay one
    claim with its cite detected, not shatter across sentences (which defeats
    case-existence + quote grounding)."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_spaced_reporter_cite_stays_one_claim(self) -> None:
        env = self._build(
            "The rule is in Smith v. Jones, 100 F. Supp. 2d 200 (S.D.N.Y. 2000), and binds here."
        )
        self.assertEqual(1, len(env["claims"]))
        self.assertTrue(env["claims"][0]["case_verdicts"])


class QuotePanelRegressionTests(unittest.TestCase):
    """The brief-level quote panel must confirm a verbatim quote from a bundled
    opinion. Regression: deterministic verdicts carried no opinion_text, so the
    panel read could-not-check even though the same-sentence check confirmed it.
    The opinion text must never cross the wire."""

    def test_verbatim_bundled_opinion_quote_reads_verbatim(self) -> None:
        draft = (
            'The Court held that "Separate educational facilities are inherently '
            'unequal." Brown v. Board of Education, 347 U.S. 483 (1954).'
        )
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            env = build_deterministic_envelope(draft, client=local_caselaw_client())
        result = verify_service._verify_result_from_envelope(draft, env, time.perf_counter())
        payload = verify_service.verify_result_to_payload(result)
        self.assertEqual(1, len(payload["quote_results"]))
        self.assertEqual("verbatim", payload["quote_results"][0]["status"])
        self.assertNotIn("opinion_text", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
