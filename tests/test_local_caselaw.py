"""Phase 4: the offline case-existence backend.

A real (in-corpus) cite resolves to exists=True; a fabricated cite is
absent -> exists=False. The MockTransport answers locally, so no real
network call is ever made.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.legal.case_verification import verify_claims_for_cases
from services.legal.local_caselaw import DEMO_CORPUS, local_caselaw_client


class LocalCaselawTests(unittest.TestCase):
    def _run(self, claim: str):
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return verify_claims_for_cases(
                [claim], client=local_caselaw_client(), enable_holding_match=False
            )

    def test_real_cite_resolves_from_corpus(self) -> None:
        results = self._run("Segregation was rejected in 347 U.S. 483.")
        self.assertTrue(results[0].ok)
        self.assertEqual(1, len(results[0].verdicts))
        verdict = results[0].verdicts[0]
        self.assertTrue(verdict.exists)
        self.assertEqual(200, verdict.status)
        self.assertEqual("Brown v. Board of Education", verdict.case_name)

    def test_fabricated_cite_is_not_found(self) -> None:
        results = self._run("As held in 999 U.S. 999, the rule applies.")
        self.assertTrue(results[0].ok)
        self.assertEqual(1, len(results[0].verdicts))
        verdict = results[0].verdicts[0]
        self.assertFalse(verdict.exists)
        self.assertEqual(404, verdict.status)

    def test_digit_reporter_cite_is_handled_offline(self) -> None:
        # A fabricated F.3d cite (the reporter class the old regex missed) is
        # detected by eyecite and reported not-found, not silently skipped.
        results = self._run("Per 410 F.3d 138, the rule is XYZ.")
        self.assertTrue(results[0].ok)
        self.assertEqual(1, len(results[0].verdicts))
        self.assertFalse(results[0].verdicts[0].exists)

    def test_plain_prose_makes_no_lookup(self) -> None:
        results = self._run("Mitosis separates duplicated chromosomes.")
        self.assertTrue(results[0].ok)
        self.assertEqual((), results[0].verdicts)

    def test_corpus_entries_are_real_scotus_cases(self) -> None:
        self.assertIn("347 U.S. 483", DEMO_CORPUS)
        self.assertEqual("scotus", DEMO_CORPUS["347 U.S. 483"].court)


if __name__ == "__main__":
    unittest.main()
