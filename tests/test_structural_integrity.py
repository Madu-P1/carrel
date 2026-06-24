"""Held-out tests for SI-1 (dangling intra-document cross-references).

These cases are the ship authority for SI-1 per
docs/plans/2026-06-24-structural-integrity-pillar.md. The engine is pure: no DB,
no network, no model. The asymmetric safety bar is the point: the loud ``flagged``
state must fire on a genuine dangle and must NOT fire on a resolving reference, an
external attachment, or a fragment.
"""

import os
import textwrap
import unittest
from unittest import mock

from services.legal.deterministic_envelope import build_deterministic_envelope
from services.legal.local_caselaw import local_caselaw_client
from services.legal.structural_integrity import (
    StructuralFinding,
    check_cross_references,
    check_defined_terms,
    check_internal_contradictions,
    check_structural_integrity,
)


def _flagged(findings: list[StructuralFinding]) -> list[StructuralFinding]:
    return [f for f in findings if f.disposition == "flagged"]


class DanglingCrossReferenceTests(unittest.TestCase):
    def test_dangling_section_is_could_not_check(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The indemnification obligations set forth in Section 12 shall survive termination.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        cnc = [f for f in findings if f.disposition == "could_not_check"]
        self.assertEqual(1, len(cnc))
        self.assertEqual("dangling_cross_reference", cnc[0].kind)
        self.assertEqual("12", cnc[0].target)
        self.assertIn("Section 12", cnc[0].span)

    def test_resolved_reference_is_silent(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            Section 4. Indemnification
            The parties shall comply with the obligations pursuant to Section 4 of this Agreement.
            """
        )
        # Every section reference resolves to a declaration, so nothing surfaces.
        self.assertEqual([], check_cross_references(draft))

    def test_attachment_reference_is_could_not_check_never_flagged(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The deliverables are described in Exhibit 7 attached to this Agreement.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        attachment = [f for f in findings if f.target == "7"]
        self.assertEqual(1, len(attachment))
        self.assertEqual("could_not_check", attachment[0].disposition)

    def test_fragment_never_flags(self) -> None:
        draft = textwrap.dedent(
            """\
            This is a short excerpt pasted from a longer agreement.
            Please see Section 8 for the full indemnification language.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        # The reference is still surfaced honestly, just as could-not-check.
        self.assertTrue(any(f.disposition == "could_not_check" for f in findings))

    def test_range_form_does_not_false_flag_interior_numbers(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The obligations in Sections 4 through 9 are incorporated by reference.
            """
        )
        # The plural range form yields no single-section anchors, so no false flag
        # on the interior numbers 4..9.
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_empty_text_is_no_findings(self) -> None:
        self.assertEqual([], check_structural_integrity(""))
        self.assertEqual([], check_structural_integrity("   \n  "))

    def test_aggregator_matches_cross_reference_check(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            See Section 99 for the survival clause.
            """
        )
        self.assertEqual(
            check_cross_references(draft),
            check_structural_integrity(draft),
        )


class AdversarialHardeningTests(unittest.TestCase):
    """Cracks found by the cachet-adversary pass (2026-06-24). Each must stay closed.

    All four are FALSE-FLAG cracks (cry wolf on a reference that actually resolves),
    the costly error class for SI-1.
    """

    def test_subsection_reference_resolves_against_parent(self) -> None:
        # A1: real contracts reference "Section 4.2" where 4.2 is a subsection of a
        # declared Section 4 that has no standalone 4.2 heading. Must not flag.
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 4. Payment
            The parties shall pay under Section 4.2 within thirty days.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_deep_subsection_resolves_against_ancestor(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 4. Payment
            Late charges accrue as described in Section 4.2.1 of this Agreement.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_subsection_with_no_ancestor_is_could_not_check(self) -> None:
        # The ancestor-resolution fix must not over-suppress: a subsection whose
        # parent is also absent is surfaced (as could-not-check) for review.
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The remedy is set forth in Section 8.3 of this Agreement.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        cnc = [f for f in findings if f.disposition == "could_not_check"]
        self.assertEqual(1, len(cnc))
        self.assertEqual("8.3", cnc[0].target)

    def test_markdown_heading_declaration_is_detected(self) -> None:
        # E3: a heading written with leading markup ("## Section 1") still counts
        # as a declaration, so a later reference to it does not false-flag.
        draft = textwrap.dedent(
            """\
            ## Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The definitions in Section 1 control this Agreement.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_roman_numeral_heading_resolves_arabic_reference(self) -> None:
        # B: "ARTICLE I" declared, referenced as "Article 1". Normalized, not flagged.
        draft = textwrap.dedent(
            """\
            ARTICLE I. Definitions
            Section 5. Payment
            Section 6. Term
            The obligations in Article 1 are incorporated by reference.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_reference_inside_quote_is_could_not_check(self) -> None:
        # C: a section reference inside a quoted external passage may point at the
        # quoted document, so it is could-not-check, never a flag.
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The tribunal quoted "the indemnity set forth in Section 88 of the Prior Agreement" today.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        quoted = [f for f in findings if f.target == "88"]
        self.assertEqual(1, len(quoted))
        self.assertEqual("could_not_check", quoted[0].disposition)

    def test_plural_section_list_is_recall_gap_not_false_flag(self) -> None:
        # D (documented limitation): plural "Sections 7 and 9" is not parsed, so the
        # dangle is missed. The contract is that it is a SILENT recall gap, never a
        # false flag. If plural parsing is added later, update this expectation.
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The provisions of Sections 7 and 9 are incorporated by reference.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))


class DefinedTermTests(unittest.TestCase):
    """SI-2: defined-but-never-used, hardened against cry-wolf on a used term."""

    def test_unused_defined_term_is_flagged(self) -> None:
        text = (
            '"Indemnified Party" means the protected party. '
            "This Agreement is governed by New York law."
        )
        findings = check_defined_terms(text)
        self.assertEqual(1, len(findings))
        self.assertEqual("defined_term_unused", findings[0].kind)
        self.assertEqual("flagged", findings[0].disposition)
        self.assertEqual("Indemnified Party", findings[0].target)

    def test_used_defined_term_is_silent(self) -> None:
        text = (
            '"Confidential Information" means trade secrets. '
            "Each party shall protect Confidential Information."
        )
        self.assertEqual([], check_defined_terms(text))

    def test_plural_use_is_not_flagged(self) -> None:
        text = 'Globex LLC (the "Seller") is engaged. The Sellers shall deliver the goods.'
        self.assertEqual([], check_defined_terms(text))

    def test_lowercase_use_is_not_flagged(self) -> None:
        text = 'Acme Inc. (the "Buyer") signs this. the buyer pays on time.'
        self.assertEqual([], check_defined_terms(text))

    def test_possessive_use_is_not_flagged(self) -> None:
        text = 'Acme Inc. (the "Buyer") signs this. The Buyer\'s obligations survive.'
        self.assertEqual([], check_defined_terms(text))


class InternalContradictionTests(unittest.TestCase):
    """SI-3: percent-only, ADR-0013-constrained. Never flags (could-not-check only)."""

    def test_si3_never_flags_safety_invariant(self) -> None:
        # The load-bearing guard: SI-3 may never emit a loud 'flagged'. Includes the
        # adversary's S5 crack (different facts near the same proper noun).
        inputs = [
            "The allocation gives 10% France in Schedule A. The summary states 20% France.",
            "There is a 10% France tax and separately a 20% France tariff.",
            "The split is 10% France and 20% Germany across markets.",
            "We allocate 10% to France here, and 20% to France there.",
            "The fee is $10 million France in one place and $20 million France elsewhere.",
        ]
        for text in inputs:
            for f in check_internal_contradictions(text):
                self.assertEqual("could_not_check", f.disposition, text)

    def test_same_subject_different_value_is_could_not_check(self) -> None:
        text = "The allocation gives 10% France in Schedule A. The summary states 20% France."
        findings = check_internal_contradictions(text)
        self.assertEqual(1, len(findings))
        self.assertEqual("internal_contradiction", findings[0].kind)
        self.assertEqual("could_not_check", findings[0].disposition)
        self.assertEqual("france", findings[0].target)

    def test_different_subjects_are_silent(self) -> None:
        self.assertEqual(
            [], check_internal_contradictions("The split is 10% France and 20% Germany.")
        )

    def test_same_subject_same_value_is_silent(self) -> None:
        self.assertEqual(
            [],
            check_internal_contradictions(
                "Allocation: 10% France in the table; the recital repeats 10% France."
            ),
        )

    def test_money_is_never_compared_adr_0013(self) -> None:
        # Money carries no subject by design; SI-3 must never compare figures.
        self.assertEqual(
            [],
            check_internal_contradictions(
                "The fee is $10 million France here and $20 million France there."
            ),
        )

    def test_unbound_percent_is_silent(self) -> None:
        # "10% to France" breaks the proper-noun adjacency, so no subject binds.
        self.assertEqual(
            [],
            check_internal_contradictions(
                "We allocate 10% to France here, and 20% to France there."
            ),
        )


class EnvelopeWiringTests(unittest.TestCase):
    """SI-4: source-free aggregator + additive structural_findings envelope key."""

    def _build(self, draft: str) -> dict:
        with mock.patch.dict(os.environ, {"COURTLISTENER_API_TOKEN": "local"}, clear=False):
            return build_deterministic_envelope(draft, client=local_caselaw_client())

    def test_aggregator_includes_si1_and_si2(self) -> None:
        text = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            "Indemnified Party" means the protected party.
            The remedy is set forth in Section 88 of this Agreement.
            """
        )
        kinds = {f.kind for f in check_structural_integrity(text)}
        self.assertIn("dangling_cross_reference", kinds)
        self.assertIn("defined_term_unused", kinds)

    def test_envelope_carries_additive_structural_findings(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            The remedy is set forth in Section 77 of this Agreement.
            """
        )
        env = self._build(draft)
        # Additive: existing keys unchanged in shape, new key present.
        self.assertIsInstance(env["claims"], list)
        self.assertEqual("deterministic", env["provider"])
        self.assertIn("structural_findings", env)
        cnc = [f for f in env["structural_findings"] if f["disposition"] == "could_not_check"]
        self.assertTrue(any(f["target"] == "77" for f in cnc))

    def test_envelope_clean_draft_has_empty_structural_findings(self) -> None:
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Under Section 1 the parties agree to the terms of Section 2.
            """
        )
        self.assertEqual([], self._build(draft)["structural_findings"])

    def test_envelope_carries_si3_internal_contradiction(self) -> None:
        # SI-3 must also survive asdict -> envelope -> wire, as could_not_check.
        draft = "The allocation gives 10% France in Schedule A. The summary states 20% France."
        env = self._build(draft)
        si3 = [f for f in env["structural_findings"] if f["kind"] == "internal_contradiction"]
        self.assertEqual(1, len(si3))
        self.assertEqual("could_not_check", si3[0]["disposition"])
        self.assertEqual("france", si3[0]["target"])


class ReviewHardeningTests(unittest.TestCase):
    """Closes the cry-wolf class found by the 2026-06-24 three-reviewer pass
    (mythos + /review Claude&Codex + /code-review). Every case below is a
    FALSE-FLAG the engine must NOT make, or a regression guard that the genuine
    catch survives.
    """

    def test_inline_declared_section_not_flagged(self) -> None:  # F1
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            This Amendment hereby adds Section 10 (Force Majeure) as follows.
            The obligations under Section 10 shall apply to both parties.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_statute_symbol_is_could_not_check(self) -> None:  # F2 (litigator wedge)
        draft = textwrap.dedent(
            """\
            Section 1. Claims
            Section 2. Relief
            Plaintiff sues under 42 U.S.C. § 1983 and also cites § 1988 for fees.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_external_agreement_reference_is_could_not_check(self) -> None:  # Codex-1
        draft = textwrap.dedent(
            """\
            Section 1. Term
            Section 2. Payment
            The parties acknowledge that Section 5 of the Credit Agreement governs the collateral.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        self.assertTrue(
            any(f.target == "5" and f.disposition == "could_not_check" for f in findings)
        )

    def test_parenthetical_subsection_heading_resolves(self) -> None:  # Codex-3
        draft = textwrap.dedent(
            """\
            1. Definitions
            2. Payment
            3. Termination
            4(a) Indemnity
            The indemnity in Section 4(a) survives termination.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_parent_reference_resolves_against_declared_subsection(self) -> None:  # NEW-1
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 4.2 Indemnification
            Section 4.3 Term
            Obligations under Section 4 are binding on the parties.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_lowercase_bare_number_heading_resolves(self) -> None:  # NEW-6b
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            4.2 indemnification obligations of the parties
            The remedy is set forth in Section 4.2 of this Agreement.
            """
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_irregular_plural_defined_term_not_flagged(self) -> None:  # F3
        self.assertEqual(
            [], check_defined_terms('Each entity (the "Party") signs. The Parties agree.')
        )
        self.assertEqual(
            [], check_defined_terms('Each (the "Company") joins. The Companies file jointly.')
        )

    def test_plural_defined_term_used_singular_not_flagged(self) -> None:  # NEW-10
        self.assertEqual(
            [], check_defined_terms('"Holders" means owners. Each Holder votes on the matter.')
        )

    def test_schedule_attachment_is_could_not_check(self) -> None:  # test-2 gap
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            The deliverables are described in Schedule 7 to this Agreement.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        sched = [f for f in findings if f.target == "7"]
        self.assertEqual(1, len(sched))
        self.assertEqual("could_not_check", sched[0].disposition)

    def test_genuine_dangle_is_could_not_check(self) -> None:  # the review surface
        draft = textwrap.dedent(
            """\
            Section 1. Definitions
            Section 2. Term
            Section 3. Payment
            Indemnification obligations under Section 12.3 survive termination.
            """
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        cnc = [f for f in findings if f.disposition == "could_not_check"]
        self.assertEqual(1, len(cnc))
        self.assertEqual("12.3", cnc[0].target)

    def test_defined_terms_scales_to_many_terms(self) -> None:  # sec-1 (correctness under load)
        import string

        def _u(i: int) -> str:
            return string.ascii_uppercase[i // 26] + string.ascii_lowercase[i % 26]

        terms = [f"Alpha Beta{_u(i)}" for i in range(400)]
        text = " ".join(f"{t} means a thing." for t in terms)
        findings = check_defined_terms(text, alias_table={t: t for t in terms})
        self.assertEqual(400, len(findings))
        self.assertTrue(all(f.disposition == "flagged" for f in findings))

    def test_defined_terms_caps_pathological_input(self) -> None:  # sec-1 DoS bound
        # Term-count cap. Contrast proves the cap fires (not "all used"): a small set
        # of unused terms all flag, but a >_MAX_DEFINED_TERMS set is skipped entirely.
        import string

        def term(i: int) -> str:
            return "Term" + string.ascii_uppercase[i // 26] + string.ascii_lowercase[i % 26]

        small = {term(i): term(i) for i in range(10)}
        small_doc = " ".join(f'"{t}" means a thing.' for t in small)
        self.assertEqual(10, len(check_defined_terms(small_doc, alias_table=small)))
        big = {term(i): term(i) for i in range(600)}
        big_doc = " ".join(f'"{t}" means a thing.' for t in big)
        self.assertEqual([], check_defined_terms(big_doc, alias_table=big))
        # Text-size cap: an oversized draft is skipped before any per-term scan.
        huge = "lorem ipsum " * 20000
        self.assertGreater(len(huge), 200_000)
        self.assertEqual([], check_defined_terms(huge, alias_table={"Foo Bar": "Foo Bar"}))

    def test_structural_integrity_caps_huge_draft(self) -> None:  # sec-1 (SI-1/SI-3 bound)
        # A draft past the whole-pass cap skips check_structural_integrity entirely,
        # so a huge adversarial paste cannot block the verify path (~16s at 200KB).
        huge = "The license in Section 12 governs France 10%. " * 3000
        self.assertGreater(len(huge), 100_000)
        self.assertEqual([], check_structural_integrity(huge))

    def test_si3_span_covers_all_values(self) -> None:  # F6
        text = "Allocation: 10% France, then 20% France, and later 30% France."
        findings = check_internal_contradictions(text)
        self.assertEqual(1, len(findings))
        f = findings[0]
        self.assertLess(f.start, f.end)
        self.assertIn("10%", f.span)

    def test_normalize_subject_matches_contract_verify(self) -> None:  # maint-1 drift guard
        from services.legal import contract_verify
        from services.legal.structural_integrity import _normalize_subject as si_norm

        for s in ("France", "  France  ", "FRANCE", "Côte d'Ivoire", " Île "):
            self.assertEqual(contract_verify._normalize_subject(s), si_norm(s))

    def test_disposition_constants(self) -> None:  # maint-5
        from services.legal.structural_integrity import COULD_NOT_CHECK, FLAGGED

        self.assertEqual("flagged", FLAGGED)
        self.assertEqual("could_not_check", COULD_NOT_CHECK)


class FanoutHardeningTests(unittest.TestCase):
    """Closes the 14 cry-wolf cracks found by the 2026-06-24 adversary fan-out
    (8 fresh-context angles, 124 cases). Every case must NOT false-flag."""

    def test_external_instrument_references_are_could_not_check(self) -> None:
        cases = [
            "Section 1. Premises\nSection 2. Rent\nThe tenant shall observe Section 7 of the Lease.",
            "Section 1. Loan\nSection 2. Repayment\nInterest accrues per Section 3 of that certain Note dated 2020.",
            "Section 1. Grant\nSection 2. Vesting\nAwards are subject to Section 4 of the 2019 Plan.",
            "Section 1. Scope\nSection 2. Term\nPayments are governed by Section 9 under the Master Agreement.",
            "Section 1. Defs\nSection 2. Covenants\nSee Section 5 of the credit agreement for details.",
            "Section 1. Conveyance\nSection 2. Warranties\nForeclosure is per Section 8 of the Deed of Trust.",
        ]
        for draft in cases:
            self.assertEqual([], _flagged(check_cross_references(draft)), draft)

    def test_internal_self_reference_is_could_not_check(self) -> None:
        # "of this Agreement" is the document itself: the unresolved ref is surfaced.
        draft = (
            "Section 1. Defs\nSection 2. Term\nObligations under Section 99 of this Agreement bind."
        )
        findings = check_cross_references(draft)
        self.assertEqual([], _flagged(findings))
        cnc = [f for f in findings if f.disposition == "could_not_check"]
        self.assertEqual(1, len(cnc))
        self.assertEqual("99", cnc[0].target)

    def test_defined_term_plural_morphology_not_flagged(self) -> None:
        cases = [
            'Any communication (the "Notice") is valid. All Notices shall be in writing.',
            'The work performed (the "Service") is defined. The Services shall be rendered.',
            'A subsidiary (the "Affiliate") is included. The Affiliates are jointly bound.',
            'The reference rate (the "Index") is set. The Indices are published monthly.',
            'Communications (the "Notices") are governed. Each Notice must be delivered.',
        ]
        for text in cases:
            self.assertEqual([], check_defined_terms(text), text)

    def test_reference_inside_single_quote_is_could_not_check(self) -> None:
        straight = "Section 1. Defs\nSection 2. Term\nThe brief argued: 'Section 99 governs the dispute' and the court agreed."
        lq, rq = chr(0x2018), chr(0x2019)
        smart = f"Section 1. Defs\nSection 2. Term\nThe brief argued: {lq}Section 99 governs the dispute{rq} today."
        for draft in (straight, smart):
            findings = check_cross_references(draft)
            self.assertEqual([], _flagged(findings), draft)
            self.assertTrue(any(f.target == "99" for f in findings), draft)

    def test_fullwidth_digit_reference_is_not_flagged(self) -> None:
        # A full-width digit reference must not produce a confident flag. A
        # full-width DECLARATION reconciles with an ASCII reference via NFKC.
        fw5 = chr(0xFF15)
        draft = f"Section 1. Definitions\nSection 2. Term\nUnder Section {fw5} the parties act."
        self.assertEqual([], _flagged(check_cross_references(draft)))
        declared_fw = (
            f"Section 1. Definitions\nSection {fw5}. Indemnity\nUnder Section 5 the parties act."
        )
        self.assertEqual([], _flagged(check_cross_references(declared_fw)))


class Fanout2HardeningTests(unittest.TestCase):
    """Closes the round-2 adversary fan-out cracks (qualified-reference rule +
    unbounded single-quote spans). Documents the Roman-reference recall gap."""

    def test_qualified_external_references_never_flag(self) -> None:
        # Any connective + any instrument: no enumerated list, so these all hold.
        base = "Section 1. A\nSection 2. B\nSection 3. C\n"
        cases = [
            "Each party agrees to Section 99 to the Lease.",
            "Rights from Section 99 from the Indenture survive.",
            "The covenant in Section 99 contained in the Mortgage binds.",
            "Risk factors are in Section 99 of the Prospectus.",
            "Distributions follow Section 99 of the Offering Circular.",
            "See Section 99 of the Subscription Booklet.",
            "Awards are subject to Section 99 of the 2019 Plan.",
            "Payments are governed by Section 99 under the Master Agreement.",
        ]
        for tail in cases:
            self.assertEqual([], _flagged(check_cross_references(base + tail)), tail)

    def test_bare_reference_is_could_not_check(self) -> None:
        # The common real dangle shape is surfaced for review (could-not-check).
        base = "Section 1. A\nSection 2. B\nSection 3. C\n"
        for tail in (
            "The obligations in Section 99 shall survive.",
            "The court held that Section 99 governs the dispute.",
            "As set forth in Section 99, the parties act.",
        ):
            findings = check_cross_references(base + tail)
            self.assertEqual([], _flagged(findings), tail)
            cnc = [f for f in findings if f.disposition == "could_not_check"]
            self.assertEqual(1, len(cnc), tail)
            self.assertEqual("99", cnc[0].target)

    def test_long_single_quoted_reference_not_flagged(self) -> None:
        # The quote span is unbounded, so a ref deep inside a long quote is still
        # recognized as quoted (could-not-check), not flagged.
        filler = "x " * 220
        draft = "Section 1. Scope\nSection 2. Term\n'" + filler + "Section 66 applies'"
        self.assertEqual([], _flagged(check_cross_references(draft)))

    def test_roman_numeral_reference_is_a_documented_recall_gap(self) -> None:
        # Roman-numeral REFERENCES are not section anchors, so a genuine Roman dangle
        # is silently missed (a recall gap, the safe error class - never a false
        # flag). Pin current behavior so a future change to add Roman references is
        # a deliberate, tested decision.
        draft = (
            "Article I. Scope\nArticle II. Payment\nPursuant to Article VII the surcharge applies."
        )
        self.assertEqual([], _flagged(check_cross_references(draft)))


class Fanout3DefinedTermTests(unittest.TestCase):
    """Closes the round-4 SI-2 morphology cracks (stem-subsequence matching,
    singular-s fix, bidirectional irregulars). A USED term must never flag."""

    def test_irregular_plural_defined_singular_used(self) -> None:
        cases = [
            'The attendees (the "People") meet. Each Person must register and each Person pays.',
            'The dependents (the "Children") enroll. Each Child gets a locker and a mentor.',
            'The grounds (the "Bases") are listed. The Basis for review is fixed; the Basis holds.',
            'The reports (the "Analyses") are due. Each Analysis is confidential and each Analysis is signed.',
        ]
        for text in cases:
            self.assertEqual([], check_defined_terms(text), text)

    def test_multiword_plural_and_irregular_not_flagged(self) -> None:
        cases = [
            '"Indemnified Party" means a party owed indemnity. Each Indemnified Parties shall give notice.',
            '"Affiliated Company" means a controlled entity. The Affiliated Companies are bound.',
            '"Market Index" means a benchmark. The Market Indices are tracked daily.',
            '"Parent Company" is defined. The Parent Companies consolidate results.',
        ]
        for text in cases:
            self.assertEqual([], check_defined_terms(text), text)

    def test_multiword_hyphen_and_possessive_not_flagged(self) -> None:
        cases = [
            'The parties acknowledge ("Force Majeure"). A Force-Majeure event excuses performance.',
            'Defined here: ("Buyer Group"). The Buyer\'s Group shall indemnify the seller.',
        ]
        for text in cases:
            self.assertEqual([], check_defined_terms(text), text)

    def test_genuinely_unused_multiword_still_flags(self) -> None:
        # The catch must survive: a multi-word term used nowhere is still flagged.
        text = '"Indemnified Party" means the protected party. This Agreement is governed by New York law.'
        findings = check_defined_terms(text)
        self.assertEqual(1, len(findings))
        self.assertEqual("flagged", findings[0].disposition)
        self.assertEqual("Indemnified Party", findings[0].target)


if __name__ == "__main__":
    unittest.main()
