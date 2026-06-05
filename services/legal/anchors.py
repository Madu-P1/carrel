"""Anchor detection for the Cachet deterministic verify engine.

An "anchor" is a deterministically detectable token that makes a
statement independently checkable: a citation, a quoted run, a money
amount, a date or duration, a section reference. Cachet verifies spans
that carry an anchor; anchor-free spans route to the loud
"not independently verifiable" tray, never silently passed.

Honesty tier T0: every detector is pure regex / string / table lookup,
no learned weights, no network. Money, duration, and date carry a
``canonical_value`` (integer cents, integer days, ISO date string) so a
downstream contradiction check is pure arithmetic.

Citation and quoted-run detection reuse the existing T0 building blocks
(``citations_eyecite``, ``quote_check``). The money/duration/date/section
regexes are clean-room MIT implementations (LexNLP is AGPL and partly
classifier-backed, so it is deliberately not used).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dateutil import parser as date_parser

from .citations_eyecite import find_citations
from .quote_check import extract_draft_quote_spans


@dataclass(frozen=True)
class Anchor:
    """One verifiable artifact located in a span.

    ``start``/``end`` are character offsets into the span passed to
    :func:`extract_anchors`. ``canonical_value`` is populated only for
    parametric types: money -> integer cents, duration -> integer days,
    date -> ISO ``YYYY-MM-DD`` string. It is ``None`` for the rest.
    """

    type: str  # citation | slip_op | quote | money | duration | date | section
    text: str
    start: int
    end: int
    canonical_value: object | None = None


_SLIP_OP = re.compile(r"\bNo\.\s+\d{1,4}-\d{1,6}\b|\bslip\s+op\.", re.IGNORECASE)

# Scale words must be standalone (not "Million-dollar" adjective, not part of a
# longer word); single-letter M/B/K must be suffixed directly to the number
# ("$5M" scales, "$5 m" does not, because a spaced bare letter is ambiguous).
_MONEY = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:million|billion|thousand)(?![-\w])|(?:MM|M|B|K)(?![-\w]))?",
    re.IGNORECASE,
)

# Matches "5 years", "five (5) years", "30 calendar days". The digit may be bare
# or in the legal "word (digit)" convention; an optional spelled-out number word
# is captured for display (restricted to number words so it cannot grab "of").
_DURATION = re.compile(
    r"(?:(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+)?"
    r"(?:\((?P<paren>\d+)\)|\b(?P<num>\d+))\s+(?:calendar\s+)?(?P<unit>year|month|week|day)s?\b",
    re.IGNORECASE,
)

_SECTION = re.compile(
    r"\b(?:Section|Sec\.|§|Clause|Article|Schedule|Exhibit)\s+\d+(?:\.\d+)*(?:\([a-z0-9]+\))?",
    re.IGNORECASE,
)

_DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4})\b"
)

_MONEY_SCALE = {
    "thousand": 1_000,
    "k": 1_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "mm": 1_000_000,  # legal/finance notation: $5MM == $5 million
    "billion": 1_000_000_000,
    "b": 1_000_000_000,
}
_DURATION_DAYS = {"year": 365, "month": 30, "week": 7, "day": 1}


def _money_cents(text: str) -> int | None:
    """Canonical integer cents for a matched money span, or None."""
    m = re.search(
        r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|thousand|MM|M|B|K)?", text, re.IGNORECASE
    )
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    scale = m.group(2)
    if scale:
        amount *= _MONEY_SCALE[scale.lower()]
    return round(amount * 100)


def _duration_days(num: int, unit: str) -> int:
    """Canonical day count (year=365, month=30, week=7, day=1, approximate)."""
    return num * _DURATION_DAYS[unit.lower()]


def _date_iso(text: str) -> str | None:
    try:
        return date_parser.parse(text, fuzzy=False).date().isoformat()
    except (ValueError, OverflowError):
        return None


def extract_anchors(span: str) -> list[Anchor]:
    """Return every verifiable anchor in ``span`` (possibly several types)."""
    if not span or not span.strip():
        return []
    anchors: list[Anchor] = []
    for ref in find_citations(span):
        anchors.append(Anchor("citation", ref.matched_text, ref.start, ref.end))
    for m in _SLIP_OP.finditer(span):
        anchors.append(Anchor("slip_op", m.group(0), m.start(), m.end()))
    for text, start, end in extract_draft_quote_spans(span):
        anchors.append(Anchor("quote", text, start, end))
    for m in _MONEY.finditer(span):
        anchors.append(Anchor("money", m.group(0), m.start(), m.end(), _money_cents(m.group(0))))
    for m in _DURATION.finditer(span):
        num = int(m.group("paren") or m.group("num"))
        anchors.append(
            Anchor("duration", m.group(0), m.start(), m.end(), _duration_days(num, m.group("unit")))
        )
    for m in _DATE.finditer(span):
        iso = _date_iso(m.group(0))
        if iso is not None:
            # Drop date-shaped but invalid values (2024-13-45) rather than emit
            # an anchor whose canonical_value is None (two would compare equal).
            anchors.append(Anchor("date", m.group(0), m.start(), m.end(), iso))
    for m in _SECTION.finditer(span):
        anchors.append(Anchor("section", m.group(0), m.start(), m.end()))
    return anchors


def has_anchor(span: str) -> bool:
    """True if ``span`` carries any verifiable anchor."""
    return bool(extract_anchors(span))
