"""Phase 3: anchor detection (the T0 'what to verify' engine).

Covers the parametric canonical values (money -> cents, duration -> days,
date -> ISO), citation coverage across digit-bearing reporters, false
positives that must NOT read as citations, and the anchor/no-anchor gate.
"""

from __future__ import annotations

import unittest

from services.legal.anchors import Anchor, extract_anchors, has_anchor


def _types(span: str) -> list[str]:
    return [a.type for a in extract_anchors(span)]


def _first(span: str, kind: str) -> Anchor:
    return next(a for a in extract_anchors(span) if a.type == kind)


class MoneyAnchorTests(unittest.TestCase):
    def test_money_canonical_cents(self) -> None:
        cases = {
            "$1,000,000": 100_000_000,
            "$1.5 million": 150_000_000,
            "$250,000": 25_000_000,
            "$1M": 100_000_000,
        }
        for text, cents in cases.items():
            with self.subTest(text=text):
                self.assertEqual(cents, _first(text, "money").canonical_value)

    def test_word_form_amount_with_numeral(self) -> None:
        # "one million dollars ($1,000,000)" carries the numeral the regex reads.
        self.assertEqual(
            100_000_000, _first("one million dollars ($1,000,000)", "money").canonical_value
        )

    def test_adjective_scale_word_does_not_over_scale(self) -> None:
        # "$5 Million-dollar deal" is $5, not $5,000,000 ("Million" is an adjective).
        self.assertEqual(500, _first("a $5 Million-dollar deal", "money").canonical_value)

    def test_spaced_bare_letter_does_not_scale(self) -> None:
        # "$1.5 m" is ambiguous; do not silently scale a spaced bare letter.
        self.assertEqual(150, _first("paid $1.5 m in fees", "money").canonical_value)

    def test_three_decimal_places_round_not_truncate(self) -> None:
        # "$1.999" rounds to 200 cents, it does not truncate to $1.99.
        self.assertEqual(200, _first("$1.999", "money").canonical_value)


class DurationAnchorTests(unittest.TestCase):
    def test_duration_canonical_days(self) -> None:
        self.assertEqual(1825, _first("5 years", "duration").canonical_value)
        self.assertEqual(30, _first("30 calendar days", "duration").canonical_value)

    def test_legal_word_paren_digit_form(self) -> None:
        # "five (5) years" is the legal "word (digit)" convention.
        anchor = _first("a term of five (5) years", "duration")
        self.assertEqual(1825, anchor.canonical_value)


class DateAnchorTests(unittest.TestCase):
    def test_iso_and_long_form_both_canonicalize(self) -> None:
        self.assertEqual("2024-03-11", _first("2024-03-11", "date").canonical_value)
        self.assertEqual("2024-03-11", _first("March 11, 2024", "date").canonical_value)

    def test_invalid_date_shape_yields_no_anchor(self) -> None:
        # Date-shaped but impossible values must not become anchors.
        self.assertEqual([], [a for a in extract_anchors("2024-13-45") if a.type == "date"])
        self.assertEqual([], [a for a in extract_anchors("February 30, 2024") if a.type == "date"])


class SectionAnchorTests(unittest.TestCase):
    def test_numbered_section_is_an_anchor(self) -> None:
        self.assertIn("section", _types("see Section 9.2 of the agreement"))


class CitationAnchorTests(unittest.TestCase):
    REPORTERS = [
        "347 U.S. 483",
        "576 U.S. 644",
        "1 U.S. 200",
        "410 F.3d 138",
        "5 F.4th 99",
        "892 F.Supp.2d 1234",
        "22 Cal.4th 100",
        "123 N.Y.2d 456",
    ]

    def test_each_reporter_yields_one_citation_anchor(self) -> None:
        for reporter in self.REPORTERS:
            with self.subTest(reporter=reporter):
                cites = [
                    a for a in extract_anchors(f"See {reporter} (2020).") if a.type == "citation"
                ]
                self.assertEqual(1, len(cites), reporter)
                self.assertEqual(reporter, cites[0].text)

    def test_false_positives_are_not_citations(self) -> None:
        for noise in ["192.168.1.1", "version 1.2.3 build 456", "call me at 555 1234 today"]:
            with self.subTest(noise=noise):
                cites = [a for a in extract_anchors(noise) if a.type == "citation"]
                self.assertEqual([], cites)


class QuoteAndGateTests(unittest.TestCase):
    def test_quoted_run_is_an_anchor(self) -> None:
        anchor = _first('The court said "the rule applies" here.', "quote")
        self.assertEqual("the rule applies", anchor.text)

    def test_plain_prose_has_no_anchor(self) -> None:
        self.assertFalse(has_anchor("The party shall use best efforts to cooperate."))
        self.assertEqual([], extract_anchors("Mitosis separates duplicated chromosomes."))

    def test_one_span_can_carry_several_anchors(self) -> None:
        types = _types("Per Section 4.1, the cap is $1,000,000 for a term of 3 years.")
        self.assertIn("section", types)
        self.assertIn("money", types)
        self.assertIn("duration", types)

    def test_anchor_is_frozen(self) -> None:
        anchor = _first("$5,000", "money")
        with self.assertRaises(Exception):
            anchor.text = "x"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
