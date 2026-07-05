"""Kernel-owned residue detectors: the anchor types the legal engine never had.

Closes the blind spots the 2026-07-02 parity experiment documented (drug
dosages, physical-unit quantities, bare grouped counts) at the KERNEL level --
no legal-pack involvement, stdlib only, pure functions.

Honesty disciplines, enforced by construction:

- **Ambiguous units never convert.** Metric mass/volume/distance/energy/power
  convert exactly within their family; units with regional variants (ton,
  gallon, pint, ounce, cup) each live in an ISOLATED dimension and compare
  only against the same unit word, so a short-ton vs metric-tonne confusion
  can structurally never mint an accusation.
- **Year-shaped integers are not counts.** A bare 1800-2199 integer refuses
  rather than reading "in 2024" as a quantity claim. Comma-grouped forms
  ("2,024") are always counts.
- **Accusations need a near-verbatim context.** A residue value only
  contradicts when the claim and the source sentence are the same sentence
  with the figures masked (the skeleton test) -- the canonical LLM-drift
  shape. Anything looser refuses; it never guesses.
- **Confirmation is narrower still.** Only an exact restatement (identical
  normalized text) or an equal-values near-copy confirms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# ---------------------------------------------------------------------------
# Unit taxonomy. Each entry: unit surface -> (dimension, factor to base unit).
# A dimension converts internally; two anchors compare ONLY within one
# dimension. Isolated dimensions (ton, oz, gal, ...) carry the unit word in
# the dimension name so they only ever compare against themselves.
# ---------------------------------------------------------------------------

_UNIT_TABLE: dict[str, tuple[str, Decimal]] = {
    # metric mass (base: microgram)
    "mcg": ("mass_metric", Decimal(1)),
    "ug": ("mass_metric", Decimal(1)),
    "µg": ("mass_metric", Decimal(1)),
    "microgram": ("mass_metric", Decimal(1)),
    "micrograms": ("mass_metric", Decimal(1)),
    "mg": ("mass_metric", Decimal(1_000)),
    "milligram": ("mass_metric", Decimal(1_000)),
    "milligrams": ("mass_metric", Decimal(1_000)),
    # NOTE (mythos batchA-20260702, false-accusation floor): bare single-letter
    # unit surfaces ("g", "m", "l", "w") are structurally ambiguous in prose --
    # enumeration markers ("Question 4 g"), network generations ("5G"), finance
    # shorthand ("10m"), Roman-alphabet labels -- and a wrong reading here mints
    # a confident RED on faithful text. They are deliberately ABSENT from this
    # table; their quantities land as honest refusals until an unambiguous
    # detector exists. Multi-letter surfaces only.
    "gram": ("mass_metric", Decimal(1_000_000)),
    "grams": ("mass_metric", Decimal(1_000_000)),
    "kg": ("mass_metric", Decimal(1_000_000_000)),
    "kilogram": ("mass_metric", Decimal(1_000_000_000)),
    "kilograms": ("mass_metric", Decimal(1_000_000_000)),
    # metric volume (base: microliter)
    "mcl": ("volume_metric", Decimal(1)),
    "µl": ("volume_metric", Decimal(1)),
    "ml": ("volume_metric", Decimal(1_000)),
    "milliliter": ("volume_metric", Decimal(1_000)),
    "milliliters": ("volume_metric", Decimal(1_000)),
    "cl": ("volume_metric", Decimal(10_000)),
    "dl": ("volume_metric", Decimal(100_000)),
    "liter": ("volume_metric", Decimal(1_000_000)),
    "liters": ("volume_metric", Decimal(1_000_000)),
    "litre": ("volume_metric", Decimal(1_000_000)),
    "litres": ("volume_metric", Decimal(1_000_000)),
    # metric distance (base: millimeter)
    "mm": ("distance_metric", Decimal(1)),
    "cm": ("distance_metric", Decimal(10)),
    "meter": ("distance_metric", Decimal(1_000)),
    "meters": ("distance_metric", Decimal(1_000)),
    "metre": ("distance_metric", Decimal(1_000)),
    "metres": ("distance_metric", Decimal(1_000)),
    "km": ("distance_metric", Decimal(1_000_000)),
    "kilometer": ("distance_metric", Decimal(1_000_000)),
    "kilometers": ("distance_metric", Decimal(1_000_000)),
    "kilometre": ("distance_metric", Decimal(1_000_000)),
    "kilometres": ("distance_metric", Decimal(1_000_000)),
    # energy (base: watt-hour)
    "wh": ("energy", Decimal(1)),
    "kwh": ("energy", Decimal(1_000)),
    "mwh": ("energy", Decimal(1_000_000)),
    "gwh": ("energy", Decimal(1_000_000_000)),
    # power (base: watt)
    "kw": ("power", Decimal(1_000)),
    "mw": ("power", Decimal(1_000_000)),
    "gw": ("power", Decimal(1_000_000_000)),
    # decimal data sizes (base: megabyte; binary-vs-decimal ambiguity is why
    # cross-size conversion stays within this one decimal family)
    "mb": ("data_decimal", Decimal(1)),
    "gb": ("data_decimal", Decimal(1_000)),
    "tb": ("data_decimal", Decimal(1_000_000)),
    "pb": ("data_decimal", Decimal(1_000_000_000)),
    # dosage IU (its own dimension; never converts to mass)
    "iu": ("iu", Decimal(1)),
    # isolated, regionally ambiguous units: same-word comparison only
    "ton": ("unit_ton", Decimal(1)),
    "tons": ("unit_ton", Decimal(1)),
    "tonne": ("unit_tonne", Decimal(1)),
    "tonnes": ("unit_tonne", Decimal(1)),
    "oz": ("unit_oz", Decimal(1)),
    "ounce": ("unit_oz", Decimal(1)),
    "ounces": ("unit_oz", Decimal(1)),
    "lb": ("unit_lb", Decimal(1)),
    "lbs": ("unit_lb", Decimal(1)),
    "pound": ("unit_lb", Decimal(1)),
    "pounds": ("unit_lb", Decimal(1)),
    "gal": ("unit_gal", Decimal(1)),
    "gallon": ("unit_gal", Decimal(1)),
    "gallons": ("unit_gal", Decimal(1)),
    "barrel": ("unit_barrel", Decimal(1)),
    "barrels": ("unit_barrel", Decimal(1)),
    "mile": ("unit_mile", Decimal(1)),
    "miles": ("unit_mile", Decimal(1)),
    "acre": ("unit_acre", Decimal(1)),
    "acres": ("unit_acre", Decimal(1)),
}

_UNIT_WORDS = "|".join(sorted((re.escape(u) for u in _UNIT_TABLE), key=len, reverse=True))

# number + unit word, unit NOT glued to a longer word ("5 mgx" is not a dose).
# Digit runs are length-bounded (no real figure carries 18+ significant digits,
# and no grouped number exceeds 8 comma groups): an unbounded `\d+` before the
# required trailing unit backtracks super-linearly on a long anchorless digit
# run, and finditer re-scans every start position, so an anchorless run gives
# O(n^2) -- a DoS reachable through the daemon's /verify claim text. The fixed
# upper bounds make each match attempt O(1) and the whole scan linear. (CWE-1333;
# the companion's parametric fork carried this bound, the kernel had drifted
# without it -- ADR-0014 surfaced the gap.)
_QUANTITY = re.compile(
    rf"(?P<num>\d{{1,3}}(?:,\d{{3}}){{1,8}}(?:\.\d+)?|\d{{1,18}}(?:\.\d+)?)\s?(?P<unit>{_UNIT_WORDS})\b",
    re.IGNORECASE,
)

# Comma-grouped integers are always counts; plain integers of 4+ digits are
# counts only outside the year-shaped band.
_GROUPED_COUNT = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
_PLAIN_COUNT = re.compile(r"\b\d{4,9}\b")

# EU-format ambiguity guards (adversarial battery, batch F). "1.000" is one
# thousand in Frankfurt and exactly one in Boston; "1,5" is one-and-a-half in
# Paris and a stray comma in New York. A deterministic engine must not pick a
# locale: dot-grouped numbers refuse, and a number token that is really the
# TAIL of a larger EU-decimal ("5" inside "1,5") must not anchor at all.
_DOT_GROUPED = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_NUMBER_TAIL = re.compile(r"\d[.,]$")


def _ambiguous_number(text: str, start: int, num: str) -> bool:
    if _DOT_GROUPED.match(num):
        return True
    return bool(_NUMBER_TAIL.match(text[max(0, start - 2) : start]))


@dataclass(frozen=True)
class ResidueAnchor:
    kind: str  # "quantity" | "count"
    text: str
    start: int
    end: int
    dimension: str
    canonical: Decimal


def _num(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def _year_shaped(surface: str) -> bool:
    if "," in surface or len(surface) != 4:
        return False
    return 1800 <= int(surface) <= 2199


def extract_residue_anchors(
    text: str, claimed_spans: list[tuple[int, int]] | None = None
) -> list[ResidueAnchor]:
    """Extract quantity and count anchors, skipping spans another detector
    already claimed (money, percent, duration, magnitude, date, citation).
    Precedence prevents double-counting: "$5 million" is money, never a count.
    """
    claimed = list(claimed_spans or [])

    def free(start: int, end: int) -> bool:
        return not any(start < ce and cs < end for cs, ce in claimed)

    anchors: list[ResidueAnchor] = []
    for m in _QUANTITY.finditer(text):
        if not free(m.start(), m.end()):
            continue
        if _ambiguous_number(text, m.start("num"), m.group("num")):
            continue
        dimension, factor = _UNIT_TABLE[m.group("unit").lower()]
        anchors.append(
            ResidueAnchor(
                kind="quantity",
                text=m.group(0),
                start=m.start(),
                end=m.end(),
                dimension=dimension,
                canonical=_num(m.group("num")) * factor,
            )
        )
        claimed.append((m.start(), m.end()))

    for pattern in (_GROUPED_COUNT, _PLAIN_COUNT):
        for m in pattern.finditer(text):
            if not free(m.start(), m.end()):
                continue
            if pattern is _PLAIN_COUNT and _year_shaped(m.group(0)):
                continue
            if _ambiguous_number(text, m.start(), m.group(0)):
                continue
            anchors.append(
                ResidueAnchor(
                    kind="count",
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    dimension="count",
                    canonical=_num(m.group(0)),
                )
            )
            claimed.append((m.start(), m.end()))

    anchors.sort(key=lambda a: a.start)
    return anchors


# ---------------------------------------------------------------------------
# Near-copy comparison. The accusation gate: claim and source sentence must be
# the SAME sentence with figures masked before any residue mismatch may
# accuse. Mirrors the legal engine's altered-figures-on-near-copy discipline
# without touching it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidueComparison:
    """Outcome of comparing one claim against one source sentence.

    ``state`` uses the kernel verdict vocabulary. ``detail`` is filing-grade.
    """

    state: str  # verified | altered | could_not_check
    detail: str
    subject: str


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    out: list[str] = []
    last = 0
    for start, end in sorted(spans):
        out.append(text[last:start])
        out.append("#")
        last = end
    out.append(text[last:])
    return _normalize(" ".join(out))


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def compare_residue(
    claim: str,
    claim_anchors: list[ResidueAnchor],
    claim_masked_spans: list[tuple[int, int]],
    sentence: str,
    sentence_anchors: list[ResidueAnchor],
    sentence_masked_spans: list[tuple[int, int]],
) -> ResidueComparison | None:
    """Compare a claim's residue anchors against one source sentence.

    Returns None when the sentence is not a near-copy (no basis to rule).
    ``*_masked_spans`` are ALL anchor spans (residue plus any other detector's)
    so a differing money figure elsewhere in the sentence cannot break the
    skeleton match that the residue comparison rides on.
    """
    if not claim_anchors:
        return None
    claim_skeleton = _mask(claim, claim_masked_spans)
    sentence_skeleton = _mask(sentence, sentence_masked_spans)
    if claim_skeleton != sentence_skeleton:
        return None

    # Positional pairing: the skeletons are identical, so the i-th residue
    # anchor in the claim corresponds to the i-th in the sentence. Evaluate
    # EVERY pair before answering: a caught alteration outranks a cross-family
    # refusal, which outranks confirmation.
    if len(claim_anchors) != len(sentence_anchors):
        return None
    cross_family: ResidueComparison | None = None
    for ca, sa in zip(claim_anchors, sentence_anchors):
        if ca.dimension != sa.dimension:
            # Same sentence shape but a different unit family ("100 tons" vs
            # "100 tonnes", "5 mg" vs "5 mL"). A cross-family comparison is
            # impossible, and regional variants (ton/tonne, oz) may describe
            # the SAME real quantity -- accusing here risks a false red, so
            # refuse and name both surfaces instead.
            cross_family = ResidueComparison(
                state="could_not_check",
                detail=(
                    f"The summary states {ca.text}; the loaded source states "
                    f"{sa.text}. The unit families differ, so a deterministic "
                    f"comparison cannot rule."
                ),
                subject=ca.text,
            )
            continue
        if ca.canonical != sa.canonical:
            return ResidueComparison(
                state="altered",
                detail=(f"The summary states {ca.text}; the loaded source states {sa.text}."),
                subject=ca.text,
            )
    if cross_family is not None:
        return cross_family
    return ResidueComparison(
        state="verified",
        detail="Every quantity in this near-verbatim statement matches the source.",
        subject=", ".join(a.text for a in claim_anchors),
    )
