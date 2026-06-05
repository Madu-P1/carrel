"""Characterization net for the Verify orchestrator (Cachet extraction P0).

Pins observable verify behavior the extraction must not change, complementing
tests/test_verify.py (which pins the verified/unsupported/unknown mapping). This
file pins the gaps that the P1 grounding seam and the later strangler PRs must
preserve byte-for-byte:

  - provider provenance flows from the engine envelope onto the result + payload
  - a seeded-wrong (non-existent) case citation surfaces on the claim card
  - a draft quote absent from every cited source is never returned "verbatim"
  - a draft with no quoted spans produces no quote results

The grounding seam (grounding.ground) is mocked, so these are deterministic and
make no network, DB, or LLM calls. See docs/plans/cachet-extraction-2026-06-05.md
(P0) and docs/adr/ADR-0011-extract-cachet-strangle-carrel.md.
"""

from __future__ import annotations

import unittest
from unittest import mock

from services import verify as verify_service

_VALID_QUOTE_STATUSES = {"verbatim", "altered", "could_not_check"}


def _envelope(**overrides):
    """Default engine envelope shape; tests override fields."""
    base = {
        "answer": "stub",
        "claims": [],
        "unsupported_spans": [],
        "citations": [],
        "source_cards": [],
        "model": "claude-sonnet-4-6",
        "provider": "",
        "error": None,
    }
    base.update(overrides)
    return base


def _run(envelope, draft="The claim under audit."):
    with mock.patch.object(
        verify_service.grounding,
        "ground",
        return_value=envelope,
    ):
        return verify_service.verify_draft(
            conn=None,
            draft=draft,
            log_study_event=lambda *a, **k: None,
            fetch_recent_events=lambda *a, **k: [],
        )


class VerifyProviderProvenanceTests(unittest.TestCase):
    def test_provider_flows_from_envelope_to_result_and_payload(self) -> None:
        env = _envelope(
            provider="claude",
            claims=[
                {"text": "A grounded claim.", "citations": [{"node_id": "c1"}], "case_verdicts": []}
            ],
        )
        result = _run(env)
        self.assertEqual("claude", result.provider)
        payload = verify_service.verify_result_to_payload(result)
        self.assertEqual("claude", payload["provider"])

    def test_missing_provider_defaults_to_empty_string(self) -> None:
        env = _envelope(
            claims=[{"text": "x", "citations": [{"node_id": "c1"}], "case_verdicts": []}]
        )
        env.pop("provider")
        result = _run(env)
        self.assertEqual("", result.provider)


class VerifySeededWrongCitationTests(unittest.TestCase):
    def test_nonexistent_case_verdict_surfaces_on_card(self) -> None:
        # A seeded-wrong citation: CourtListener said the cited case does not
        # exist (status 404, exists False). The verifier must surface that batch
        # on the claim card (minus the server-internal opinion_text) so the
        # operator sees the bad cite; the claim, having a node citation, stays
        # "verified" while the failed case verdict rides alongside it.
        bad_batch = {
            "claim_index": 0,
            "ok": True,
            "verdicts": [
                {"citation": "999 U.S. 1", "status": 404, "exists": False, "case_name": None}
            ],
            "error_code": None,
            "error_message": None,
        }
        env = _envelope(
            claims=[
                {
                    "text": "Per 999 U.S. 1 the rule is X.",
                    "citations": [{"node_id": "c1"}],
                    "case_verdicts": [bad_batch],
                }
            ]
        )
        result = _run(env)
        self.assertEqual(1, len(result.claim_verdicts))
        card = result.claim_verdicts[0]
        self.assertEqual("verified", card.verdict)
        self.assertEqual(1, len(card.case_verdicts))
        self.assertEqual(404, card.case_verdicts[0]["verdicts"][0]["status"])
        self.assertFalse(card.case_verdicts[0]["verdicts"][0]["exists"])
        # the failed verdict survives serialization to the API payload
        payload = verify_service.verify_result_to_payload(result)
        self.assertEqual(
            404,
            payload["claim_verdicts"][0]["case_verdicts"][0]["verdicts"][0]["status"],
        )


class VerifyDraftQuoteTests(unittest.TestCase):
    def test_quote_absent_from_sources_is_not_verbatim(self) -> None:
        # A draft quote whose text appears in NO cited source must never come
        # back "verbatim". With a lone citation whose content does not contain
        # it, the current behavior is could_not_check. Pinned so the strangler
        # cannot silently turn a miss into a false "verbatim".
        draft = 'The court held "the defendant shall be liable for all damages herein".'
        env = _envelope(
            claims=[
                {
                    "text": "Liability claim.",
                    "citations": [
                        {
                            "node_id": "c1",
                            "document_id": "d1",
                            "content": "An unrelated sentence about something else entirely.",
                        }
                    ],
                    "case_verdicts": [],
                }
            ]
        )
        result = _run(env, draft=draft)
        self.assertEqual(1, len(result.quote_results))
        qr = result.quote_results[0]
        self.assertIn(qr["status"], _VALID_QUOTE_STATUSES)
        self.assertNotEqual("verbatim", qr["status"])
        self.assertEqual("could_not_check", qr["status"])

    def test_no_draft_quotes_means_empty_quote_results(self) -> None:
        env = _envelope(
            claims=[
                {"text": "No quotes here.", "citations": [{"node_id": "c1"}], "case_verdicts": []}
            ]
        )
        result = _run(env, draft="A plain claim with no quoted spans at all.")
        self.assertEqual((), result.quote_results)


if __name__ == "__main__":
    unittest.main()
