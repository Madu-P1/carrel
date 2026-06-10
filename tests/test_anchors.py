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

    def test_word_form_money_without_numeral(self) -> None:
        # An AI summary that paraphrases "$1,000,000" as "one million dollars" drops
        # the numeral; the spelled-out form must still anchor to cents so the
        # parametric-contradiction catch can fire instead of an honest could-not-check.
        cases = {
            "the cap is one million dollars": 100_000_000,
            "a fee of a million dollars": 100_000_000,
            "five hundred thousand dollars": 50_000_000,
            "ten thousand dollars": 1_000_000,
            "two billion dollars": 200_000_000_000,
        }
        for text, cents in cases.items():
            with self.subTest(text=text):
                self.assertEqual(cents, _first(text, "money").canonical_value)

    def test_word_form_with_numeral_counts_the_figure_once(self) -> None:
        # "one million dollars ($1,000,000)" is a single figure: the spelled-out form
        # defers to the numeral via a lookahead so the amount is not double-counted.
        self.assertEqual(1, len(_of("one million dollars ($1,000,000)", "money")))

    def test_compound_word_number_is_could_not_check_not_a_wrong_value(self) -> None:
        # "twenty-five million" is outside the bounded grammar. It must yield NO money
        # anchor (an honest could-not-check), never a wrong $5,000,000 from matching
        # "five" inside "twenty-five".
        self.assertEqual([], _of("twenty-five million dollars", "money"))

    def test_space_separated_compound_yields_no_anchor_not_a_wrong_value(self) -> None:
        # The hyphen guard alone does not stop "twenty five million dollars": the
        # detector matched the tail ("five million dollars") and minted $5,000,000
        # out of a twenty-five-million sentence — which both false-verifies against
        # a $5M clause and manufactures a contradiction against the correct $25M
        # clause. A spelled-out amount the bounded grammar cannot represent must
        # yield NO anchor, in every compound shape.
        cases = [
            "twenty five million dollars",
            "one hundred twenty five million dollars",
            "the cap is twenty five million dollars",
            "ninety five thousand dollars",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual([], _of(text, "money"))

    def test_unicode_separator_compounds_yield_no_anchor(self) -> None:
        # The 2026-06-10 adversarial review reopened the compound seal through a
        # character-class side door: U+2011 (Word's non-breaking hyphen, which
        # survives PDF extraction) is neither \w nor ASCII '-', so
        # 'twenty\u2011five million dollars' minted $5,000,000. Every separator
        # shape must refuse, not just ASCII space and hyphen.
        cases = [
            "twenty\u2011five million dollars",  # non-breaking hyphen
            "twenty\u2010five million dollars",  # unicode hyphen
            "twenty\u2013five million dollars",  # en dash
            "twenty.five million dollars",
            "twenty, five million dollars",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual([], _of(text, "money"))

    def test_scale_word_compounds_yield_no_anchor(self) -> None:
        # The rejector's scale-word arm, pinned in isolation: in
        # 'three billion five hundred thousand dollars' the word immediately
        # before the matched tail is 'billion', so only the scale-word list
        # stands between this sentence and a minted $500,000.
        self.assertEqual([], _of("three billion five hundred thousand dollars", "money"))
        self.assertEqual([], _of("two hundred five million dollars", "money"))

    def test_simple_word_forms_survive_the_compound_guard(self) -> None:
        # Sealing the compound boundary must not regress the in-grammar forms,
        # including when ordinary (non-number) words precede them.
        self.assertEqual(
            500_000_000, _first("a payment of five million dollars", "money").canonical_value
        )
        self.assertEqual(
            100_000_000, _first("liability is one million dollars", "money").canonical_value
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


class PercentAnchorTests(unittest.TestCase):
    def test_percent_canonical_basis_points(self) -> None:
        # Canonical value is basis points, exact decimal arithmetic. Digit forms
        # only, with the unit marker in-span.
        cases = {
            "5%": 500,
            "12.5%": 1250,
            "100%": 10_000,
            "0.01%": 1,
            "12.5 percent": 1250,
            "12 per cent": 1200,
            "50 bps": 50,
            "50 basis points": 50,
            "1 basis point": 1,
        }
        for text, bps in cases.items():
            with self.subTest(text=text):
                anchor = _first(f"interest accrues at {text} per annum", "percent")
                self.assertEqual(bps, anchor.canonical_value)

    def test_word_digit_convention_counts_the_figure_once(self) -> None:
        # "fifty percent (50%)": word-form percent is out of scope (the same
        # bounded-grammar lesson as the money compounds), so only the
        # parenthetical digit anchors — exactly one anchor, the right value.
        anchors = _of("fifty percent (50%) of fees", "percent")
        self.assertEqual(1, len(anchors))
        self.assertEqual(5000, anchors[0].canonical_value)

    def test_word_form_percent_yields_no_anchor(self) -> None:
        # Spelled-out percent carries no digit; refusing beats guessing. A
        # pinned recall gap, the corpus-tested word-form question (ADR-0012).
        self.assertEqual([], _of("five percent of revenue", "percent"))

    def test_range_form_yields_no_anchor_not_a_guessed_end(self) -> None:
        # "5-10%": anchoring either end would manufacture a verdict against a
        # clause stating the other. The whole range form refuses.
        self.assertEqual([], _of("between 5-10% per annum", "percent"))
        self.assertEqual([], _of("a 5\u201310% band", "percent"))

    def test_percentage_points_are_not_percent(self) -> None:
        # Percentage points are an additive quantity, not a rate; conflating
        # them would compare unlike values. Deferred, pinned.
        self.assertEqual([], _of("rose by 5 percentage points", "percent"))

    def test_bare_number_without_unit_is_not_percent(self) -> None:
        self.assertEqual([], _of("Section 50 applies to the parties", "percent"))

    def test_decimal_does_not_double_anchor(self) -> None:
        # "1.5%" is one anchor; the "5%" tail must not also match.
        self.assertEqual(1, len(_of("a 1.5% royalty", "percent")))

    def test_decimal_comma_refuses_not_a_tenfold_value(self) -> None:
        # European/typo decimal commas: '12,5%' read as a thousands grouping
        # canonicalized to 1250 percent — a tenfold-wrong value that both
        # false-accuses a correct draft and false-verifies a wrong one. Commas
        # are accepted only in valid 3-digit groupings; anything else refuses.
        self.assertEqual([], _of("a royalty of 12,5% of revenue", "percent"))
        self.assertEqual([], _of("a late charge of 0,5% per month", "percent"))
        self.assertEqual(1250, _first("a charge of 1,250 bps", "percent").canonical_value)

    def test_worded_ranges_yield_no_anchor(self) -> None:
        # 'between 5 and 10%' left the low end unit-less, so only the top end
        # anchored: a single point value minted from a range manufactures a
        # verdict against a clause stating any other point of it. Every range
        # spelling refuses; only the both-ends-marked form ('from 5% to 10%')
        # anchors, as TWO values the multi-value refusal handles honestly.
        cases = [
            "a fee of 5 to 10% of revenue",
            "between 5 and 10% of revenue",
            "ranging from 5 to 10% of revenue",
            "a 5 \u2013 10% band",
            "a 5\u201210% band",  # figure dash
            "adjusted by \u22125% overall",  # minus sign
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual([], _of(text, "percent"))
        self.assertEqual(2, len(_of("from 5% to 10% of fees", "percent")))

    def test_nested_decimal_yields_no_anchor(self) -> None:
        # '8.5.3%' (typo/OCR/section-number collision): the dot in the
        # lookbehind is what refuses the '5.3%' tail. Pinned in isolation —
        # match consumption alone covers only the well-formed '1.5%' case.
        self.assertEqual([], _of("8.5.3% of fees", "percent"))
        self.assertEqual([], _of("clause 12.5.3% rate", "percent"))

    def test_offsets_are_exact(self) -> None:
        text = "a fee of 12.5% of net revenue"
        anchor = _first(text, "percent")
        self.assertEqual(anchor.text, text[anchor.start : anchor.end])


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

    def test_section_sign_glyph_is_an_anchor(self) -> None:
        # A bare "§ 1983" / "§ 7.2" must be caught; the leading word boundary
        # used to swallow the section-sign form entirely.
        self.assertEqual(_texts("the claim arises under § 1983", "section"), ["§ 1983"])
        self.assertEqual(_texts("governed by § 7.2 of the Agreement", "section"), ["§ 7.2"])

    def test_section_sign_without_space_and_subparts(self) -> None:
        self.assertEqual(_texts("pursuant to §12(b) of the Act", "section"), ["§12(b)"])

    def test_plural_section_sign_is_an_anchor(self) -> None:
        self.assertIn("§§ 5", _texts("see §§ 5 and 6", "section"))

    def test_section_sign_inside_a_citation_is_not_double_counted(self) -> None:
        # "42 U.S.C. § 1983" is one law citation; its "§ 1983" is the citation's
        # own section symbol, so the overlap guard drops it as a section anchor.
        text = "See 42 U.S.C. § 1983 for the standard."
        self.assertEqual(_texts(text, "section"), [])
        self.assertIn("citation", _types(text))

    def test_section_keyword_does_not_match_inside_a_word(self) -> None:
        self.assertNotIn("section", _types("in subsection 5 of the policy"))


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


class GoverningLawAnchorTests(unittest.TestCase):
    def test_boilerplate_governed_by_laws_of_state(self) -> None:
        # The canonical contract form: trigger verb, connective run, "laws of
        # the State of X". canonical_value is the normalized jurisdiction key.
        a = _first(
            "This Agreement shall be governed by and construed in accordance "
            "with the laws of the State of Delaware.",
            "governing_law",
        )
        self.assertEqual("delaware", a.canonical_value)
        self.assertEqual("Delaware", a.text)

    def test_summary_form_governed_by_jurisdiction_law(self) -> None:
        # The AI-summary phrasing: "governed by New York law".
        a = _first("The agreement is governed by New York law.", "governing_law")
        self.assertEqual("new york", a.canonical_value)

    def test_jurisdiction_law_governs(self) -> None:
        a = _first("Delaware law governs this Agreement.", "governing_law")
        self.assertEqual("delaware", a.canonical_value)

    def test_canonical_is_stable_across_forms(self) -> None:
        long_form = _first(
            "governed by and construed in accordance with the laws of the State of New York",
            "governing_law",
        )
        short_form = _first("governed by New York law", "governing_law")
        self.assertEqual(long_form.canonical_value, short_form.canonical_value)

    def test_adjectival_english_law_means_england_and_wales(self) -> None:
        # "English law" conventionally designates the law of England and Wales.
        # Both surface forms must share one canonical so the contradiction check
        # can never accuse a summary across this naming variant.
        adjectival = _first("The deed is governed by English law.", "governing_law")
        full = _first(
            "This deed shall be governed by the laws of England and Wales.",
            "governing_law",
        )
        self.assertEqual(adjectival.canonical_value, full.canonical_value)
        self.assertEqual("england and wales", full.canonical_value)

    def test_lebanese_law_form(self) -> None:
        a = _first("The contract is governed by Lebanese law.", "governing_law")
        self.assertEqual("lebanon", a.canonical_value)

    def test_venue_clause_is_not_a_governing_law_anchor(self) -> None:
        # Forum selection is not choice of law. Anchoring the venue jurisdiction
        # would let a court reference mask or manufacture a governing-law verdict.
        self.assertNotIn(
            "governing_law",
            _types("The parties consent to the exclusive jurisdiction of the courts of Delaware."),
        )

    def test_incorporation_state_is_not_a_governing_law_anchor(self) -> None:
        self.assertNotIn("governing_law", _types("Acme Holdings is a Delaware corporation."))

    def test_liable_under_is_not_a_governing_law_trigger(self) -> None:
        # "liable under New York law" is a liability proposition, not a choice of
        # law; only governing verbs trigger, so this yields no governing_law anchor.
        self.assertNotIn(
            "governing_law", _types("The Seller may be held liable under New York law.")
        )

    def test_unknown_jurisdiction_yields_no_anchor(self) -> None:
        # Outside the closed lexicon the detector refuses: no anchor, never a
        # guessed canonical. The sentence routes to the honest could-not-check side.
        self.assertNotIn("governing_law", _types("governed by the laws of Atlantis"))

    def test_all_caps_conspicuous_clause_anchors(self) -> None:
        # The conspicuous-formatting convention: an all-caps governing-law
        # clause must still anchor (the gap accepts an all-caps connective run).
        a = _first(
            "THIS AGREEMENT SHALL BE GOVERNED BY AND CONSTRUED IN ACCORDANCE "
            "WITH THE LAWS OF THE STATE OF NEW YORK.",
            "governing_law",
        )
        self.assertEqual("new york", a.canonical_value)

    def test_intervening_object_refuses_the_anchor(self) -> None:
        # "governed by" whose object is something else entirely, with a
        # compliance phrase trailing in the same sentence: the mixed-case
        # intervening noun breaks the boilerplate gap, so no governing-law value
        # is minted from the compliance phrase.
        for span in (
            "The fees are governed by Section 4, and payments shall comply "
            "with the laws of New York.",
            "The Plan is governed by ERISA and not by the laws of Texas.",
        ):
            with self.subTest(span=span):
                self.assertNotIn("governing_law", _types(span))

    def test_longest_jurisdiction_name_wins(self) -> None:
        a = _first("governed by the laws of West Virginia", "governing_law")
        self.assertEqual("west virginia", a.canonical_value)

    def test_new_jersey_does_not_collapse_to_jersey(self) -> None:
        # "New Jersey" (US state) and "Jersey" (Channel Island) are distinct
        # jurisdictions; longest-first alternation keeps them apart.
        a = _first("governed by the laws of the State of New Jersey", "governing_law")
        self.assertEqual("new jersey", a.canonical_value)

    def test_offsets_are_exact(self) -> None:
        text = "The agreement is governed by New York law."
        a = _first(text, "governing_law")
        self.assertEqual("New York", text[a.start : a.end])

    def test_modified_adjective_refuses_not_the_wrong_jurisdiction(self) -> None:
        # "North Korean law" is not South Korea's and "Federal Indian law" is a
        # body of US law, not India's. The modifier guard refuses the anchor
        # rather than mint the tail adjective's canonical (the adversarial
        # review's blocker pair).
        for span in (
            "North Korean law governs the joint venture.",
            "Federal Indian law governs all claims arising on tribal land.",
            "The treaty is governed by West German law.",
        ):
            with self.subTest(span=span):
                self.assertNotIn("governing_law", _types(span))

    def test_south_korean_law_survives_the_modifier_guard(self) -> None:
        # The multi-word lexicon form matches longest-first as its own surface,
        # so the guard never sees "South" as a stray modifier.
        a = _first("South Korean law governs the joint venture.", "governing_law")
        self.assertEqual("south korea", a.canonical_value)


class PolarityAnchorTests(unittest.TestCase):
    def test_exclusive_license_is_affirmative(self) -> None:
        # The canonical carries stem AND noun class: "exclusive license" and
        # "exclusive remedy" must never compare against each other.
        a = _first("Licensor grants Licensee an exclusive license.", "polarity")
        self.assertEqual("exclusive:license+", a.canonical_value)
        self.assertEqual("exclusive", a.text)

    def test_non_exclusive_license_is_negated(self) -> None:
        # Hyphenated and solid spellings carry the same canonical.
        for span in (
            "Licensor grants a non-exclusive license.",
            "Licensor grants a nonexclusive license.",
        ):
            with self.subTest(span=span):
                a = _first(span, "polarity")
                self.assertEqual("exclusive:license-", a.canonical_value)

    def test_irrevocable_is_the_negated_revocable(self) -> None:
        # The ir- pair shares a stem with revocable so a flip can contradict.
        neg = _first("an irrevocable license to use the Software", "polarity")
        aff = _first("a revocable license to use the Software", "polarity")
        self.assertEqual("revocable:license-", neg.canonical_value)
        self.assertEqual("revocable:license+", aff.canonical_value)

    def test_each_adjective_in_a_run_anchors_individually(self) -> None:
        anchors = _of(
            "Licensor grants an exclusive, non-transferable, irrevocable license.",
            "polarity",
        )
        self.assertEqual(
            ["exclusive:license+", "transferable:license-", "revocable:license-"],
            [a.canonical_value for a in anchors],
        )

    def test_binding_arbitration_pair(self) -> None:
        # Different noun classes on purpose: binding arbitration and
        # non-binding mediation are different procedures, not a flip.
        aff = _first("Disputes are resolved by binding arbitration.", "polarity")
        neg = _first("The parties will first attempt non-binding mediation.", "polarity")
        self.assertEqual("binding:arbitration+", aff.canonical_value)
        self.assertEqual("binding:mediation-", neg.canonical_value)

    def test_plural_noun_folds_to_the_singular_class(self) -> None:
        a = _first("Licensee receives exclusive rights to the Work.", "polarity")
        self.assertEqual("exclusive:right+", a.canonical_value)

    def test_scope_negators_refuse_the_anchor(self) -> None:
        # Clause-scope negation reverses the qualifier's meaning; the bounded
        # grammar cannot represent it, so no sign is ever minted (the
        # adversarial review's negation-hole pair).
        for span in (
            "Nothing herein creates a binding obligation.",
            "Licensor may act without granting an exclusive license to any party.",
            "In no event shall this constitute a binding commitment.",
            "Neither party receives an exclusive license under this Section.",
        ):
            with self.subTest(span=span):
                self.assertNotIn("polarity", _types(span))

    def test_negator_in_a_prior_sentence_does_not_refuse(self) -> None:
        # The scope guard is segment-bounded: a negation BEFORE the sentence
        # boundary cannot suppress a clean grant after it.
        a = _first(
            "The prior draft was not executed. Licensor grants an exclusive license.",
            "polarity",
        )
        self.assertEqual("exclusive:license+", a.canonical_value)

    def test_exclusive_jurisdiction_is_not_a_polarity_anchor(self) -> None:
        # Forum language: "exclusive" there is venue, not a grant qualifier.
        self.assertNotIn(
            "polarity",
            _types("The parties consent to the exclusive jurisdiction of the courts."),
        )

    def test_broken_adjective_run_refuses(self) -> None:
        # "exclusive" modifies "distributor", not the later "license"; the
        # closed-vocabulary run is broken, so no anchor is minted.
        self.assertNotIn(
            "polarity",
            _types("The exclusive distributor shall hold a license to the marks."),
        )

    def test_negated_forms_refuse_not_flip(self) -> None:
        # "not exclusive" is outside the bounded grammar: refusing is honest;
        # minting either sign would be a guess.
        for span in (
            "The license is not an exclusive license.",
            "There is no binding obligation under this term sheet.",
            "This letter shall not be a binding agreement.",
        ):
            with self.subTest(span=span):
                self.assertNotIn("polarity", _types(span))

    def test_predicative_position_anchors(self) -> None:
        # The common summary phrasing puts the qualifier after the copula.
        cases = {
            "The license granted hereunder is non-exclusive.": "exclusive:license-",
            "This Agreement is binding.": "binding:agreement+",
            "The deposit is refundable.": "refundable:deposit+",
        }
        for span, canonical in cases.items():
            with self.subTest(span=span):
                self.assertEqual(canonical, _first(span, "polarity").canonical_value)

    def test_predicative_negation_refuses_structurally(self) -> None:
        # The copula-adjacency requirement means a negator breaks the match;
        # no sign is guessed for "is not exclusive" or "no longer binding".
        for span in (
            "The license is not exclusive.",
            "This Agreement shall not be binding.",
            "The offer is no longer binding.",
        ):
            with self.subTest(span=span):
                self.assertNotIn("polarity", _types(span))

    def test_bare_adjective_without_a_grant_noun_refuses(self) -> None:
        # "arrangement" is not a grant noun: neither the attributive nor the
        # predicative grammar reaches the qualifier.
        self.assertNotIn("polarity", _types("The arrangement is binding."))

    def test_offsets_cover_the_full_surface(self) -> None:
        text = "Licensor grants a non-exclusive license."
        a = _first(text, "polarity")
        self.assertEqual("non-exclusive", text[a.start : a.end])


if __name__ == "__main__":
    unittest.main()
