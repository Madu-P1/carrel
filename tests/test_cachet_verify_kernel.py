"""The cachet-verify kernel: contract algebra, adapter honesty, daemon posture.

These tests ARE the forever-API's lock. The combine() semantics, the mandatory
provenance, and the daemon's loopback/token posture are the product's honesty
promise made executable; a change that breaks one of these is a different
product, not a refactor (ADR-0015).
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from cachet_verify.adapter import verify_claim
from cachet_verify.contract import Attestation, CheckResult, attest, combine
from cachet_verify.daemon import AttestationDaemon


def _r(state: str, provenance: str = "deterministic") -> CheckResult:
    return CheckResult(state=state, provenance=provenance)  # type: ignore[arg-type]


class CombineAlgebraTests(unittest.TestCase):
    def test_altered_beats_everything(self) -> None:
        self.assertEqual("altered", combine([_r("verified"), _r("altered"), _r("verified")]))

    def test_refusal_floors_the_verdict(self) -> None:
        self.assertEqual("could_not_check", combine([_r("verified"), _r("could_not_check")]))

    def test_verified_requires_unanimity(self) -> None:
        self.assertEqual("verified", combine([_r("verified"), _r("verified")]))

    def test_silence_is_never_a_pass(self) -> None:
        self.assertEqual("could_not_check", combine([]))

    def test_altered_beats_refusal_too(self) -> None:
        # A caught fabrication is reported even when other checks abstained.
        self.assertEqual("altered", combine([_r("could_not_check"), _r("altered")]))

    def test_provenance_is_mandatory(self) -> None:
        with self.assertRaises(ValueError):
            CheckResult(state="verified", provenance="")

    def test_invalid_state_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CheckResult(state="probably_fine", provenance="deterministic")  # type: ignore[arg-type]

    def test_attest_carries_receipts(self) -> None:
        a = attest([_r("verified")])
        self.assertIsInstance(a, Attestation)
        self.assertEqual("verified", a.state)
        self.assertEqual(1, len(a.checks))


class AdapterHonestyTests(unittest.TestCase):
    SOURCE = "Net revenue for the third quarter was $2.4 billion, up 6% year over year."

    def test_altered_figure_is_altered(self) -> None:
        a = verify_claim(
            "Net revenue for the third quarter was $4.2 billion, up 6% year over year.",
            [self.SOURCE],
        )
        self.assertEqual("altered", a.state)
        self.assertTrue(any(c.state == "altered" for c in a.checks))

    def test_semantic_claim_refuses(self) -> None:
        a = verify_claim("The company is well positioned for growth.", [self.SOURCE])
        self.assertEqual("could_not_check", a.state)

    def test_fabricated_quote_is_altered_even_beside_clean_figures(self) -> None:
        a = verify_claim(
            'The CFO said "revenue tripled overnight" during the call.',
            [self.SOURCE],
        )
        self.assertEqual("altered", a.state)

    def test_no_sources_refuses(self) -> None:
        a = verify_claim("The fund totals $360 million.", [])
        self.assertEqual("could_not_check", a.state)

    def test_conflicting_sources_refuse_rather_than_pick(self) -> None:
        # One source contradicts the claim, another matches it verbatim as a
        # near-copy. The seam must refuse, never silently pick a winner.
        claim = "The termination fee is $5 million, payable within 30 days."
        contradicts = "The termination fee is $2 million, payable within 30 days."
        a = verify_claim(claim, [contradicts, claim])
        self.assertIn(a.state, ("could_not_check", "altered"))
        self.assertNotEqual("verified", a.state)

    def test_every_check_carries_provenance(self) -> None:
        a = verify_claim(
            "Net revenue for the third quarter was $4.2 billion, up 6% year over year.",
            [self.SOURCE],
        )
        for c in a.checks:
            self.assertTrue(c.provenance)


class NearCopyFlipTests(unittest.TestCase):
    """The anchor-free near-copy leg (nearcopy.py, byte-identical with the
    companion's copy): negation flips and proper-noun swaps on near-verbatim
    sentences catch deterministically; verbatim restatement of an anchor-free
    claim confirms; every guard shape refuses rather than accuses."""

    def test_negation_prefix_flip_is_altered(self) -> None:
        a = verify_claim(
            "The auditors found the internal controls were reliable.",
            ["The auditors found the internal controls were unreliable."],
        )
        self.assertEqual("altered", a.state)

    def test_dropped_not_is_altered(self) -> None:
        a = verify_claim(
            "The device is approved for pediatric use.",
            ["The device is not approved for pediatric use."],
        )
        self.assertEqual("altered", a.state)

    def test_quoted_source_polarity_flip_is_altered(self) -> None:
        # The live-smoke miss verbatim (2026-07-02): unquoted paraphrase of a
        # quoted source sentence with the polarity inverted.
        a = verify_claim(
            "The Supreme Court held that separate educational facilities are inherently equal.",
            [
                'The Supreme Court held that "separate educational facilities are inherently unequal."'
            ],
        )
        self.assertEqual("altered", a.state)

    def test_anchor_free_restatement_is_verified(self) -> None:
        s = "The committee approved the revised safety protocol without amendment."
        a = verify_claim(s, [s])
        self.assertEqual("verified", a.state)

    def test_synonym_substitution_never_accuses(self) -> None:
        a = verify_claim(
            "The results were disappointing this quarter overall.",
            ["The results were underwhelming this quarter overall."],
        )
        self.assertNotEqual("altered", a.state)

    def test_rhetorical_not_only_never_accuses(self) -> None:
        a = verify_claim(
            "The committee is not only responsible for oversight of the program.",
            ["The committee is only responsible for oversight of the program."],
        )
        self.assertNotEqual("altered", a.state)

    def test_stated_and_contradicted_refuses(self) -> None:
        claim = "The auditors found the internal controls were reliable."
        a = verify_claim(
            claim,
            ["The auditors found the internal controls were unreliable.", claim],
        )
        self.assertNotEqual("verified", a.state)
        self.assertNotEqual("altered", a.state)


class DaemonPostureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = AttestationDaemon(token="test-token-1", port=0)
        cls.daemon.start()
        cls.base = f"http://127.0.0.1:{cls.daemon.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def _post(self, payload: dict, token: str | None = "test-token-1") -> tuple[int, dict]:
        req = urllib.request.Request(
            f"{self.base}/verify",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
            | ({"X-Cachet-Token": token} if token else {}),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_round_trip_flags_an_altered_figure(self) -> None:
        status, body = self._post(
            {
                "claim": "The settlement fund totals $360 million.",
                "sources": ["The settlement fund totals $180 million."],
            }
        )
        self.assertEqual(200, status)
        self.assertEqual("altered", body["state"])
        self.assertEqual(1, body["schema_version"])
        self.assertTrue(body["checks"])
        for check in body["checks"]:
            self.assertIn("provenance", check)

    def test_rejects_a_missing_or_wrong_token(self) -> None:
        status, _ = self._post({"claim": "x", "sources": []}, token=None)
        self.assertEqual(401, status)
        status, _ = self._post({"claim": "x", "sources": []}, token="wrong")
        self.assertEqual(401, status)

    def test_get_is_refused(self) -> None:
        req = urllib.request.Request(f"{self.base}/verify", method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(405, ctx.exception.code)

    def test_malformed_body_is_a_400_not_a_crash(self) -> None:
        status, _ = self._post({"claim": 42, "sources": "nope"})
        self.assertEqual(400, status)

    def test_non_loopback_bind_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            AttestationDaemon(token="t", host="0.0.0.0")

    def test_empty_token_is_refused_at_construction(self) -> None:
        with self.assertRaises(ValueError):
            AttestationDaemon(token="")


if __name__ == "__main__":
    unittest.main()
