"""Assembles the full attack battery: mutated contract cases + clean controls +
hand-crafted litigator citation attacks.

The litigator family targets the bounded demo corpus (Brown v. Board of Education,
347 U.S. 483). It is the 2026 sanctions-frontier surface: a REAL citation number
wearing a FABRICATED case name, year, or court. The engine must never affirm
(``supported``) such a misattributed or fabricated cite; an honest refusal
(could-not-verify) or an active flag (contradicted) both HOLD.
"""

from __future__ import annotations

from collections.abc import Iterator

from .contracts import CONTRADICTED, COULD_NOT_VERIFY, SUPPORTED, AttackCase, Mode
from .corpus import QUOTE, SEEDS, Seed
from .mutators import contract_cases

# The one real citation in the bounded demo corpus.
_REAL_CITE = "347 U.S. 483"
_REAL_NAME = "Brown v. Board of Education"

# Fabricated case names paired with the REAL reporter number (caption mismatch).
_FAKE_CAPTIONS = [
    "Plessy v. Ferguson",
    "Smith v. Jones",
    "United States v. Carrel",
    "Lochner v. New York",
    "Roe v. Wade",
    "Marbury v. Madison",
    "Dred Scott v. Sandford",
    "Korematsu v. United States",
]

# Fabricated reporter numbers that resolve to no case in the bounded corpus.
_FAKE_CITES = [
    "999 U.S. 999",
    "555 U.S. 1234",
    "123 U.S. 4567",
    "404 U.S. 404",
    "888 F.3d 8888",
    "111 F.4th 2222",
    "777 U.S. 100",
    "650 U.S. 650",
]


def _lit_case(
    case_id: str, family: str, claim: str, acceptable: set[str], rationale: str
) -> AttackCase:
    return AttackCase(
        case_id=case_id,
        family=family,
        mode=Mode.LITIGATOR,
        claim=claim,
        source=f"bounded demo corpus: {_REAL_NAME}, {_REAL_CITE} (1954, SCOTUS)",
        acceptable_states=frozenset(acceptable),
        rationale=rationale,
        origin="hand:litigator",
    )


def litigator_cases() -> Iterator[AttackCase]:
    # Control: the real cite with the real caption must stay supported.
    yield _lit_case(
        "lit|control|brown",
        "citation-verbatim-control",
        f"In {_REAL_NAME}, {_REAL_CITE}, the Court held that segregation in public schools is unconstitutional.",
        {SUPPORTED},
        "Correct caption + correct cite; the engine must still affirm a real citation.",
    )
    # Caption mismatch: real number, fabricated case name.
    for name in _FAKE_CAPTIONS:
        yield _lit_case(
            f"lit|caption|{name.split()[0].lower()}",
            "citation-caption-mismatch",
            f"As held in {name}, {_REAL_CITE}, the challenged statute was unconstitutional.",
            {CONTRADICTED, COULD_NOT_VERIFY},
            f"Real number {_REAL_CITE} wears a fabricated caption ({name}); must not be affirmed.",
        )
    # Year mismatch: real cite, wrong year (the case is 1954).
    for year in ("2021", "2024", "1999"):
        yield _lit_case(
            f"lit|year|{year}",
            "citation-year-mismatch",
            f"In {_REAL_NAME}, {_REAL_CITE} ({year}), the Court rejected segregation.",
            {CONTRADICTED, COULD_NOT_VERIFY},
            f"Real cite with a fabricated year ({year}); the decision is 1954.",
        )
    # Court mismatch: real cite (SCOTUS), wrong court.
    for court in ("9th Cir.", "2d Cir.", "S.D.N.Y."):
        yield _lit_case(
            f"lit|court|{court.split()[0].lower().replace('.', '')}",
            "citation-court-mismatch",
            f"In {_REAL_NAME}, {_REAL_CITE} ({court} 1954), segregation was rejected.",
            {CONTRADICTED, COULD_NOT_VERIFY},
            f"Real SCOTUS cite attributed to the wrong court ({court}).",
        )
    # Fabricated cite: no such case in the bounded corpus.
    for cite in _FAKE_CITES:
        yield _lit_case(
            f"lit|fabricated|{cite.split()[0]}",
            "citation-fabricated",
            f"As established in {cite}, the doctrine applies here.",
            {COULD_NOT_VERIFY, CONTRADICTED},
            f"Fabricated citation {cite} resolves to no case; must never be affirmed.",
        )


def clean_controls(seeds: list[Seed]) -> Iterator[AttackCase]:
    """The unperturbed non-quote seeds: a clean claim consistent with its clause.

    A genuinely-matching value may honestly read as supported (the value matches) OR
    as could-not-verify (money/duration are scoped out by ADR-0013, multi-value
    clauses refuse). Both are honest. The ONLY crack on a clean claim is a spurious
    contradiction — a false accusation. Quote controls are emitted by the quote
    mutator instead.
    """

    for seed in seeds:
        if seed.anchor_type == QUOTE:
            continue
        yield AttackCase(
            case_id=f"{seed.seed_id}|clean-control",
            family="clean-control",
            mode=Mode.CONTRACT,
            claim=seed.claim,
            source=seed.clause,
            acceptable_states=frozenset({SUPPORTED, COULD_NOT_VERIFY}),
            rationale="Clean claim consistent with the clause; must not be accused.",
            origin=f"seed:{seed.seed_id};control",
        )


# Single-value subject-mismatch: the claim asserts the clause's ONLY value but
# attributes it to a DIFFERENT subject. The value matches; the subject does not. The
# engine must not affirm (supported) a value the clause never attributes to the
# claim's subject. This is the real single-clause subject-binding risk (distinct from
# the multi-value subject-swap family, where the engine refuses on multi-value).
_SUBJECT_MISMATCH = [
    (
        "subjmismatch.percent_royalty",
        "The audit fee is 10% of Net Sales.",
        "Licensee shall pay Licensor a royalty of 10% of Net Sales",
        "10% is the royalty rate; the claim re-attributes it to an audit fee.",
    ),
    (
        "subjmismatch.percent_interest",
        "The early-payment discount is 8%.",
        "overdue amounts shall bear interest at a rate of 8% per annum",
        "8% is the default interest rate; the claim re-attributes it to a discount.",
    ),
    (
        "subjmismatch.money_price",
        "The breakup fee is $15,000,000.",
        "the Buyer shall pay the Seller a purchase price of $15,000,000 at Closing",
        "$15,000,000 is the purchase price; the claim re-attributes it to a breakup fee.",
    ),
    (
        "subjmismatch.duration_cure",
        "The warranty period lasts 30 days.",
        "the breaching party shall have 30 days after written notice to cure the breach",
        "30 days is the cure period; the claim re-attributes it to a warranty period.",
    ),
]


def subject_mismatch_single_cases() -> Iterator[AttackCase]:
    for case_id, claim, clause, rationale in _SUBJECT_MISMATCH:
        yield AttackCase(
            case_id=case_id,
            family="subject-mismatch-single",
            mode=Mode.CONTRACT,
            claim=claim,
            source=clause,
            acceptable_states=frozenset({COULD_NOT_VERIFY, CONTRADICTED}),
            rationale=rationale
            + " Affirming it (supported) would be subject-blind: a false green.",
            origin="hand:subject-mismatch-single",
        )


def all_cases(seeds: list[Seed] | None = None) -> list[AttackCase]:
    seeds = SEEDS if seeds is None else seeds
    cases: list[AttackCase] = []
    cases.extend(contract_cases(seeds))
    cases.extend(clean_controls(seeds))
    cases.extend(subject_mismatch_single_cases())
    cases.extend(litigator_cases())
    return cases
