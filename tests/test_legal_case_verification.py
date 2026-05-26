"""Tests for the per-claim case-existence verifier.

Carrel V2 Stage 1 wedge. Covers:
  - non-legal text -> ok=True, verdicts=(), no network
  - citation-shape text + no token -> ok=False with error_code
  - citation-shape text + token + found cite -> ok=True with verdict
  - citation-shape text + token + 404 cite -> ok=True with exists=False
  - failure cases (no token, 401, rate limit) propagate ok=False
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import httpx

from services.legal.case_verification import verify_claims_for_cases


def _transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class PreFilterTests(unittest.TestCase):
    def test_plain_prose_skips_network(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url)
            return httpx.Response(200, json=[])

        client = _transport(handler)
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Mitosis separates duplicated chromosomes."],
                client=client,
            )

        self.assertEqual(1, len(results))
        self.assertTrue(results[0].ok)
        self.assertEqual((), results[0].verdicts)
        self.assertEqual([], calls, "non-legal text must not call CourtListener")

    def test_empty_text_is_handled(self) -> None:
        results = verify_claims_for_cases(["", "   "])
        self.assertEqual(2, len(results))
        for verdict in results:
            self.assertTrue(verdict.ok)
            self.assertEqual((), verdict.verdicts)


class HappyPathTests(unittest.TestCase):
    def test_legal_text_with_found_cite_emits_exists_verdict(self) -> None:
        body = [
            {
                "citation": "576 U.S. 644",
                "normalized_citations": ["576 U.S. 644"],
                "start_index": 22,
                "end_index": 34,
                "status": 200,
                "error_message": "",
                "clusters": [
                    {
                        "case_name": "Obergefell v. Hodges",
                        "absolute_url": "/opinion/3038/obergefell-v-hodges/",
                        "court": "scotus",
                        "date_filed": "2015-06-26",
                    }
                ],
            }
        ]
        client = _transport(lambda req: httpx.Response(200, json=body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Same-sex marriage was recognized in 576 U.S. 644."],
                client=client,
            )

        self.assertEqual(1, len(results))
        batch = results[0]
        self.assertTrue(batch.ok)
        self.assertEqual(1, len(batch.verdicts))
        verdict = batch.verdicts[0]
        self.assertTrue(verdict.exists)
        self.assertEqual("Obergefell v. Hodges", verdict.case_name)
        self.assertEqual(200, verdict.status)

    def test_legal_text_with_fabricated_cite_emits_exists_false(self) -> None:
        body = [
            {
                "citation": "1 U.S. 200",
                "normalized_citations": ["1 U.S. 200"],
                "start_index": 0,
                "end_index": 10,
                "status": 404,
                "error_message": "Citation not found: '1 U.S. 200'",
                "clusters": [],
            }
        ]
        client = _transport(lambda req: httpx.Response(200, json=body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Per 1 U.S. 200, the rule is XYZ."],
                client=client,
            )

        self.assertTrue(results[0].ok)
        self.assertEqual(1, len(results[0].verdicts))
        self.assertFalse(results[0].verdicts[0].exists)
        self.assertEqual(404, results[0].verdicts[0].status)


class FailurePropagationTests(unittest.TestCase):
    def test_missing_token_makes_each_legal_claim_ok_false(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COURTLISTENER_API_TOKEN", None)
            results = verify_claims_for_cases(
                ["Cited 576 U.S. 644", "Plain prose claim with no cites."]
            )
        # Legal claim batch carries the failure code; non-legal stays ok.
        self.assertFalse(results[0].ok)
        self.assertEqual("courtlistener_no_api_token", results[0].error_code)
        self.assertTrue(results[1].ok)
        self.assertEqual((), results[1].verdicts)

    def test_rate_limit_makes_legal_claim_ok_false(self) -> None:
        client = _transport(lambda req: httpx.Response(429))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(["Per 576 U.S. 644 ..."], client=client)
        self.assertFalse(results[0].ok)
        self.assertEqual("courtlistener_rate_limited", results[0].error_code)


class _StubProvider:
    """Minimal stand-in for AIProvider's request_tool_call surface.
    Returns a pre-baked ClaudeCallResult so the holding-match tests
    never touch a real model."""

    def __init__(self, payload: dict, *, ok: bool = True, error_code: str | None = None):
        self._payload = payload
        self._ok = ok
        self._error_code = error_code

    def request_tool_call(self, **kwargs):
        from ai.router import ClaudeCallResult

        return ClaudeCallResult(
            ok=self._ok,
            task=kwargs.get("task", "balanced"),
            model="claude-sonnet-4-6",
            request_kind=kwargs.get("request_kind", "legal.holding_match"),
            text=None,
            json_payload=self._payload if self._ok else None,
            error_code=self._error_code,
            error_message=self._error_code,
            latency_ms=10.0,
            input_tokens=10,
            output_tokens=10,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            cache_hit=False,
            service_tier="auto",
            stop_reason="tool_use",
            request_id="req_holding_test",
        )


class CheckHoldingMatchTests(unittest.TestCase):
    """Carrel V2 half-2: check_holding_match runs the Claude verifier
    on (claim_text, opinion_text) and returns a typed verdict. Honest
    fallbacks cover empty inputs, missing provider, model errors, and
    null-supports refusals."""

    from services.legal.case_verification import check_holding_match  # noqa: E402

    def test_empty_claim_returns_no_claim_error(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="   ",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="opinion body here",
            provider=_StubProvider({}),
        )
        self.assertFalse(result.ok)
        self.assertEqual("holding_match_no_claim", result.error_code)

    def test_empty_opinion_returns_no_opinion_text_error(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="The claim",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="",
            provider=_StubProvider({}),
        )
        self.assertFalse(result.ok)
        self.assertEqual("holding_match_no_opinion_text", result.error_code)

    def test_supports_true_verdict(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="Per X v Y the rule is A.",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="We hold that the rule is A. " * 5,
            provider=_StubProvider(
                {
                    "supports": True,
                    "concern": "Opinion explicitly states the rule is A.",
                    "excerpt": "We hold that the rule is A.",
                }
            ),
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.supports)
        self.assertIn("rule is A", result.excerpt or "")

    def test_supports_false_verdict(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="Per X v Y the rule is A.",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="We hold that the rule is B, not A.",
            provider=_StubProvider(
                {
                    "supports": False,
                    "concern": "Opinion holds the rule is B, opposite of A.",
                    "excerpt": "We hold that the rule is B, not A.",
                }
            ),
        )
        self.assertTrue(result.ok)
        self.assertFalse(result.supports)
        self.assertIn("opposite", result.concern or "")

    def test_supports_null_means_model_refused_to_decide(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="The claim is vague.",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="A short snippet.",
            provider=_StubProvider(
                {"supports": None, "concern": "Excerpt insufficient.", "excerpt": ""}
            ),
        )
        self.assertTrue(result.ok)
        self.assertIsNone(result.supports)

    def test_provider_error_returns_ok_false(self) -> None:
        from services.legal.case_verification import check_holding_match as fn

        result = fn(
            claim_text="The claim",
            case_name="X v Y",
            citation="1 U.S. 1",
            opinion_text="The opinion text",
            provider=_StubProvider({}, ok=False, error_code="anthropic_overloaded"),
        )
        self.assertFalse(result.ok)
        self.assertEqual("anthropic_overloaded", result.error_code)


class VerifyClaimsWithHoldingMatchTests(unittest.TestCase):
    """End-to-end: a status=200 cite with sub_opinions triggers the
    holding-match follow-up; the returned CaseVerdict carries
    holding_match + holding_concern + holding_excerpt. A status=200
    cite with NO sub_opinions returns holding_error='no_sub_opinions'.
    A status=404 cite skips the follow-up entirely."""

    def _lookup_body(self, *, status: int, sub_opinions: list[str]) -> list:
        return [
            {
                "citation": "576 U.S. 644",
                "normalized_citations": ["576 U.S. 644"],
                "start_index": 0,
                "end_index": 12,
                "status": status,
                "error_message": "",
                "clusters": (
                    [
                        {
                            "case_name": "Obergefell v. Hodges",
                            "absolute_url": "/opinion/3038/",
                            "sub_opinions": sub_opinions,
                        }
                    ]
                    if status in {200, 300}
                    else []
                ),
            }
        ]

    def _handler(self, *, lookup_body, opinion_body=None):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "citation-lookup" in url:
                return httpx.Response(200, json=lookup_body)
            if "opinions/" in url and opinion_body is not None:
                return httpx.Response(200, json=opinion_body)
            return httpx.Response(404)

        return handler

    def test_status_200_with_sub_opinion_runs_holding_match(self) -> None:
        from services.legal.case_verification import verify_claims_for_cases

        lookup_body = self._lookup_body(
            status=200, sub_opinions=["https://example.com/opinions/1/"]
        )
        opinion_body = {"plain_text": "We hold that same-sex couples may marry."}
        client = _transport(self._handler(lookup_body=lookup_body, opinion_body=opinion_body))
        provider = _StubProvider(
            {
                "supports": True,
                "concern": "Holding directly affirms claim.",
                "excerpt": "We hold that same-sex couples may marry.",
            }
        )
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Same-sex marriage was recognized in 576 U.S. 644."],
                client=client,
                ai_provider=provider,
            )
        self.assertEqual(1, len(results))
        verdict = results[0].verdicts[0]
        self.assertTrue(verdict.exists)
        self.assertTrue(verdict.holding_match)
        self.assertIn("same-sex", verdict.holding_excerpt or "")
        self.assertIsNone(verdict.holding_error)

    def test_status_200_with_no_sub_opinion_emits_no_sub_opinions_error(self) -> None:
        from services.legal.case_verification import verify_claims_for_cases

        lookup_body = self._lookup_body(status=200, sub_opinions=[])
        client = _transport(self._handler(lookup_body=lookup_body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Per 576 U.S. 644 ..."],
                client=client,
                ai_provider=_StubProvider({}),
            )
        verdict = results[0].verdicts[0]
        self.assertTrue(verdict.exists)
        self.assertIsNone(verdict.holding_match)
        self.assertEqual("no_sub_opinions", verdict.holding_error)

    def test_status_404_skips_holding_match(self) -> None:
        from services.legal.case_verification import verify_claims_for_cases

        lookup_body = self._lookup_body(status=404, sub_opinions=[])
        client = _transport(self._handler(lookup_body=lookup_body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Per 1 U.S. 200 ..."],
                client=client,
                ai_provider=_StubProvider({}),
            )
        verdict = results[0].verdicts[0]
        self.assertFalse(verdict.exists)
        self.assertIsNone(verdict.holding_match)
        self.assertIsNone(verdict.holding_error)

    def test_enable_holding_match_false_skips_follow_up(self) -> None:
        from services.legal.case_verification import verify_claims_for_cases

        lookup_body = self._lookup_body(
            status=200, sub_opinions=["https://example.com/opinions/1/"]
        )
        opinion_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "citation-lookup" in url:
                return httpx.Response(200, json=lookup_body)
            opinion_calls.append(url)
            return httpx.Response(200, json={"plain_text": "x"})

        client = _transport(handler)
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            results = verify_claims_for_cases(
                ["Per 576 U.S. 644 ..."],
                client=client,
                ai_provider=_StubProvider({}),
                enable_holding_match=False,
            )
        verdict = results[0].verdicts[0]
        self.assertTrue(verdict.exists)
        self.assertIsNone(verdict.holding_match)
        self.assertIsNone(verdict.holding_error)
        self.assertEqual([], opinion_calls, "no opinion fetch when flag off")


if __name__ == "__main__":
    unittest.main()
