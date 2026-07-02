"""Batch F: the adversarial battery. Attack pairs engineered to make the
kernel give a WRONG confident verdict -- above all a false green on an altered
claim, secondarily a false accusation on a faithful one -- plus daemon fuzz,
cross-instance determinism, and mixed concurrent load."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request

from cachet_verify.adapter import verify_claim
from cachet_verify.certificate import attest_and_issue
from cachet_verify.daemon import AttestationDaemon
from cachet_verify.residue import extract_residue_anchors


class EuFormatAmbiguityTests(unittest.TestCase):
    """Locale attacks: the engine must never pick a locale for a number."""

    def test_eu_thousands_dot_never_accuses(self) -> None:
        # "1.000 mg" is 1000 in Frankfurt, 1 in Boston. Accusing either way
        # is a coin flip; the honest verdict refuses.
        a = verify_claim("take 1.000 mg daily.", ["take 1000 mg daily."])
        self.assertEqual("could_not_check", a.state)
        self.assertEqual([], extract_residue_anchors("take 1.000 mg daily"))

    def test_eu_decimal_comma_tail_never_anchors(self) -> None:
        # "1,5 mg" must not read as "5 mg" (the tail after the EU comma).
        self.assertEqual([], extract_residue_anchors("take 1,5 mg daily"))
        a = verify_claim("take 1,5 mg daily.", ["take 15 mg daily."])
        self.assertNotEqual("altered", a.state)

    def test_unambiguous_forms_still_anchor(self) -> None:
        self.assertEqual(1, len(extract_residue_anchors("take 500 mg daily")))
        self.assertEqual(1, len(extract_residue_anchors("take 1.5 mg daily")))
        self.assertEqual(1, len(extract_residue_anchors("ship 1,200 tons monthly")))

    def test_us_grouped_quantity_still_catches_drift(self) -> None:
        a = verify_claim(
            "The batch contains 2,400 mg of active compound.",
            ["The batch contains 1,400 mg of active compound."],
        )
        self.assertEqual("altered", a.state)


class VerdictGamingTests(unittest.TestCase):
    """Attacks on the composition rules themselves."""

    def test_padding_a_fabrication_with_true_quotes_cannot_green_it(self) -> None:
        # Attack: bury one altered figure under several verbatim quotes.
        source = (
            'The report said "margins improved materially" and "cash flow was strong". '
            "The settlement fund totals $180 million."
        )
        claim = (
            'The report said "margins improved materially" and "cash flow was strong". '
            "The settlement fund totals $360 million."
        )
        a = verify_claim(claim, [source])
        self.assertEqual("altered", a.state)

    def test_self_sourcing_the_fabrication_cannot_green_it(self) -> None:
        # Attack: append the fabricated claim itself as an extra "source".
        claim = "The settlement fund totals $360 million."
        a = verify_claim(claim, ["The settlement fund totals $180 million.", claim])
        self.assertNotEqual("verified", a.state)

    def test_unicode_confusable_digits_do_not_green(self) -> None:
        # Fullwidth digits in the claim: whatever the parse, never a green
        # against a source stating a different value.
        a = verify_claim(
            "The fee is $５ million.",
            ["The fee is $2 million."],
        )
        self.assertNotEqual("verified", a.state)

    def test_empty_and_whitespace_claims_refuse(self) -> None:
        self.assertEqual("could_not_check", verify_claim("", ["source"]).state)
        self.assertEqual("could_not_check", verify_claim("   \n  ", ["source"]).state)


class DaemonFuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = AttestationDaemon(token="fuzz-token", port=0)
        cls.daemon.start()
        cls.base = f"http://127.0.0.1:{cls.daemon.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _post_raw(self, body: bytes, token: str = "fuzz-token") -> int:
        req = urllib.request.Request(
            f"{self.base}/verify",
            data=body,
            headers={"X-Cachet-Token": token, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_garbage_bodies_get_honest_400s_and_the_daemon_survives(self) -> None:
        for body in (
            b"\xff\xfe garbage bytes",
            b"{" * 1000,
            b'{"claim": ["not", "a", "string"], "sources": []}',
            b'{"claim": "x", "sources": {"not": "a list"}}',
            b"null",
            b'"just a string"',
            json.dumps({"claim": "x" * 10_000, "sources": ["y" * 10_000]}).encode(),
        ):
            status = self._post_raw(body)
            self.assertIn(status, (200, 400), f"unexpected status {status} for {body[:30]!r}")
        # Still alive and honest afterwards.
        with urllib.request.urlopen(f"{self.base}/health", timeout=10) as resp:
            self.assertEqual(200, resp.status)

    def test_mixed_concurrent_verify_and_attest_stay_correct(self) -> None:
        results: list[str | None] = [None] * 8

        def verify_worker(i: int) -> None:
            req = urllib.request.Request(
                f"{self.base}/verify",
                data=json.dumps(
                    {
                        "claim": "The fund totals $360 million.",
                        "sources": ["The fund totals $180 million."],
                    }
                ).encode(),
                headers={"X-Cachet-Token": "fuzz-token", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                results[i] = json.loads(resp.read().decode())["state"]

        def attest_worker(i: int) -> None:
            req = urllib.request.Request(
                f"{self.base}/attest",
                data=json.dumps(
                    {
                        "draft": "The fund totals $180 million.",
                        "sources": ["The fund totals $180 million."],
                    }
                ).encode(),
                headers={"X-Cachet-Token": "fuzz-token", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                results[i] = json.loads(resp.read().decode())["state"]

        threads = [
            threading.Thread(target=verify_worker if i % 2 == 0 else attest_worker, args=(i,))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        for i, state in enumerate(results):
            self.assertEqual("altered" if i % 2 == 0 else "verified", state, f"slot {i}")


class CrossInstanceDeterminismTests(unittest.TestCase):
    def test_two_daemon_instances_issue_identical_certificates(self) -> None:
        issued = "2026-07-02T05:00:00+00:00"
        payload = json.dumps(
            {"draft": "The fund totals $360 million.", "sources": ["The fund totals $180 million."]}
        ).encode()
        certs = []
        for _ in range(2):
            daemon = AttestationDaemon(token="det-token", port=0, now=lambda: issued)
            daemon.start()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{daemon.port}/attest",
                    data=payload,
                    headers={"X-Cachet-Token": "det-token", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    certs.append(json.loads(resp.read().decode()))
            finally:
                daemon.stop()
        self.assertEqual(certs[0], certs[1])
        self.assertEqual(
            certs[0],
            attest_and_issue(
                "The fund totals $360 million.", ["The fund totals $180 million."], issued
            ),
        )


if __name__ == "__main__":
    unittest.main()
