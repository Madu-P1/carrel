"""Batch E: POST /api/attest — the app-server twin of the daemon's /attest.

Same kernel, same sealed certificate: the wire artifact must be byte-equal to
local issuance for identical inputs and clock."""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cachet_verify.certificate import attest_and_issue, verify_certificate
from routes.attest import register_attest_routes

DRAFT = (
    "Net revenue for the third quarter was $2.4 billion.\nThe settlement fund totals $360 million."
)
SOURCES = [
    "Net revenue for the third quarter was $2.4 billion.\nThe settlement fund totals $180 million."
]
ISSUED = "2026-07-02T04:00:00+00:00"


def _client() -> TestClient:
    app = FastAPI()
    register_attest_routes(app)
    return TestClient(app)


class AttestRouteTests(unittest.TestCase):
    def test_returns_a_sealed_certificate(self) -> None:
        resp = _client().post(
            "/api/attest", json={"draft": DRAFT, "sources": SOURCES, "issued_at": ISSUED}
        )
        self.assertEqual(200, resp.status_code)
        cert = resp.json()
        self.assertTrue(verify_certificate(cert))
        self.assertEqual("altered", cert["state"])

    def test_wire_matches_local_issuance_byte_for_byte(self) -> None:
        resp = _client().post(
            "/api/attest", json={"draft": DRAFT, "sources": SOURCES, "issued_at": ISSUED}
        )
        self.assertEqual(attest_and_issue(DRAFT, SOURCES, ISSUED), resp.json())

    def test_source_records_pass_through(self) -> None:
        resp = _client().post(
            "/api/attest",
            json={
                "draft": 'He said "the shipment left on Tuesday".',
                "sources": [{"text": "Partial deposition text.", "truncated": True}],
                "issued_at": ISSUED,
            },
        )
        cert = resp.json()
        # Truncated source: the quote miss refuses, never flags.
        self.assertEqual("could_not_check", cert["state"])

    def test_live_clock_still_seals(self) -> None:
        resp = _client().post("/api/attest", json={"draft": DRAFT, "sources": SOURCES})
        self.assertTrue(verify_certificate(resp.json()))

    def test_malformed_body_is_422_not_a_crash(self) -> None:
        resp = _client().post("/api/attest", json={"sources": "nope"})
        self.assertEqual(422, resp.status_code)

    def test_oversized_draft_is_rejected(self) -> None:
        # mythos batchE-20260702: the engine fan-out is superlinear, so the
        # route caps its inputs like the daemon caps its body.
        resp = _client().post("/api/attest", json={"draft": "x" * 100_001, "sources": SOURCES})
        self.assertEqual(422, resp.status_code)

    def test_oversized_sources_are_rejected(self) -> None:
        resp = _client().post(
            "/api/attest",
            json={"draft": "The fee is $5 million.", "sources": ["y" * 1_100_000] * 2},
        )
        self.assertEqual(413, resp.status_code)


if __name__ == "__main__":
    unittest.main()
