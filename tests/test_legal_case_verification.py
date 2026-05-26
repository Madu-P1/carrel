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


if __name__ == "__main__":
    unittest.main()
