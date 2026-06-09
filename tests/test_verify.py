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

import os
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

    def test_engine_error_with_citation_claims_demotes_to_unknown(self) -> None:
        # C1 (silent-pass guard): on the LLM opt-out path the passages-only refusal
        # fallback still attaches citations while the engine reports it declined to
        # ground (ok=False + error). A citation-only "verified" must never read green
        # when grounding failed; demote to the honest could-not-check, never a silent
        # pass. Cover every error code that reaches this path, not just one.
        for code in (
            "weak_coverage",
            "grounded_tutor_unavailable",
            "grounded_tutor_disabled",
            "claude_call_failed",
        ):
            with self.subTest(error=code):
                envelope = self._envelope(
                    claims=[
                        {
                            "text": "A claim the fallback attached a passage to.",
                            "citations": [{"node_id": "c1", "snippet": "..."}],
                            "case_verdicts": [],
                        }
                    ],
                    error=code,
                    model="",
                )
                result = self._call(envelope)
                self.assertEqual(
                    "unknown",
                    result.claim_verdicts[0].verdict,
                    f"a citation-only claim under engine error {code!r} must not read verified",
                )
                self.assertEqual(0, result.summary.verified)
                self.assertIn(code, result.claim_verdicts[0].unsupported_reason or "")

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

    def test_deterministic_verdict_annotations_survive_the_wire_model(self) -> None:
        # The non-stream POST /api/verify serializes through VerifyResponse, and
        # Pydantic strips undeclared keys. The deterministic annotations
        # (bounded_corpus, the corpus manifest, the mismatch flags) must survive
        # that model, or the stream and non-stream responses disagree and a
        # bounded miss reads as the accusatory citation_not_found client-side.
        import api_models

        verdict = {
            "citation": "999 U.S. 999",
            "status": 404,
            "exists": False,
            "holding_skipped": True,
            "bounded_corpus": True,
            "corpus_scope": "demo",
            "corpus_case_count": 3,
            "corpus_as_of": "2026-06-05",
            "caption_unconfirmed": True,
            "year_mismatch": True,
            "cited_year": 1990,
            "resolved_year": 1954,
            "court_mismatch": True,
            "cited_court": "ca9",
        }
        kept = api_models.CaseVerdictItem.model_validate(verdict).model_dump()
        for key, value in verdict.items():
            self.assertEqual(value, kept.get(key), f"{key} must survive the wire model")

    def test_deterministic_envelope_carries_coverage_counts(self) -> None:
        # Coverage honesty (the untreated/could-not-check split, made visible):
        # the deterministic envelope is sentence-aligned, so the payload must
        # say how many statements there were, how many carried checkable
        # material, and how many were untreated. Without this the UI and the
        # certification can only imply that everything was checked.
        envelope = self._envelope(
            claims=[
                {"text": "Plain prose.", "citations": [], "case_verdicts": [], "untreated": True},
                {"text": "More prose.", "citations": [], "case_verdicts": [], "untreated": True},
                {
                    "text": "The cap is $5.",
                    "citations": [],
                    "case_verdicts": [],
                    "could_not_check_reason": "no source",
                },
            ],
            model="deterministic-v1",
            provider="deterministic",
        )
        result = self._call(envelope)
        payload = verify_service.verify_result_to_payload(result)
        self.assertEqual({"statements": 3, "treated": 1, "untreated": 2}, payload.get("coverage"))

    def test_llm_envelope_has_no_coverage_block(self) -> None:
        # LLM-path claims are model-extracted, not sentence-aligned, so a
        # coverage count would overstate what the engine knows. The block is
        # absent (None), and the UI falls back to the legacy copy.
        envelope = self._envelope(
            claims=[{"text": "x", "citations": [{"node_id": "c1"}], "case_verdicts": []}]
        )
        result = self._call(envelope)
        payload = verify_service.verify_result_to_payload(result)
        self.assertIsNone(payload.get("coverage"))

    def test_assessed_fields_default_none_on_the_wire(self) -> None:
        # T1 PR-2: the assessed_* tier fields exist on every card, default None, and
        # round-trip through the payload. Nothing sets them yet (the selector is dark).
        envelope = self._envelope(
            claims=[{"text": "x", "citations": [{"node_id": "c1"}], "case_verdicts": []}]
        )
        result = self._call(envelope)
        card = verify_service.verify_result_to_payload(result)["claim_verdicts"][0]
        for key in ("assessed_confidence", "assessed_model", "assessed_label"):
            self.assertIn(key, card)
            self.assertIsNone(card[key])


class CaseVerdictDerivationTests(unittest.TestCase):
    """Direct coverage for `_verdict_from_case_verdicts` and the LLM-path
    parser-divergence claim that previously produced a false accusation.
    """

    def test_existing_case_is_verified(self) -> None:
        batch = {"ok": True, "verdicts": [{"citation": "576 U.S. 644", "exists": True}]}
        self.assertEqual("verified", verify_service._verdict_from_case_verdicts((batch,)))

    def test_missing_case_is_unsupported(self) -> None:
        batch = {"ok": True, "verdicts": [{"citation": "123 Foo 456", "exists": False}]}
        self.assertEqual("unsupported", verify_service._verdict_from_case_verdicts((batch,)))

    def test_failed_batch_is_unknown(self) -> None:
        batch = {"ok": False, "verdicts": []}
        self.assertEqual("unknown", verify_service._verdict_from_case_verdicts((batch,)))

    def test_ok_batch_with_zero_verdicts_is_unknown_not_unsupported(self) -> None:
        # Parser divergence: eyecite recognized a cite the live CourtListener
        # parser did not, so the batch ran ok but examined no case. That is a
        # could-not-check, never the accusatory "a cited case does not exist."
        batch = {
            "claim_index": 0,
            "ok": True,
            "verdicts": [],
            "error_code": None,
            "error_message": None,
        }
        self.assertEqual("unknown", verify_service._verdict_from_case_verdicts((batch,)))

    def test_llm_path_parser_divergence_claim_reads_unknown(self) -> None:
        # End-to-end through the per-claim mapper on the LLM tutor path (no
        # could_not_check_reason set): a scanned cite with an empty-ok batch must
        # not read "unsupported" with a null reason -- that is a false accusation.
        card = verify_service._claim_dict_to_verdict(
            {
                "text": "Per Smith v. Jones, 123 Foo 456.",
                "citations": [],
                "case_verdicts": [
                    {
                        "claim_index": 0,
                        "ok": True,
                        "verdicts": [],
                        "error_code": None,
                        "error_message": None,
                    }
                ],
            },
            0,
        )
        self.assertEqual("unknown", card.verdict)
        self.assertIsNone(card.unsupported_reason)


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

        # Mock db.get_db so the route doesn't hit the filesystem.
        # Prior tests in the broader sweep may have left main.DB_PATH
        # pointing at a torn-down temp dir; the route's engine call
        # is already stubbed so the conn is unused.
        from contextlib import contextmanager

        @contextmanager
        def fake_db():
            yield None

        # This route test exercises the LLM path, now the explicit opt-out: the
        # /api/verify surface defaults to the deterministic engine (PR-3).
        with mock.patch.dict(os.environ, {"CACHET_DETERMINISTIC_VERIFY": "0"}, clear=False):
            with mock.patch("routes.verify.db.get_db", fake_db):
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

    def test_post_verify_defaults_to_deterministic_engine(self) -> None:
        # PR-3: the /api/verify surface defaults to the no-LLM deterministic engine
        # when the flag is unset. The LLM grounding path must NOT run, so no draft
        # text can reach CourtListener off-device on the default production path.
        from contextlib import contextmanager

        from fastapi.testclient import TestClient

        import main
        from services.local_api_security import HEADER_NAME, get_local_api_token

        @contextmanager
        def fake_db():
            yield None

        llm_calls: list[int] = []

        def llm_spy(*a, **k):
            llm_calls.append(1)
            return {}

        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            os.environ.pop("CACHET_DETERMINISTIC_VERIFY", None)  # unset -> default on
            with mock.patch("routes.verify.db.get_db", fake_db):
                with mock.patch(
                    "services.verify.tutor_service.grounded_tutor_envelope",
                    side_effect=llm_spy,
                ):
                    client = TestClient(main.app, headers={HEADER_NAME: get_local_api_token()})
                    response = client.post(
                        "/api/verify",
                        json={"draft": "As held in 999 U.S. 999, the rule applies."},
                    )

        self.assertEqual(200, response.status_code)
        self.assertEqual("deterministic-v1", response.json()["model"])
        self.assertEqual([], llm_calls, "the LLM path must not run on the default Cachet surface")

    def test_deterministic_surface_default_resolution(self) -> None:
        # Unset -> deterministic; only an explicit 0/false/no opts out to the LLM path.
        from routes.verify import _deterministic_surface_default

        cases = [
            (None, True),
            ("1", True),
            ("true", True),
            ("0", False),
            ("false", False),
            ("no", False),
            ("", True),
        ]
        for value, expected in cases:
            with mock.patch.dict(os.environ, {}, clear=False):
                if value is None:
                    os.environ.pop("CACHET_DETERMINISTIC_VERIFY", None)
                else:
                    os.environ["CACHET_DETERMINISTIC_VERIFY"] = value
                self.assertEqual(expected, _deterministic_surface_default(), f"value={value!r}")


if __name__ == "__main__":
    unittest.main()
