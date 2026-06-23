"""Typed, audited perturbations that turn clean seeds into adversarial cases.

Each mutator derives the honest expectation from the perturbation, so a divergence
from that expectation is a real crack, never a guess. Two confidence tiers:

  - PROVEN families assert a hard expectation the engine demonstrably meets in the
    test suite (a mismatched single money/duration/percent/date value is a
    parametric contradiction). For these, ``acceptable_states`` is a single state,
    so a could-not-verify there is laundering and a supported is a false green.
  - EXPLORATORY families (polarity, governing law) only assert the engine must not
    AFFIRM the altered claim. ``acceptable_states`` includes could-not-verify, so an
    honest refusal is HELD and only a supported is a crack. The ledger reports their
    catch-rate as a coverage stat instead of inflating laundering claims.

Quote alteration is the highest-value family: a fabricated quote that the engine
affirms (supported) is a false green — the exact 2026 sanctions-frontier failure.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from .contracts import CONTRADICTED, COULD_NOT_VERIFY, SUPPORTED, AttackCase, Mode
from .corpus import (
    DATE,
    DURATION,
    GOVERNING_LAW,
    MONEY,
    PERCENT,
    POLARITY,
    QUOTE,
    Seed,
)

_MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


def _case(
    seed: Seed,
    family: str,
    tag: str,
    claim: str,
    acceptable: set[str],
    rationale: str,
    *,
    source: str | None = None,
) -> AttackCase:
    return AttackCase(
        case_id=f"{seed.seed_id}|{family}|{tag}",
        family=family,
        mode=Mode.CONTRACT,
        claim=claim,
        source=seed.clause if source is None else source,
        acceptable_states=frozenset(acceptable),
        rationale=rationale,
        origin=f"seed:{seed.seed_id};mutator:{family}",
    )


# --- money ------------------------------------------------------------------

# A diverse pool of distinct amounts. The generator filters out any that equal the
# seed's own value so a "contradiction" variant is always genuinely different.
_MONEY_POOL = [
    "$1,000",
    "$10,000",
    "$25,000",
    "$50,000",
    "$75,000",
    "$100,000",
    "$150,000",
    "$200,000",
    "$300,000",
    "$400,000",
    "$450,000",
    "$499,999",
    "$500,001",
    "$600,000",
    "$750,000",
    "$1,000,000",
    "$1,250,000",
    "$1,500,000",
    "$2,500,000",
    "$3,000,000",
    "$5,000,000",
    "$7,500,000",
    "$10,000,000",
    "$25,000,000",
]


def _money_int(s: str) -> int:
    digits = re.sub(r"[^\d]", "", s)
    return int(digits) if digits else -1


def money_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != MONEY or not seed.value or not seed.single_value:
        return
    base_int = _money_int(seed.value or "")
    for variant in _MONEY_POOL:
        if _money_int(variant) == base_int:
            continue
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "value-contradiction-money",
            variant,
            claim,
            {CONTRADICTED},
            f"AI summary states {variant}; the executed clause states {seed.value}.",
        )
    # Magnitude scaling (million -> billion class): same digits, three orders bigger.
    if base_int > 0:
        scaled = f"${base_int * 1000:,}"
        claim = seed.claim.replace(seed.value, scaled, 1)
        yield _case(
            seed,
            "magnitude-scaling-money",
            "x1000",
            claim,
            {CONTRADICTED},
            f"Magnitude inflated x1000 ({seed.value} -> {scaled}); the tampered-slide class.",
        )
    # Word-form contradiction the digit-only matcher must still catch.
    if base_int != 1_000_000:
        claim = seed.claim.replace(seed.value, "one million dollars", 1)
        yield _case(
            seed,
            "word-form-money",
            "one-million",
            claim,
            {CONTRADICTED},
            f"Spelled-out one million dollars vs the clause's {seed.value}.",
        )


# --- duration ---------------------------------------------------------------

_DUR_RANGES = {"year": (1, 15), "month": (1, 48), "week": (1, 52), "day": (5, 185)}


def _parse_duration(value: str) -> tuple[int, str] | None:
    m = re.search(r"(\d+)\s*(year|month|week|day)s?", value, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), m.group(2).lower()


def duration_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != DURATION or not seed.value or not seed.single_value:
        return
    parsed = _parse_duration(seed.value or "")
    if parsed is None:
        return
    num, unit = parsed
    lo, hi = _DUR_RANGES[unit]
    step = 5 if unit == "day" else 1
    for n in range(lo, hi + 1, step):
        if n == num:
            continue
        variant = f"{n} {unit}s" if n != 1 else f"{n} {unit}"
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "near-miss-duration",
            variant.replace(" ", "-"),
            claim,
            {CONTRADICTED},
            f"Same-unit term {variant} vs the clause's {seed.value}: a different term.",
        )
    # Cross-unit magnitude change (unit confusion): same number, different unit.
    for other in ("year", "month", "week", "day"):
        if other == unit:
            continue
        variant = f"{num} {other}s" if num != 1 else f"{num} {other}"
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "unit-confusion-duration",
            variant.replace(" ", "-"),
            claim,
            {CONTRADICTED},
            f"Unit swapped: {variant} vs the clause's {seed.value}.",
        )
    # Equivalence: years<->months of the SAME term must NOT be a contradiction.
    if unit == "year":
        equiv = f"{num * 12} months"
        claim = seed.claim.replace(seed.value, equiv, 1)
        yield _case(
            seed,
            "equivalent-duration",
            equiv.replace(" ", "-"),
            claim,
            {SUPPORTED, COULD_NOT_VERIFY},
            f"{equiv} is the same term as {seed.value}; must not be flagged as a contradiction.",
        )
    elif unit == "month" and num % 12 == 0:
        equiv = f"{num // 12} years" if num // 12 != 1 else "1 year"
        claim = seed.claim.replace(seed.value, equiv, 1)
        yield _case(
            seed,
            "equivalent-duration",
            equiv.replace(" ", "-"),
            claim,
            {SUPPORTED, COULD_NOT_VERIFY},
            f"{equiv} is the same term as {seed.value}; must not be flagged as a contradiction.",
        )


# --- percent ----------------------------------------------------------------


def _parse_percent(value: str) -> int | None:
    m = re.search(r"(\d+)\s*%", value)
    return int(m.group(1)) if m else None


def percent_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != PERCENT or not seed.value or not seed.single_value:
        return
    base = _parse_percent(seed.value or "")
    if base is None:
        return
    for n in range(1, 41):
        if n == base:
            continue
        variant = f"{n}%"
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "value-contradiction-percent",
            variant,
            claim,
            {CONTRADICTED},
            f"Rate {variant} vs the clause's {seed.value}.",
        )
    # Format-equivalent: same rate, different surface -> must not be a contradiction.
    for variant in (f"{base}.0%", f"{base} percent"):
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "format-variant-percent",
            variant.replace(" ", "-").replace("%", "pct"),
            claim,
            {SUPPORTED, COULD_NOT_VERIFY},
            f"{variant} is the same rate as {seed.value}; must not be flagged.",
        )


# --- date -------------------------------------------------------------------


def _parse_date(value: str) -> tuple[str, int, int] | None:
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", value)
    if not m or m.group(1) not in _MONTHS:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3))


def date_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != DATE or not seed.value or not seed.single_value:
        return
    parsed = _parse_date(seed.value or "")
    if parsed is None:
        return
    month_name, day, year = parsed
    month_num = _MONTHS[month_name]
    # Year shifts (always valid).
    for dy in (-3, -2, -1, 1, 2, 3, 5):
        variant = f"{month_name} {day}, {year + dy}"
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "value-contradiction-date",
            f"year{year + dy}",
            claim,
            {CONTRADICTED},
            f"Year shifted: {variant} vs the clause's {seed.value}.",
        )
    # Day shifts (kept <=28 so they are valid in any month).
    for nd in (1, 5, 15, 20, 25):
        if nd == day:
            continue
        variant = f"{month_name} {nd}, {year}"
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "value-contradiction-date",
            f"day{nd}",
            claim,
            {CONTRADICTED},
            f"Day shifted: {variant} vs the clause's {seed.value}.",
        )
    # Format-equivalent: same calendar date, different surface -> must not flag.
    iso = f"{year:04d}-{month_num:02d}-{day:02d}"
    us = f"{month_num:02d}/{day:02d}/{year}"
    for variant in (iso, us):
        claim = seed.claim.replace(seed.value, variant, 1)
        yield _case(
            seed,
            "format-variant-date",
            variant.replace("/", "-"),
            claim,
            {SUPPORTED, COULD_NOT_VERIFY},
            f"{variant} is the same date as {seed.value}; must not be flagged.",
        )


# --- subject swap (right value, wrong subject) ------------------------------

_SUBJECT_SWAPS = {
    "France": ["Germany", "Spain", "Italy", "Belgium"],
    "Class A": ["Class B", "Class C", "the Series A"],
}


def subject_mutations(seed: Seed) -> Iterator[AttackCase]:
    if not seed.subject:
        return
    for other in _SUBJECT_SWAPS.get(seed.subject, []):
        claim = seed.claim.replace(seed.subject, other, 1)
        yield _case(
            seed,
            "subject-swap",
            other.replace(" ", "-"),
            claim,
            {COULD_NOT_VERIFY, CONTRADICTED},
            f"Value {seed.value} re-attributed from {seed.subject} to {other}; "
            f"must not be affirmed as supported for {other}.",
        )


# --- governing law (exploratory) --------------------------------------------

_LAW_SWAPS = ["Delaware", "California", "New Jersey", "Texas", "England and Wales"]


def governing_law_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != GOVERNING_LAW or not seed.value:
        return
    for other in _LAW_SWAPS:
        if other.split()[0].lower() == seed.value.split()[0].lower():
            continue
        claim = seed.claim.replace(seed.value, other, 1)
        yield _case(
            seed,
            "governing-law-lookalike",
            other.replace(" ", "-"),
            claim,
            {CONTRADICTED, COULD_NOT_VERIFY},
            f"Governing law swapped to {other}; the clause names {seed.value}. "
            f"Must not be affirmed.",
        )


# --- polarity (exploratory) -------------------------------------------------

_POLARITY_SWAPS = {
    "exclusive": ["non-exclusive", "nonexclusive"],
    "survives": ["does not survive", "terminates upon"],
}


def polarity_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != POLARITY or not seed.value:
        return
    for other in _POLARITY_SWAPS.get(seed.value, []):
        claim = seed.claim.replace(seed.value, other, 1)
        yield _case(
            seed,
            "polarity-flip",
            other.replace(" ", "-"),
            claim,
            {CONTRADICTED, COULD_NOT_VERIFY},
            f"Polarity flipped ({seed.value} -> {other}); the clause asserts {seed.value}. "
            f"Must not be affirmed.",
        )


# --- quote alteration (highest value) ---------------------------------------

_QUOTE_ALTERATIONS = {
    "survive termination": [
        "survive expiration",
        "survive cancellation",
        "survive any rescission",
        "expire on termination",
    ],
    "indemnify and hold harmless": [
        "indemnify and defend",
        "indemnify and hold blameless",
        "reimburse and hold harmless",
        "indemnify but not defend",
    ],
    "time is of the essence": [
        "time is not of the essence",
        "timing is of the essence",
        "time is of no essence",
        "time may be of the essence",
    ],
    "as is": [
        "as available",
        "free of defects",
        "in pristine condition",
        "fit for purpose",
    ],
}


def quote_mutations(seed: Seed) -> Iterator[AttackCase]:
    if seed.anchor_type != QUOTE or not seed.quote:
        return
    # Control: the verbatim quote IS present -> the engine must still affirm it.
    yield _case(
        seed,
        "quote-verbatim-control",
        "verbatim",
        seed.claim,
        {SUPPORTED},
        f'Verbatim quote "{seed.quote}" is present in the clause; must stay supported.',
    )
    quoted = f'"{seed.quote}"'
    for altered in _QUOTE_ALTERATIONS.get(seed.quote, []):
        claim = seed.claim.replace(quoted, f'"{altered}"', 1)
        yield _case(
            seed,
            "quote-alteration",
            altered.replace(" ", "-"),
            claim,
            {COULD_NOT_VERIFY},
            f'Fabricated quote "{altered}" is NOT in the clause; affirming it is a false green.',
        )


CONTRACT_MUTATORS = (
    money_mutations,
    duration_mutations,
    percent_mutations,
    date_mutations,
    subject_mutations,
    governing_law_mutations,
    polarity_mutations,
    quote_mutations,
)


def contract_cases(seeds: list[Seed]) -> Iterator[AttackCase]:
    """All contract-path adversarial cases generated from the seeds."""

    for seed in seeds:
        for mutator in CONTRACT_MUTATORS:
            yield from mutator(seed)
