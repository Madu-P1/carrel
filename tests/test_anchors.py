"""Phase 3: anchor detection (the T0 'what to verify' engine).

Covers the parametric canonical values (money -> cents, duration -> days,
date -> ISO), citation coverage across digit-bearing reporters, false
positives that must NOT read as citations, and the anchor/no-anchor gate.
"""

from __future__ import annotations

import unittest

from services.legal.anchors import Anchor, build_alias_table, extract_anchors, has_anchor


def _types(span: str) -> list[str]:
    return [a.type for a in extract_anchors(span)]


def _first(span: str, kind: str) -> Anchor:
    return next(a for a in extract_anchors(span) if a.type == kind)


def _of(span: str, kind: str) -> list[Anchor]:
    return [a for a in extract_anchors(span) if a.type == kind]


def _texts(span: str, kind: str) -> list[str]:
    return [a.text for a in _of(span, kind)]


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

    def test_mm_millions_suffix_scales(self) -> None:
        # "MM" is the standard legal/finance notation for millions: "$5MM" is
        # $5,000,000, not $5. It must scale and keep the suffix in the span text,
        # so a contract check never compares a truncated $5 against the real value.
        self.assertEqual("$5MM", _first("$5MM", "money").text)
        self.assertEqual(500_000_000, _first("$5MM", "money").canonical_value)
        self.assertEqual(500_000_000, _first("a $5MM fee", "money").canonical_value)
        self.assertEqual(250_000_000, _first("$2.5MM", "money").canonical_value)


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


class PartyAnchorTests(unittest.TestCase):
    def test_parenthetical_alias(self) -> None:
        self.assertEqual(_texts('(the "Buyer") shall pay.', "party"), ['(the "Buyer")'])
        self.assertEqual(_texts('Named ("Seller") here.', "party"), ['("Seller")'])
        self.assertEqual(
            _texts('(the "Initial Purchaser") agrees.', "party"), ['(the "Initial Purchaser")']
        )

    def test_entity_suffix(self) -> None:
        cases = {
            "Paid by Acme Inc. today.": "Acme Inc.",
            "Globex LLC operates.": "Globex LLC",
            "Wayne Enterprises, Inc. filed.": "Wayne Enterprises, Inc.",
            "Run by Acme Corp. here.": "Acme Corp.",
            "Held by Acme Ltd. abroad.": "Acme Ltd.",
            "Funded by Acme Capital L.P. now.": "Acme Capital L.P.",
            "Listed as Acme PLC today.": "Acme PLC",
            "Made by Acme GmbH overseas.": "Acme GmbH",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(_texts(text, "party"), [expected])

    def test_suffix_boundary_and_spelled_out_forms_do_not_false_positive(self) -> None:
        # The trailing boundary stops a suffix from matching a longer word, and the
        # ambiguous spelled-out forms are dropped, so all of these yield no party.
        # "Acme Corporation"/"Smith Incorporated" are a documented recall gap.
        for text in [
            "Acme Corporate offices opened.",
            "Acme LLCs were formed.",
            "The Limited Partners met.",
            "Important Limited Warranty applies.",
            "Plaintiff Corporation Counsel spoke.",
            "Smith Incorporated agreed.",
            "Acme Corporation agreed.",
            "Acme Corp.oration argued.",
            "Acme Inc.idental issue.",
            "Acme L.P.s invested.",
            "The Acme Inc-owned warehouse closed.",
            "Important PLC-level guidance arrived.",
            "Acme LP-style funds are rare.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(_of(text, "party"), [])

    def test_within_name_connectors(self) -> None:
        self.assertEqual(
            _texts("Bank of America Corp. lent it.", "party"), ["Bank of America Corp."]
        )
        self.assertEqual(
            _texts("Johnson & Johnson Inc. makes it.", "party"), ["Johnson & Johnson Inc."]
        )

    def test_and_does_not_merge_distinct_parties(self) -> None:
        self.assertEqual(
            _texts("Acme Inc. and Globex LLC are parties.", "party"),
            ["Acme Inc.", "Globex LLC"],
        )

    def test_generic_company_word_and_prose_are_not_parties(self) -> None:
        # "Company"/"Co" are excluded as too generic, even with a name prefix;
        # plain prose has no party.
        for text in [
            "The Company shall pay.",
            "Acme Company filed.",
            "Acme Co. filed.",
            "The parties met on Tuesday.",
            "An ordinary sentence.",
        ]:
            with self.subTest(text=text):
                self.assertEqual(_of(text, "party"), [])

    def test_inherent_capitalized_word_limits_are_pinned(self) -> None:
        # Pinned (not hidden) inherent T0-NER limits; real NER is T1/off (per the
        # design doc). Each still points at a real entity span and routes to the
        # verifier (never a false verdict); the precision point is a human gate.
        # (1) a capitalized prose word directly before a suffix is swept in:
        self.assertEqual(
            _texts("Defendant Stark Industries LLC denies.", "party"),
            ["Defendant Stark Industries LLC"],
        )
        # (2) an all-caps heading whose suffix is itself all-caps (LLC/LP/PLC):
        self.assertEqual(_texts("THE BOARD LLC MET TODAY.", "party"), ["THE BOARD LLC"])

    def test_offsets_and_no_canonical_value(self) -> None:
        text = 'Acme Inc. (the "Buyer") and Globex LLC agree.'
        parties = _of(text, "party")
        # exact list + document order, not just "non-empty"
        self.assertEqual([a.text for a in parties], ["Acme Inc.", '(the "Buyer")', "Globex LLC"])
        for a in parties:
            with self.subTest(anchor=a.text):
                self.assertEqual(text[a.start : a.end], a.text)
                self.assertIsNone(a.canonical_value)


class DefinedTermTests(unittest.TestCase):
    DOC = (
        'Acme Inc. (the "Buyer") shall pay. "Confidential Information" means '
        "non-public data. The Buyer must protect Confidential Information."
    )

    def test_build_alias_table_from_both_forms(self) -> None:
        # parenthetical (the "Buyer") + definition '"Confidential Information" means'
        self.assertEqual(
            build_alias_table(self.DOC),
            {"Buyer": "Buyer", "Confidential Information": "Confidential Information"},
        )

    def test_defined_term_anchors_with_canonical_value(self) -> None:
        table = build_alias_table(self.DOC)
        dt = [a for a in extract_anchors(self.DOC, alias_table=table) if a.type == "defined_term"]
        # both terms, each at its definition site and its later reference, in document order
        self.assertEqual(
            [a.text for a in dt],
            ["Buyer", "Confidential Information", "Buyer", "Confidential Information"],
        )
        for a in dt:
            with self.subTest(anchor=a.text):
                self.assertEqual(self.DOC[a.start : a.end], a.text)
                self.assertEqual(a.canonical_value, a.text)

    def test_default_equals_alias_output_minus_defined_term(self) -> None:
        # Load-bearing: the default run equals the alias run with its defined_term
        # anchors removed (so the other detectors are unchanged AND present), and
        # the alias run genuinely adds defined_term anchors.
        table = build_alias_table(self.DOC)
        default = extract_anchors(self.DOC)
        with_aliases = extract_anchors(self.DOC, alias_table=table)
        self.assertEqual(default, [a for a in with_aliases if a.type != "defined_term"])
        self.assertTrue(any(a.type == "defined_term" for a in with_aliases))

    def test_precision_is_structural_undefined_caps_ignored(self) -> None:
        # only terms the document itself defined enter the table, so an undefined
        # capitalized word is never a defined_term.
        doc = "The Court ruled and the Tribunal agreed."
        table = build_alias_table(doc)
        self.assertEqual(table, {})
        self.assertEqual(
            [a for a in extract_anchors(doc, alias_table=table) if a.type == "defined_term"],
            [],
        )

    def test_case_sensitivity_is_isolated(self) -> None:
        # Isolates the case rule: same sentence + definition verb, differing only in
        # the term's leading case - lowercase rejected, Title-case captured.
        self.assertEqual(build_alias_table('The "data" means everything.'), {})
        self.assertEqual(build_alias_table('The "Data" means everything.'), {"Data": "Data"})

    def test_canonical_value_comes_from_the_table_not_the_term(self) -> None:
        # Non-identity table: canonical_value must be the table's value, proving the
        # detector propagates the canonical rather than echoing the matched term.
        dt = [
            (a.text, a.canonical_value)
            for a in extract_anchors("The Buyer agrees.", alias_table={"Buyer": "Acme Inc."})
            if a.type == "defined_term"
        ]
        self.assertEqual(dt, [("Buyer", "Acme Inc.")])

    def test_term_with_regex_metachars_is_matched_literally(self) -> None:
        # re.escape is load-bearing: the term "A.B" matches "A.B" literally, not the
        # regex-dot "AxB". Without escaping this assertion would also capture "AxB".
        hits = [
            a.text
            for a in extract_anchors("See A.B and AxB here.", alias_table={"A.B": "X"})
            if a.type == "defined_term"
        ]
        self.assertEqual(hits, ["A.B"])

    def test_over_captures_rhetorical_definition_by_design(self) -> None:
        # Pinned (not hidden): a rhetorical `"X" means Y` in prose enters the table.
        # The safe direction - an extra review anchor routed to the tray, never a
        # false verdict; whether to tighten is an operator (human-gate) call.
        self.assertEqual(build_alias_table('"Justice" means a lot to her.'), {"Justice": "Justice"})

    def test_alias_table_is_keyword_only_and_inert_when_no_term_occurs(self) -> None:
        # alias_table is keyword-only; a table whose terms never occur in the text
        # adds no anchors, so the result equals the default run.
        text = "Governed by Section 12.3 and Schedule 2 of the deal."
        self.assertEqual(
            extract_anchors(text), extract_anchors(text, alias_table={"Buyer": "Buyer"})
        )


class CitationSectionOverlapTests(unittest.TestCase):
    def test_statute_section_symbol_not_double_counted(self) -> None:
        # "42 U.S.C. § 1983" is one statute citation; a section anchor that sits
        # inside that citation span must NOT also be emitted (the overlap guard).
        # The citation is detected and no section anchor overlaps its span.
        text = "Liability under 42 U.S.C. § 1983 and §1983 again."
        self.assertEqual(_texts(text, "citation"), ["42 U.S.C. § 1983"])
        cite = _of(text, "citation")[0]
        for sec in _of(text, "section"):
            with self.subTest(section=sec.text):
                self.assertFalse(sec.start < cite.end and cite.start < sec.end)

    def test_standalone_word_section_outside_a_citation_survives(self) -> None:
        # A keyword-form section reference with no enclosing citation is not
        # suppressed by the overlap guard.
        self.assertEqual(_texts("Governed by Section 9.2 of the deal.", "section"), ["Section 9.2"])


if __name__ == "__main__":
    unittest.main()
