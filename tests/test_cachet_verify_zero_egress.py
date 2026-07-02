"""Batch D: the kernel's zero-egress proof, mirrored from tests/test_zero_egress.

Forbids any real socket, then runs the kernel's full public surface -- claim
attestation, draft attestation, certificate issuance and revalidation, and the
CLI's in-process main() -- end to end. Zero-egress is the trust spine's first
promise; for the kernel package it must hold at the PACKAGE boundary, not just
inside the legal engine it currently wraps.
"""

from __future__ import annotations

import socket
import unittest
from unittest import mock


def _forbid_sockets():
    def _raise(*_args, **_kwargs):
        raise AssertionError("the attestation kernel attempted to open a real socket")

    return mock.patch.object(socket, "socket", _raise)


DRAFT = (
    "Net revenue for the third quarter was $2.4 billion.\n"
    "The settlement fund totals $360 million.\n"
    'The CEO said "we expect to close by the end of the second quarter".'
)
SOURCES = [
    "Net revenue for the third quarter was $2.4 billion.\n"
    "The settlement fund totals $180 million.\n"
    "Prepared remarks: we expect to close by the end of the second quarter."
]


class KernelZeroEgressTests(unittest.TestCase):
    def test_verify_claim_opens_no_socket(self) -> None:
        from cachet_verify.adapter import verify_claim

        with _forbid_sockets():
            a = verify_claim("The settlement fund totals $360 million.", SOURCES)
        self.assertEqual("altered", a.state)

    def test_attest_draft_and_certificate_open_no_socket(self) -> None:
        from cachet_verify.adapter import attest_draft
        from cachet_verify.certificate import (
            issue_certificate,
            revalidate_certificate,
        )

        with _forbid_sockets():
            attestation = attest_draft(DRAFT, SOURCES)
            cert = issue_certificate(DRAFT, SOURCES, attestation, "2026-07-02T03:00:00+00:00")
            result = revalidate_certificate(cert, DRAFT, SOURCES)
        self.assertTrue(result["valid"])

    def test_cli_main_opens_no_socket(self) -> None:
        from cachet_verify.__main__ import main

        with _forbid_sockets():
            code = main(
                [
                    "--claim",
                    "The settlement fund totals $360 million.",
                    "--source",
                    SOURCES[0],
                ]
            )
        self.assertEqual(1, code)  # altered

    def test_residue_and_conformance_open_no_socket(self) -> None:
        from cachet_verify.conformance import DEFAULT_CORPUS, load_corpus, run_conformance

        cases = load_corpus(DEFAULT_CORPUS)
        from cachet_verify.adapter import verify_claim

        with _forbid_sockets():
            report = run_conformance(lambda c, s: verify_claim(c, s).state, cases)
        self.assertTrue(report.conformant)


if __name__ == "__main__":
    unittest.main()
