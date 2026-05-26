"""Tests for the CourtListener citation-lookup client.

Carrel V2 Stage 1 wedge. Covers the contract that the lookup
function honors:
  - token missing -> ok=False, error_code="courtlistener_no_api_token"
    (no network)
  - empty text -> ok=True with empty hits (no network)
  - >64K chars -> ok=False, error_code="courtlistener_text_too_long"
    (no network)
  - HTTP 200 with parseable body -> ok=True with coerced hits
  - HTTP 200 with single match -> hit.exists == True (status 200)
  - HTTP 200 with 404 hit -> hit.exists == False (status 404)
  - HTTP 200 with 300 (ambiguous) -> hit.exists == False
  - HTTP 401/403 -> error_code="courtlistener_auth_rejected"
  - HTTP 429 -> error_code="courtlistener_rate_limited"
  - HTTP 5xx -> error_code="courtlistener_http_status"
  - non-JSON body -> error_code="courtlistener_invalid_json"
  - non-list payload -> error_code="courtlistener_invalid_shape"
  - httpx.HTTPError -> error_code="courtlistener_http_error"
  - cluster site-relative URL absolutized against base
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

import httpx

from services.legal import courtlistener as cl


def _client_with_response(handler) -> httpx.Client:
    """Build an httpx.Client whose transport is a custom handler.

    The handler receives an httpx.Request and returns an httpx.Response
    so we never touch the network. Idiomatic httpx test pattern.
    """
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


class TokenAndPrecheckTests(unittest.TestCase):
    def test_missing_token_returns_no_api_token_error(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COURTLISTENER_API_TOKEN", None)
            result = cl.lookup_citations_in_text("576 U.S. 644")
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_no_api_token", result.error_code)
        self.assertEqual((), result.hits)

    def test_empty_text_returns_ok_with_no_hits_and_no_network(self) -> None:
        called = []

        def handler(request: httpx.Request) -> httpx.Response:
            called.append(request.url)
            return httpx.Response(200, json=[])

        client = _client_with_response(handler)
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            result = cl.lookup_citations_in_text("   ", client=client)
        self.assertTrue(result.ok)
        self.assertEqual((), result.hits)
        self.assertEqual([], called, "empty text must not open a socket")

    def test_too_long_text_returns_text_too_long_error(self) -> None:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            result = cl.lookup_citations_in_text("a" * (64_001))
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_text_too_long", result.error_code)


class HappyPathTests(unittest.TestCase):
    def test_single_match_status_200_marks_hit_exists_true(self) -> None:
        body = [
            {
                "citation": "576 U.S. 644",
                "normalized_citations": ["576 U.S. 644"],
                "start_index": 0,
                "end_index": 12,
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

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("POST", request.method)
            self.assertIn("/api/rest/v4/citation-lookup/", str(request.url))
            self.assertEqual("Token tok", request.headers["authorization"])
            return httpx.Response(200, json=body)

        client = _client_with_response(handler)
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            result = cl.lookup_citations_in_text("576 U.S. 644 says ...", client=client)

        self.assertTrue(result.ok)
        self.assertEqual(1, len(result.hits))
        hit = result.hits[0]
        self.assertEqual("576 U.S. 644", hit.citation)
        self.assertTrue(hit.exists)
        self.assertEqual(1, len(hit.clusters))
        cluster = hit.clusters[0]
        self.assertEqual("Obergefell v. Hodges", cluster.case_name)
        self.assertTrue(cluster.absolute_url.startswith("https://www.courtlistener.com"))
        self.assertEqual("scotus", cluster.court)
        self.assertEqual("2015-06-26", cluster.date_filed)

    def test_status_404_hit_marks_exists_false(self) -> None:
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
        client = _client_with_response(lambda req: httpx.Response(200, json=body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            result = cl.lookup_citations_in_text("1 U.S. 200", client=client)
        self.assertTrue(result.ok)
        self.assertFalse(result.hits[0].exists)
        self.assertEqual(404, result.hits[0].status)

    def test_status_300_ambiguous_marks_exists_false(self) -> None:
        """Ambiguous is NOT confirmed-found. The verifier UX surfaces
        300 as 'multiple matches'; `exists` returning True there would
        misrepresent the verdict."""
        body = [
            {
                "citation": "5 U.S. 137",
                "normalized_citations": ["5 U.S. 137"],
                "start_index": 0,
                "end_index": 10,
                "status": 300,
                "error_message": "Multiple matches",
                "clusters": [{"case_name": "Multiple Cases"}, {"case_name": "Another"}],
            }
        ]
        client = _client_with_response(lambda req: httpx.Response(200, json=body))
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False):
            result = cl.lookup_citations_in_text("5 U.S. 137", client=client)
        self.assertTrue(result.ok)
        self.assertFalse(result.hits[0].exists)


class HttpErrorTests(unittest.TestCase):
    def _with_token(self):
        return mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "tok"}, clear=False)

    def test_http_401_returns_auth_rejected(self) -> None:
        client = _client_with_response(lambda req: httpx.Response(401))
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_auth_rejected", result.error_code)

    def test_http_403_returns_auth_rejected(self) -> None:
        client = _client_with_response(lambda req: httpx.Response(403))
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_auth_rejected", result.error_code)

    def test_http_429_returns_rate_limited(self) -> None:
        client = _client_with_response(lambda req: httpx.Response(429))
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_rate_limited", result.error_code)

    def test_http_500_returns_http_status(self) -> None:
        client = _client_with_response(lambda req: httpx.Response(500))
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_http_status", result.error_code)

    def test_non_json_body_returns_invalid_json(self) -> None:
        client = _client_with_response(lambda req: httpx.Response(200, content=b"<html/>"))
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_invalid_json", result.error_code)

    def test_non_list_payload_returns_invalid_shape(self) -> None:
        client = _client_with_response(
            lambda req: httpx.Response(200, content=json.dumps({"foo": "bar"}).encode())
        )
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_invalid_shape", result.error_code)

    def test_httpx_transport_error_returns_http_error(self) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        client = _client_with_response(boom)
        with self._with_token():
            result = cl.lookup_citations_in_text("text", client=client)
        self.assertFalse(result.ok)
        self.assertEqual("courtlistener_http_error", result.error_code)


if __name__ == "__main__":
    unittest.main()
