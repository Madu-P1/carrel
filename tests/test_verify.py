"""Tests for the Verify-mode orchestrator (Carrel V2 Stage 1).

Covers the per-claim verdict mapping the verifier does on top of the
existing grounded-tutor engine:
  - empty draft -> ok=False, error="empty_draft"
  - engine returns claims with citations -> verdict="verified"
  - engine returns no claims + unsupported_spans -> verdict="unsupported"
  - engine itself fails (empty_retrieval / etc.) -> verdict="unknown"
  - summary counts roll up correctly
  - case_verdicts pass through onto each verdict card
"""

from __future__ import annotations

import unittest
from unittest import mock

from services import verify as verify_service


class VerifyDraftOrchestrationTests(unittest.TestCase):
    def _envelope(self, **overrides):
        """Default engine envelope shape; tests override fields."""
        base = {
            "answer": "stub",
            "claims": [],
            "unsupported_spans": [],
            "citations": [],
            "source_cards": [],
            "model": "claude-sonnet-4-6",
            "error": None,
        }
        base.update(overrides)
        return base

    def _call(self, envelope):
        with mock.patch.object(
            verify_service.tutor_service,
            "grounded_tutor_envelope",
            return_value=envelope,
        ):
            return verify_service.verify_draft(
                conn=None,
                draft="The claim under audit.",
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )

    def test_empty_draft_short_circuits_with_engine_untouched(self) -> None:
        envelope_calls = []

        def spy(*args, **kwargs):
            envelope_calls.append((args, kwargs))
            return {}

        with mock.patch.object(
            verify_service.tutor_service, "grounded_tutor_envelope", side_effect=spy
        ):
            result = verify_service.verify_draft(
                conn=None,
                draft="   ",
                log_study_event=lambda *a, **k: None,
                fetch_recent_events=lambda *a, **k: [],
            )
        self.assertFalse(result.ok)
        self.assertEqual("empty_draft", result.error)
        self.assertEqual(0, result.summary.total)
        self.assertEqual([], envelope_calls, "empty draft must not call the engine")

    def test_claim_with_citations_is_verified(self) -> None:
        envelope = self._envelope(
            claims=[
                {
                    "text": "Mitosis separates duplicated chromosomes.",
                    "citations": [{"node_id": "c1", "snippet": "..."}],
                    "case_verdicts": [],
                }
            ]
        )
        result = self._call(envelope)
        self.assertTrue(result.ok)
        self.assertEqual(1, len(result.claim_verdicts))
        self.assertEqual("verified", result.claim_verdicts[0].verdict)
        self.assertEqual(1, result.summary.verified)
        self.assertEqual(0, result.summary.unsupported)

    def test_claim_without_citations_is_unsupported(self) -> None:
        envelope = self._envelope(
            claims=[
                {
                    "text": "Unsupported model claim.",
                    "citations": [],
                    "case_verdicts": [],
                }
            ]
        )
        result = self._call(envelope)
        self.assertTrue(result.ok)
        self.assertEqual("unsupported", result.claim_verdicts[0].verdict)
        self.assertEqual(1, result.summary.unsupported)

    def test_unsupported_spans_become_verdict_cards(self) -> None:
        envelope = self._envelope(
            claims=[],
            unsupported_spans=["The corpus does not cover X.", "Y is also missing."],
        )
        result = self._call(envelope)
        self.assertEqual(2, len(result.claim_verdicts))
        for v in result.claim_verdicts:
            self.assertEqual("unsupported", v.verdict)
            self.assertIsNotNone(v.unsupported_reason)
        self.assertEqual(2, result.summary.unsupported)

    def test_engine_error_with_no_claims_emits_single_unknown_card(self) -> None:
        envelope = self._envelope(
            claims=[],
            unsupported_spans=[],
            error="empty_retrieval",
            model="",
        )
        result = self._call(envelope)
        self.assertFalse(result.ok)
        self.assertEqual("empty_retrieval", result.error)
        self.assertEqual(1, len(result.claim_verdicts))
        self.assertEqual("unknown", result.claim_verdicts[0].verdict)
        self.assertIn("empty_retrieval", result.claim_verdicts[0].unsupported_reason or "")
        self.assertEqual(1, result.summary.unknown)

    def test_mixed_claims_and_spans_aggregate_correctly(self) -> None:
        envelope = self._envelope(
            claims=[
                {
                    "text": "Verified claim.",
                    "citations": [{"node_id": "c1"}],
                    "case_verdicts": [],
                },
                {
                    "text": "Unsupported model claim.",
                    "citations": [],
                    "case_verdicts": [],
                },
            ],
            unsupported_spans=["Out-of-corpus span."],
        )
        result = self._call(envelope)
        self.assertEqual(3, result.summary.total)
        self.assertEqual(1, result.summary.verified)
        self.assertEqual(2, result.summary.unsupported)
        self.assertEqual(0, result.summary.unknown)

    def test_case_verdicts_flow_onto_verdict_card(self) -> None:
        case_batch = {
            "claim_index": 0,
            "ok": True,
            "verdicts": [
                {
                    "citation": "576 U.S. 644",
                    "status": 200,
                    "exists": True,
                    "case_name": "Obergefell v. Hodges",
                }
            ],
            "error_code": None,
            "error_message": None,
        }
        envelope = self._envelope(
            claims=[
                {
                    "text": "Per 576 U.S. 644 the rule is X.",
                    "citations": [{"node_id": "c1"}],
                    "case_verdicts": [case_batch],
                }
            ]
        )
        result = self._call(envelope)
        self.assertEqual(1, len(result.claim_verdicts))
        verdict_card = result.claim_verdicts[0]
        self.assertEqual(1, len(verdict_card.case_verdicts))
        self.assertEqual(case_batch, verdict_card.case_verdicts[0])

    def test_payload_serialization_is_json_safe(self) -> None:
        import json

        envelope = self._envelope(
            claims=[
                {
                    "text": "Claim.",
                    "citations": [{"node_id": "c1"}],
                    "case_verdicts": [],
                }
            ]
        )
        result = self._call(envelope)
        payload = verify_service.verify_result_to_payload(result)
        # round-trip through json to confirm shape is serializable
        serialized = json.dumps(payload)
        roundtripped = json.loads(serialized)
        self.assertEqual(payload["draft_text"], roundtripped["draft_text"])
        self.assertEqual(1, roundtripped["summary"]["verified"])


class VerifyRouteSmokeTests(unittest.TestCase):
    """Carrel V2 Stage 1: confirms the /api/verify route is registered,
    forwards to verify_draft, and serializes the result the same way
    the service does. Mocks the engine so the test is fast and
    doesn't require a populated DB."""

    def test_post_verify_returns_response_shape(self) -> None:
        from fastapi.testclient import TestClient

        import main
        from services.local_api_security import HEADER_NAME, get_local_api_token

        stub_envelope = {
            "answer": "stub",
            "claims": [
                {
                    "text": "Mitosis separates duplicated chromosomes.",
                    "citations": [
                        {
                            "node_id": "c1",
                            "document_id": "d1",
                            "document_name": "Bio.txt",
                            "section": "Intro",
                            "page_num": 1,
                            "snippet": "Mitosis separates chromosomes.",
                            "content": "Mitosis separates chromosomes.",
                            "score": 0.5,
                            "label": "Bio.txt · Intro",
                            "node_type": "body",
                        }
                    ],
                    "case_verdicts": [],
                }
            ],
            "unsupported_spans": [],
            "citations": [],
            "source_cards": [],
            "model": "claude-sonnet-4-6",
            "error": None,
        }

        with mock.patch(
            "services.verify.tutor_service.grounded_tutor_envelope",
            return_value=stub_envelope,
        ):
            client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})
            response = client.post("/api/verify", json={"draft": "Mitosis is the process."})

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertIn("claim_verdicts", body)
        self.assertIn("summary", body)
        self.assertEqual(1, body["summary"]["total"])
        self.assertEqual(1, body["summary"]["verified"])
        self.assertEqual("verified", body["claim_verdicts"][0]["verdict"])


if __name__ == "__main__":
    unittest.main()
