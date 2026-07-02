"""Kernel residue detectors: dosages, quantities, counts (ADR-0015 batch A).

These lock the three blind spots the 2026-07-02 parity experiment documented,
plus the honesty disciplines that make them safe: ambiguous units never
convert, year-shaped integers are not counts, accusations require a
near-verbatim context, and cross-family comparisons refuse rather than risk a
false red.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from cachet_verify.adapter import verify_claim
from cachet_verify.residue import compare_residue, extract_residue_anchors


def _spans(anchors) -> list[tuple[int, int]]:
    return [(a.start, a.end) for a in anchors]


class ResidueExtractionTests(unittest.TestCase):
    def test_dosage_mg_is_anchored_with_canonical_micrograms(self) -> None:
        anchors = extract_residue_anchors("Started on atorvastatin 5 mg nightly.")
        self.assertEqual(1, len(anchors))
        self.assertEqual("quantity", anchors[0].kind)
        self.assertEqual("mass_metric", anchors[0].dimension)
        self.assertEqual(Decimal(5000), anchors[0].canonical)

    def test_metric_mass_converts_within_family(self) -> None:
        (a,) = extract_residue_anchors("a dose of 0.5 grams")
        (b,) = extract_residue_anchors("a dose of 500 mg")
        self.assertEqual(a.canonical, b.canonical)
        self.assertEqual(a.dimension, b.dimension)

    def test_bare_single_letter_units_never_anchor(self) -> None:
        # mythos batchA-20260702 (confirmed false-accusation): "g"/"m"/"l"/"w"
        # beside a number are enumeration markers, network generations ("5G"),
        # or finance shorthand ("10m") as often as they are units. They must
        # not anchor at all; the honest verdict on such text is refusal.
        for text in (
            "Question 4 g asks for a proof.",
            "upgraded to 5G coverage",
            "a 10 m runway of budget",
            "rated 8 w overall",
            "clause 3 l applies",
        ):
            self.assertEqual([], extract_residue_anchors(text), text)

    def test_ton_and_tonne_are_isolated_dimensions(self) -> None:
        (ton,) = extract_residue_anchors("shipped 100 tons of resin")
        (tonne,) = extract_residue_anchors("shipped 100 tonnes of resin")
        self.assertNotEqual(ton.dimension, tonne.dimension)

    def test_grouped_count_is_anchored(self) -> None:
        (a,) = extract_residue_anchors("Headcount reached 1,240 at year end.")
        self.assertEqual("count", a.kind)
        self.assertEqual(Decimal(1240), a.canonical)

    def test_year_shaped_integer_is_not_a_count(self) -> None:
        self.assertEqual([], extract_residue_anchors("The program launched in 2024."))
        # But a comma-grouped form is always a count, and non-year plains are counts.
        self.assertEqual(1, len(extract_residue_anchors("produced 2,024 units-of-output")))
        self.assertEqual(1, len(extract_residue_anchors("a fleet of 12000 vehicles")))

    def test_claimed_spans_take_precedence(self) -> None:
        # "$5 million" is money (a services anchor); the residue detector must
        # not double-claim the 5 when the money span is marked claimed.
        text = "a fund of $5 million"
        dollar = text.index("$")
        self.assertEqual(
            [],
            extract_residue_anchors(text, claimed_spans=[(dollar, len(text))]),
        )

    def test_kwh_energy_family(self) -> None:
        (a,) = extract_residue_anchors("consumed 30 kWh per cycle")
        self.assertEqual("energy", a.dimension)
        self.assertEqual(Decimal(30_000), a.canonical)


class ResidueComparisonTests(unittest.TestCase):
    def _compare(self, claim: str, sentence: str):
        ca = extract_residue_anchors(claim)
        sa = extract_residue_anchors(sentence)
        return compare_residue(claim, ca, _spans(ca), sentence, sa, _spans(sa))

    def test_near_copy_value_drift_is_altered(self) -> None:
        out = self._compare(
            "Started on atorvastatin 50 mg nightly at discharge.",
            "Started on atorvastatin 5 mg nightly at discharge.",
        )
        self.assertIsNotNone(out)
        self.assertEqual("altered", out.state)
        self.assertIn("50 mg", out.detail)
        self.assertIn("5 mg", out.detail)

    def test_cross_unit_equal_value_is_verified(self) -> None:
        out = self._compare(
            "administer 0.5 grams with food.",
            "administer 500 mg with food.",
        )
        self.assertIsNotNone(out)
        self.assertEqual("verified", out.state)

    def test_ton_vs_tonne_refuses_never_accuses(self) -> None:
        out = self._compare(
            "shipped 100 tons of resin daily.",
            "shipped 100 tonnes of resin daily.",
        )
        self.assertIsNotNone(out)
        self.assertEqual("could_not_check", out.state)

    def test_non_near_copy_context_returns_none(self) -> None:
        out = self._compare(
            "The patient takes 50 mg every evening.",
            "A dose of 5 mg was prescribed at discharge alongside counseling.",
        )
        self.assertIsNone(out)

    def test_alteration_outranks_cross_family_refusal(self) -> None:
        out = self._compare(
            "mix 10 mL with 50 mg of powder.",
            "mix 10 tons with 5 mg of powder.",
        )
        self.assertIsNotNone(out)
        self.assertEqual("altered", out.state)


class ResidueAdapterIntegrationTests(unittest.TestCase):
    def test_dosage_drift_is_caught_end_to_end(self) -> None:
        a = verify_claim(
            "Started on atorvastatin 50 mg nightly at discharge.",
            ["Med list confirmed. Started on atorvastatin 5 mg nightly at discharge."],
        )
        self.assertEqual("altered", a.state)

    def test_faithful_dosage_is_confirmed(self) -> None:
        a = verify_claim(
            "Started on atorvastatin 5 mg nightly at discharge.",
            ["Med list confirmed. Started on atorvastatin 5 mg nightly at discharge."],
        )
        self.assertEqual("verified", a.state)

    def test_count_drift_is_caught(self) -> None:
        a = verify_claim(
            "Headcount reached 2,140 at year end.",
            ["Headcount reached 1,240 at year end."],
        )
        self.assertEqual("altered", a.state)

    def test_tons_drift_is_caught_same_unit(self) -> None:
        a = verify_claim(
            "The plant produces 620 tons of resin per day.",
            ["The plant produces 120 tons of resin per day."],
        )
        self.assertEqual("altered", a.state)

    def test_restatement_confirms_outright(self) -> None:
        a = verify_claim(
            "Net revenue for the third quarter was $2.4 billion, up 6% year over year.",
            ["Net revenue for the third quarter was $2.4 billion, up 6% year over year."],
        )
        self.assertEqual("verified", a.state)

    def test_restatement_plus_contradiction_refuses_as_conflict(self) -> None:
        a = verify_claim(
            "The retention bonus pool totals 1,500 shares.",
            [
                "The retention bonus pool totals 1,500 shares.\n"
                "The retention bonus pool totals 2,500 shares."
            ],
        )
        self.assertEqual("could_not_check", a.state)
        self.assertTrue(any("disagree" in c.detail for c in a.checks))

    def test_reworded_context_refuses_never_accuses(self) -> None:
        a = verify_claim(
            "The facility ships 620 tons of product every day.",
            ["Daily outbound volume at the facility is 120 tons of product."],
        )
        self.assertEqual("could_not_check", a.state)

    def test_enumeration_prose_never_accuses(self) -> None:
        # The mythos batchA-20260702 repro, locked: a sub-item marker beside a
        # number must not read as a physical-quantity contradiction.
        a = verify_claim(
            "The rubric awards a 5 g for clarity.",
            ["The rubric awards a 9 g for clarity."],
        )
        self.assertNotEqual("altered", a.state)


if __name__ == "__main__":
    unittest.main()
