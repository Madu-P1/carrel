"""Cross-detector honesty floor at the deterministic-envelope seam (added 2026-07-07).

The seven Foundry structural detectors each have their own isolation suite. This suite
locks the two properties that matter once they all run TOGETHER on the same document,
which no single-detector test exercises:

  1. NO FALSE ACCUSATION -- running all seven over an honest document (or a battery of
     conflict-adjacent-but-honest near-misses) never produces a FLAGGED finding, and no
     detector is tripped by another domain's text (cross-detector cross-talk).
  2. RECALL SURVIVES CONTEXT -- the dual: a single real conflict still surfaces when it
     is buried among six other domains' honest drafts. Honest bulk must not mask a catch.

Every finding must also satisfy StructuralFindingItem or /api/verify's response_model
500s. The honest drafts and conflicts here are the CONSISTENT / CONFLICT cases from the
seven per-detector envelope suites, consolidated so their interaction is under test.
See the Foundry universal-engine campaign notes.
"""

import unittest

from api_models import StructuralFindingItem
from services.legal.deterministic_envelope import build_deterministic_envelope

# Honest, single-domain drafts (each is a passing CONSISTENT case from its own suite).
HONEST = {
    "words_figures": "The initial term is thirty (30) days from the Effective Date.",
    "date_duration": (
        "The term runs from January 1, 2025 to December 31, 2025, a period of twelve (12) months."
    ),
    "bound_pair": (
        "Notice shall be given not less than thirty (30) days nor more than sixty (60) days "
        "before closing."
    ),
    "enumeration_count": (
        "Termination requires the following three (3) conditions: (a) notice; (b) cure period; "
        "(c) failure to cure."
    ),
    "crossref": "Section 1. Purpose.\nSection 2. Term. This is governed by Section 1.\nSection 3. Fees.",
    "temporal": (
        "The Hearing must be completed before the Filing. The Filing shall occur before the Trial."
    ),
    "table_footing": (
        "Consulting fees      $10,000\n"
        "Travel               $2,500\n"
        "Software licences    $1,200\n"
        "Total                $13,700"
    ),
}

# A real conflict per detector (each is the CONFLICT case from its own suite), paired
# with the kind-prefix its detector emits when it flags.
CONFLICT = {
    "words_figures": (
        "words_figures",
        "The initial term is thirty (40) days from the Effective Date.",
    ),
    "date_duration": (
        "date_duration",
        "The term runs from January 1, 2025 to June 30, 2025, a period of nine (9) months.",
    ),
    "bound_pair": (
        "bound_pair",
        "Notice shall be given not less than sixty (60) days nor more than thirty (30) days "
        "before closing.",
    ),
    "enumeration_count": (
        "enumeration_count",
        "Termination requires the following three (3) conditions: (a) notice; (b) cure period; "
        "(c) failure to cure; and (d) a certificate.",
    ),
    "crossref": (
        "crossref",
        "Section 1. Purpose.\nSection 2. Term.\nSection 3. Fees. Fees are governed by Section 9.",
    ),
    "temporal": (
        "temporal",
        "The Hearing must be completed before the Filing. The Filing shall occur before the Hearing.",
    ),
    "table_footing": (
        "table_footing",
        "Consulting fees      $10,000\n"
        "Travel               $2,500\n"
        "Software licences    $1,200\n"
        "Total                $14,000",  # items sum to 13,700, not 14,000
    ),
}

# Conflict-adjacent but HONEST. Each targets a specific over-firing risk.
NEAR_MISSES = [
    # multi-figure list -- the ADR-0013 subject-binding false-accusation trap
    "The agreement provides fees of $5,000, costs of $3,000, and a deposit of $2,000.",
    # a bare figure in prose that is NOT a word/figure pair
    "Section 3 incorporates 40 exhibits by reference.",
    # a word/figure pair that agrees
    "The parties shall meet within thirty (30) days of execution.",
    # an all-percentage table (non-summable -> must never be a footing conflict)
    "Marketing    40%\nEngineering  35%\nOperations   25%",
    # a correctly-footed table with magnitude suffixes
    "Series A     $1.5M\nSeries B     $500k\nTotal        $2.0M",
    # consistent bounds with parenthetical figures
    "The rent is not less than one thousand ($1,000) nor more than two thousand ($2,000) per month.",
    # a resolving cross-reference
    "Section 4. Indemnity. As limited by Section 4, the cap applies.",
    # a matching enumeration
    "The buyer has two (2) remedies: (a) repair; and (b) replacement.",
    # clean boilerplate
    "The parties agree to cooperate in good faith and to execute such further documents "
    "as may be reasonably required.",
]

COMBINED_HONEST = "\n\n".join(HONEST.values())


def _findings(draft: str) -> list[dict]:
    return list(build_deterministic_envelope(draft).get("structural_findings", []))


def _flagged(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("disposition") == "flagged"]


class EnvelopeNoFalseAccusation(unittest.TestCase):
    def test_each_honest_domain_never_flags(self):
        for name, draft in HONEST.items():
            with self.subTest(domain=name):
                self.assertEqual(
                    _flagged(_findings(draft)), [], f"{name} honest draft was falsely accused"
                )

    def test_combined_mixed_honest_document_never_flags(self):
        # All seven domains in ONE document: no detector may fire on honest content, and
        # none may be tripped by another domain's text (cross-detector cross-talk).
        self.assertEqual(_flagged(_findings(COMBINED_HONEST)), [])

    def test_adversarial_near_misses_never_flag(self):
        for i, draft in enumerate(NEAR_MISSES):
            with self.subTest(case=i):
                self.assertEqual(_flagged(_findings(draft)), [], f"near-miss #{i} falsely accused")

    def test_honest_input_adds_no_green(self):
        # The wire may only ADD flagged / could_not_check; it can never assert "supported".
        for draft in list(HONEST.values()) + NEAR_MISSES + [COMBINED_HONEST]:
            for f in _findings(draft):
                self.assertIn(f["disposition"], ("flagged", "could_not_check"))

    def test_every_finding_satisfies_the_api_contract(self):
        # REGRESSION LOCK: honest or not, every finding must validate or /api/verify 500s.
        for draft in list(HONEST.values()) + NEAR_MISSES + [COMBINED_HONEST]:
            for f in _findings(draft):
                StructuralFindingItem.model_validate(f)


class EnvelopeConflictSurvivesHonestContext(unittest.TestCase):
    """The dual of no-false-accusation: a real conflict must still surface when buried
    in a large honest document. Proves honest bulk does not mask recall."""

    def test_planted_conflict_flags_its_detector_in_honest_context(self):
        for name, (prefix, conflict) in CONFLICT.items():
            honest_context = "\n\n".join(d for k, d in HONEST.items() if k != name)
            draft = honest_context + "\n\n" + conflict
            with self.subTest(detector=name):
                kinds = {f.get("kind", "") for f in _flagged(_findings(draft))}
                self.assertTrue(
                    any(k.startswith(prefix) for k in kinds),
                    f"{name}: planted conflict not flagged in honest context; flagged={kinds}",
                )

    def test_standalone_conflict_flags_its_detector(self):
        # Grounding: each conflict flags on its own too (so the context test is meaningful).
        for name, (prefix, conflict) in CONFLICT.items():
            with self.subTest(detector=name):
                kinds = {f.get("kind", "") for f in _flagged(_findings(conflict))}
                self.assertTrue(
                    any(k.startswith(prefix) for k in kinds),
                    f"{name}: standalone conflict not flagged; flagged={kinds}",
                )


if __name__ == "__main__":
    unittest.main()
