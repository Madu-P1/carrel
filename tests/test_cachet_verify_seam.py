"""Batch B: the adjudicator swallow, draft attestation, and daemon posture v2.

Locks the seam-level honesty rules: the app's cross-clause adjudicator decides
the clause leg (a value-carrier conflict refuses with both clauses named, and
that refusal vetoes even an exact restatement); a bare value coincidence never
earns a green at this seam; drafts attest per-sentence under the one combine
algebra; truncated sources degrade quote misses to refusal; and the daemon
serves a token-free liveness endpoint plus a stable error taxonomy.
"""

from __future__ import annotations

import itertools
import json
import threading
import unittest
import urllib.error
import urllib.request

from cachet_verify.adapter import attest_draft, verify_claim
from cachet_verify.contract import CheckResult, combine
from cachet_verify.daemon import AttestationDaemon


class AdjudicatorSwallowTests(unittest.TestCase):
    def test_value_carrier_conflict_refuses_and_names_the_conflict(self) -> None:
        # One source states the claim verbatim, another contradicts the figure.
        # The adjudicator's rule 1: accusing would be a guess, so refuse -- and
        # the refusal VETOES the restatement confirmation.
        claim = "The termination fee is $5 million, payable within 30 days."
        a = verify_claim(
            claim,
            [
                "The termination fee is $2 million, payable within 30 days.",
                claim,
            ],
        )
        self.assertEqual("could_not_check", a.state)

    def test_reworded_amendment_conflict_still_vetoes_restatement(self) -> None:
        # mythos batchB-20260702 (critical), locked: the amendment states the
        # same fact in DIFFERENT words. The conflict veto must survive the
        # rewording; a verbatim restatement must not green a contradicted value.
        claim = "The Company shall pay a termination fee of $5 million."
        a = verify_claim(
            claim,
            [
                "Notwithstanding the foregoing, the applicable termination fee "
                "shall be $2 million.",
                claim,
            ],
        )
        self.assertEqual("could_not_check", a.state)

    def test_uncontested_contradiction_still_accuses(self) -> None:
        a = verify_claim(
            "The termination fee is $5 million, payable within 30 days.",
            ["The termination fee is $2 million, payable within 30 days."],
        )
        self.assertEqual("altered", a.state)

    def test_cross_fact_contradiction_never_accuses(self) -> None:
        # Floor fix (batch D): a different fact carrying a different figure is
        # not a contradiction of THIS claim. Accusing "break fee $3M" because
        # a marketing budget is $7M is a false red; the honest verdict refuses.
        a = verify_claim(
            "The break fee is $3 million.",
            ["The marketing budget for the fall campaign is $7 million."],
        )
        self.assertEqual("could_not_check", a.state)

    def test_co_located_matching_anchor_never_masks_a_caught_alteration(self) -> None:
        # mythos final-sweep (high), locked: a money drift ($900->$500) on a
        # near-verbatim sentence must read altered even though a co-located
        # DIFFERENT anchor ("1,234 units") matches. A caught RED must not be
        # downgraded to could_not_check by an unrelated confirmation.
        a = verify_claim(
            "The $900 payment covers 1,234 units.",
            ["The $500 payment covers 1,234 units."],
        )
        self.assertEqual("altered", a.state)
        # Symmetric control: count drifts, money matches -> still altered.
        b = verify_claim(
            "The $500 payment covers 2,234 units.",
            ["The $500 payment covers 1,234 units."],
        )
        self.assertEqual("altered", b.state)

    def test_same_fact_cross_source_disagreement_still_refuses(self) -> None:
        # The genuine case the veto DOES exist for: the same dosage confirmed
        # in one source sentence and contradicted in another.
        a = verify_claim(
            "The patient takes 5 mg nightly.",
            ["The patient takes 5 mg nightly.\nThe patient takes 50 mg nightly."],
        )
        self.assertEqual("could_not_check", a.state)

    def test_true_accusation_names_the_same_fact_clause(self) -> None:
        # Evidence quality (batch D): when a same-fact contradiction exists,
        # the filing-grade detail must cite IT, not a cross-fact figure that
        # happened to rank earlier.
        a = verify_claim(
            "The settlement fund totals $360 million.",
            [
                "Net revenue for the third quarter was $2.4 billion.\n"
                "The settlement fund totals $180 million."
            ],
        )
        self.assertEqual("altered", a.state)
        detail = next(c.detail for c in a.checks if c.state == "altered")
        self.assertIn("$180 million", detail)
        self.assertNotIn("$2.4 billion", detail)

    def test_bare_value_coincidence_never_greens(self) -> None:
        # The claim's figure appears in an unrelated sentence. With no
        # relevance signal at this seam, confirming would be a C3 violation;
        # the honest verdict is refusal.
        a = verify_claim(
            "The break fee is capped at $3 million under the merger terms.",
            ["The marketing budget for the fall campaign is $3 million."],
        )
        self.assertEqual("could_not_check", a.state)


class DraftAttestationTests(unittest.TestCase):
    SOURCES = [
        "Net revenue for the third quarter was $2.4 billion.\n"
        "The settlement fund totals $180 million.\n"
        "Started on atorvastatin 5 mg nightly at discharge."
    ]

    def test_mixed_draft_attests_per_sentence_and_combines_altered(self) -> None:
        draft = (
            "Net revenue for the third quarter was $2.4 billion.\n"
            "The settlement fund totals $360 million.\n"
            "Momentum remains strong across the portfolio."
        )
        d = attest_draft(draft, self.SOURCES)
        self.assertEqual(3, len(d.claims))
        states = [c.attestation.state for c in d.claims]
        self.assertEqual("verified", states[0])  # restatement
        self.assertEqual("altered", states[1])  # 360 vs 180
        self.assertEqual("could_not_check", states[2])  # semantic
        self.assertEqual("altered", d.state)  # altered dominates the draft

    def test_all_verified_draft_is_verified(self) -> None:
        d = attest_draft(
            "Net revenue for the third quarter was $2.4 billion.",
            self.SOURCES,
        )
        self.assertEqual("verified", d.state)

    def test_clean_but_uncheckable_draft_refuses(self) -> None:
        d = attest_draft("The outlook is bright.", self.SOURCES)
        self.assertEqual("could_not_check", d.state)

    def test_empty_draft_refuses(self) -> None:
        self.assertEqual("could_not_check", attest_draft("   ", self.SOURCES).state)


class CombinePropertyTests(unittest.TestCase):
    def test_combine_is_order_invariant(self) -> None:
        results = [
            CheckResult(state="verified", provenance="deterministic"),
            CheckResult(state="could_not_check", provenance="deterministic"),
            CheckResult(state="altered", provenance="deterministic"),
            CheckResult(state="verified", provenance="deterministic"),
        ]
        verdicts = {combine(list(p)) for p in itertools.permutations(results)}
        self.assertEqual({"altered"}, verdicts)

    def test_combine_without_altered_is_order_invariant_too(self) -> None:
        results = [
            CheckResult(state="verified", provenance="deterministic"),
            CheckResult(state="could_not_check", provenance="deterministic"),
        ]
        verdicts = {combine(list(p)) for p in itertools.permutations(results)}
        self.assertEqual({"could_not_check"}, verdicts)

    def test_verify_claim_is_deterministic(self) -> None:
        claim = "The settlement fund totals $360 million."
        sources = ["The settlement fund totals $180 million."]
        a1 = verify_claim(claim, sources)
        a2 = verify_claim(claim, sources)
        self.assertEqual(a1, a2)


class TruncationHonestyTests(unittest.TestCase):
    def test_quote_missing_from_truncated_source_refuses_not_flags(self) -> None:
        a = verify_claim(
            'The witness said "the shipment left on Tuesday morning".',
            [{"text": "Deposition excerpt: the schedule was disputed.", "truncated": True}],
        )
        quote_checks = [c for c in a.checks if c.subject.startswith("the shipment")]
        self.assertEqual(1, len(quote_checks))
        self.assertEqual("could_not_check", quote_checks[0].state)

    def test_quote_missing_from_complete_source_flags(self) -> None:
        a = verify_claim(
            'The witness said "the shipment left on Tuesday morning".',
            ["Deposition excerpt: the schedule was disputed and nothing more was said."],
        )
        self.assertEqual("altered", a.state)


class DaemonPostureV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.daemon = AttestationDaemon(token="batch-b-token", port=0)
        cls.daemon.start()
        cls.base = f"http://127.0.0.1:{cls.daemon.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.daemon.stop()

    def test_health_needs_no_token_and_leaks_nothing(self) -> None:
        with urllib.request.urlopen(f"{self.base}/health", timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        self.assertEqual({"ok": True, "schema_version": 1}, body)

    def test_error_taxonomy_is_stable_codes(self) -> None:
        req = urllib.request.Request(
            f"{self.base}/verify",
            data=b"{}",
            headers={"X-Cachet-Token": "wrong"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual("unauthorized", body["error"]["code"])

    def test_concurrent_requests_get_independent_correct_verdicts(self) -> None:
        cases = [
            ("The fund totals $360 million.", "The fund totals $180 million.", "altered"),
            ("The fund totals $180 million.", "The fund totals $180 million.", "verified"),
            ("The outlook is bright.", "The fund totals $180 million.", "could_not_check"),
        ] * 3
        results: list[tuple[int, str]] = [None] * len(cases)  # type: ignore[list-item]

        def worker(i: int, claim: str, source: str) -> None:
            req = urllib.request.Request(
                f"{self.base}/verify",
                data=json.dumps({"claim": claim, "sources": [source]}).encode("utf-8"),
                headers={"X-Cachet-Token": "batch-b-token", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                results[i] = (resp.status, json.loads(resp.read().decode("utf-8"))["state"])

        threads = [
            threading.Thread(target=worker, args=(i, claim, source))
            for i, (claim, source, _) in enumerate(cases)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        for i, (_claim, _source, expected) in enumerate(cases):
            self.assertIsNotNone(results[i], f"request {i} never completed")
            self.assertEqual((200, expected), results[i], f"request {i}")


if __name__ == "__main__":
    unittest.main()
