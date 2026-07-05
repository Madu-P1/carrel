"""Batch C: the demandable certificate -- seal, tamper-evidence, revalidation,
exhibit register, daemon /attest determinism, and the CLI gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

from cachet_verify.adapter import attest_draft
from cachet_verify.certificate import (
    attest_and_issue,
    issue_certificate,
    render_exhibit,
    revalidate_certificate,
    verify_certificate,
)
from cachet_verify.daemon import AttestationDaemon

DRAFT = (
    "Net revenue for the third quarter was $2.4 billion.\n"
    "The settlement fund totals $360 million.\n"
    "Momentum remains strong across the portfolio."
)
SOURCES = [
    "Net revenue for the third quarter was $2.4 billion.\nThe settlement fund totals $180 million."
]
ISSUED = "2026-07-02T03:00:00+00:00"


def _cert() -> dict:
    return attest_and_issue(DRAFT, SOURCES, ISSUED)


class CertificateSealTests(unittest.TestCase):
    def test_issuance_is_deterministic(self) -> None:
        self.assertEqual(_cert(), _cert())

    def test_seal_verifies_and_detects_tampering(self) -> None:
        cert = _cert()
        self.assertTrue(verify_certificate(cert))
        tampered = json.loads(json.dumps(cert))
        # The exact attack the certificate exists to make impossible: flipping
        # an altered verdict to verified after issuance.
        tampered["claims"][1]["state"] = "verified"
        self.assertFalse(verify_certificate(tampered))
        # State-level tampering breaks it too.
        tampered2 = json.loads(json.dumps(cert))
        tampered2["state"] = "verified"
        self.assertFalse(verify_certificate(tampered2))

    def test_revalidation_reproduces_verdicts_offline(self) -> None:
        result = revalidate_certificate(_cert(), DRAFT, SOURCES)
        self.assertTrue(result["valid"], result)

    def test_revalidation_fails_on_swapped_draft(self) -> None:
        result = revalidate_certificate(_cert(), DRAFT.replace("$360", "$180"), SOURCES)
        self.assertFalse(result["valid"])
        self.assertFalse(result["draft_ok"])

    def test_revalidation_fails_on_swapped_sources(self) -> None:
        result = revalidate_certificate(_cert(), DRAFT, ["a different record entirely"])
        self.assertFalse(result["valid"])
        self.assertFalse(result["sources_ok"])

    def test_certificate_carries_the_refusals_not_just_the_hits(self) -> None:
        cert = _cert()
        states = [c["state"] for c in cert["claims"]]
        self.assertIn("could_not_check", states)
        self.assertIn("altered", states)
        self.assertIn("verified", states)
        self.assertEqual("altered", cert["state"])


class ExhibitRegisterTests(unittest.TestCase):
    def test_exhibit_counts_and_seal_present(self) -> None:
        text = render_exhibit(_cert())
        self.assertIn("Statements examined: 3", text)
        self.assertIn("Verified against the record: 1", text)
        self.assertIn("Altered from the record: 1", text)
        self.assertIn("Could not be checked: 1", text)
        self.assertIn("Seal (SHA-256 of the canonical record):", text)

    def test_exhibit_register_stays_honest(self) -> None:
        # Voice rules: no celebratory language, no traffic-light vocabulary,
        # and the refusal disclaimer is always present.
        text = render_exhibit(_cert()).lower()
        for banned in ("passed", "green", "100%", "certified safe", "guarantee"):
            self.assertNotIn(banned, text)
        self.assertIn("neither confirmed nor accused", text)


class DaemonAttestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = AttestationDaemon(token="cert-token", port=0, now=lambda: ISSUED)
        cls.daemon.start()
        cls.base = f"http://127.0.0.1:{cls.daemon.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _attest(self) -> dict:
        req = urllib.request.Request(
            f"{self.base}/attest",
            data=json.dumps({"draft": DRAFT, "sources": SOURCES}).encode("utf-8"),
            headers={"X-Cachet-Token": "cert-token", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_attest_round_trip_is_sealed_and_deterministic(self) -> None:
        one, two = self._attest(), self._attest()
        self.assertEqual(one, two)  # injected clock -> byte-identical
        self.assertTrue(verify_certificate(one))
        self.assertEqual("altered", one["state"])

    def test_wire_certificate_matches_local_issuance(self) -> None:
        self.assertEqual(attest_and_issue(DRAFT, SOURCES, ISSUED), self._attest())


class CliGateTests(unittest.TestCase):
    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "cachet_verify", *argv],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

    def test_altered_claim_exits_1(self) -> None:
        out = self._run(
            "--claim",
            "The settlement fund totals $360 million.",
            "--source",
            "The settlement fund totals $180 million.",
        )
        self.assertEqual(1, out.returncode, out.stderr)
        self.assertIn("ALTERED", out.stdout)

    def test_verified_claim_exits_0(self) -> None:
        out = self._run(
            "--claim",
            "The settlement fund totals $180 million.",
            "--source",
            "The settlement fund totals $180 million.",
        )
        self.assertEqual(0, out.returncode, out.stderr)

    def test_uncheckable_claim_exits_2(self) -> None:
        out = self._run("--claim", "The outlook is bright.", "--source", "Numbers here.")
        self.assertEqual(2, out.returncode, out.stderr)

    def test_usage_error_exits_3_never_a_verdict_code(self) -> None:
        # mythos batchC-20260702: argparse's default exit 2 collided with the
        # could_not_check verdict code. Usage errors are 3, per the table.
        self.assertEqual(3, self._run("--bogus").returncode)
        self.assertEqual(3, self._run().returncode)

    def test_unwritable_certificate_exits_3_never_altered(self) -> None:
        # mythos batchC-20260702 (critical): an uncaught write error exited 1,
        # indistinguishable from a caught fabrication for a $?-keyed CI gate.
        out = self._run(
            "--claim",
            "The settlement fund totals $360 million.",
            "--source",
            "The settlement fund totals $360 million.",
            "--certificate",
            "/nonexistent-dir-for-cachet-test/cert.json",
        )
        self.assertEqual(3, out.returncode, out.stderr)
        self.assertIn("cannot write certificate", out.stderr)

    def test_draft_certificate_and_exhibit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            draft_path = Path(td) / "draft.txt"
            source_path = Path(td) / "source.txt"
            cert_path = Path(td) / "cert.json"
            draft_path.write_text(DRAFT, encoding="utf-8")
            source_path.write_text(SOURCES[0], encoding="utf-8")
            out = self._run(
                "--draft-file",
                str(draft_path),
                "--source-file",
                str(source_path),
                "--certificate",
                str(cert_path),
                "--exhibit",
            )
            self.assertEqual(1, out.returncode, out.stderr)  # draft carries an alteration
            self.assertIn("CACHET ATTESTATION RECORD", out.stdout)
            cert = json.loads(cert_path.read_text(encoding="utf-8"))
            self.assertTrue(verify_certificate(cert))


class CertificateShapeTests(unittest.TestCase):
    def test_issue_and_attest_draft_agree(self) -> None:
        attestation = attest_draft(DRAFT, SOURCES)
        cert = issue_certificate(DRAFT, SOURCES, attestation, ISSUED)
        self.assertEqual(attestation.state, cert["state"])
        self.assertEqual(len(attestation.claims), len(cert["claims"]))


class DraftProvenanceTests(unittest.TestCase):
    """Track D, D2: an uploaded-DOCUMENT draft names the original file and the
    extractor inside the sealed body. Additive-only: absent, the certificate is
    byte-identical to before; present, the fields are sealed and tamper-evident."""

    PROV = {"file_sha256": "a" * 64, "extractor": "pdf:native_text"}

    def test_absent_provenance_is_byte_identical_to_before(self) -> None:
        # The additivity proof: a pasted-text draft (no provenance) seals to the
        # exact same certificate whether or not the new parameter exists. This
        # is what keeps the conformance corpus and every issued cert unchanged.
        plain = attest_and_issue(DRAFT, SOURCES, ISSUED)
        also_plain = attest_and_issue(DRAFT, SOURCES, ISSUED, draft_provenance=None)
        self.assertEqual(plain, also_plain)
        self.assertNotIn("draft_file_sha256", plain)
        self.assertNotIn("draft_extractor", plain)

    def test_present_provenance_rides_the_sealed_body_and_verifies(self) -> None:
        cert = attest_and_issue(DRAFT, SOURCES, ISSUED, draft_provenance=self.PROV)
        self.assertEqual(cert["draft_file_sha256"], self.PROV["file_sha256"])
        self.assertEqual(cert["draft_extractor"], self.PROV["extractor"])
        # draft_sha256 stays the EXTRACTED-text hash (unchanged meaning).
        self.assertNotEqual(cert["draft_sha256"], cert["draft_file_sha256"])
        self.assertTrue(verify_certificate(cert))

    def test_tampering_the_file_hash_breaks_the_seal(self) -> None:
        cert = attest_and_issue(DRAFT, SOURCES, ISSUED, draft_provenance=self.PROV)
        cert["draft_file_sha256"] = "b" * 64
        self.assertFalse(verify_certificate(cert), "editing the file hash must break the seal")

    def test_half_provenance_is_dropped_not_half_sealed(self) -> None:
        # A file hash with no extractor (or vice versa) is a dishonest label;
        # the whole block is dropped, leaving a plain certificate.
        cert = attest_and_issue(
            DRAFT, SOURCES, ISSUED, draft_provenance={"file_sha256": "a" * 64, "extractor": ""}
        )
        self.assertNotIn("draft_file_sha256", cert)
        self.assertEqual(cert, attest_and_issue(DRAFT, SOURCES, ISSUED))

    def test_exhibit_names_the_file_when_present(self) -> None:
        cert = attest_and_issue(DRAFT, SOURCES, ISSUED, draft_provenance=self.PROV)
        exhibit = render_exhibit(cert)
        self.assertIn("Draft file SHA-256", exhibit)
        self.assertIn("pdf:native_text", exhibit)
        # A plain certificate's exhibit does not grow the line.
        self.assertNotIn(
            "Draft file SHA-256", render_exhibit(attest_and_issue(DRAFT, SOURCES, ISSUED))
        )


if __name__ == "__main__":
    unittest.main()
