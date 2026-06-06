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

# --- Party-name detector (canonical_value None). Two T0 sub-patterns. Real NER
# for un-aliased names is T1 and off (per the design doc), so the entity branch is
# a best-effort T0 heuristic with two inherent capitalized-word limits, both
# documented + tested and routed to the verifier (never a false verdict; the
# precision/recall point is an operator human-gate call): a capitalized prose word
# directly before a suffix is swept in ("Defendant Stark Industries LLC"), and an
# all-caps heading whose suffix is itself all-caps (LLC/LP/PLC) can match ("THE
# BOARD LLC"). The parenthetical-alias branch has no such ambiguity. ---

# Defined-party alias in parentheses: ("Buyer"), (the "Seller"), (the "Initial
# Purchaser"). Unambiguous and precise.
_PARTY_ALIAS = re.compile(r"""\((?:the\s+)?["“']([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)*)["”']\)""")
# Company name ending in an UNAMBIGUOUS corporate suffix abbreviation. The
# terminal "(?:\.(?![A-Za-z])|(?![A-Za-z.-]))" stops a suffix from matching a
# longer word ("Corporate", "LLCs", "Incorporated"), a dot-then-letter
# ("Corp.oration", "L.P.s"), or a hyphen-adjective ("PLC-level", "Inc-owned"),
# while still allowing the optional trailing dot ("Inc."). Generic "Company"/"Co"
# and the spelled-out forms "Corporation"/"Limited"/"N.A" are excluded (common
# English words that false-positive in prose like "The Limited Partners") - a
# documented recall gap. "and" is NOT a connector (it joins distinct parties);
# "&"/"of" are (within-name: "Bank of America").
_PARTY_ENTITY = re.compile(
    r"\b[A-Z][A-Za-z0-9&.'\-]*(?:\s(?:&|of|[A-Z][A-Za-z0-9&.'\-]*))*"
    r",?\s(?:Inc|LLC|L\.L\.C|Corp|Ltd|L\.P|LP|PLC|GmbH)(?:\.(?![A-Za-z])|(?![A-Za-z.\-]))"
)

# Defined-term definition pattern: a quoted, capitalized term (one or more words,
# all-caps included) immediately followed by `means | shall mean | refers to`. The
# parenthetical-alias form (the "Term") reuses _PARTY_ALIAS. Case-sensitive on the
# leading capital, so a lowercase "buyer" is not captured. It DOES over-capture a
# rhetorical `"X" means Y` from prose (e.g. `"Justice" means a lot`); that is the
# safe direction - an extra review anchor routed to the tray, never a false verdict;
# whether to tighten is a human gate. Single-letter and hyphenated terms ("A",
# "Class A", "Non-Competition") are a documented recall gap.
_DEFN = re.compile(
    r"""["“']([A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)*)["”']"""
    r"\s+(?:means|shall\s+mean|refers?\s+to|shall\s+refer\s+to)\b"
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


def _party_anchors(text: str) -> list[Anchor]:
    anchors: list[Anchor] = []
    for pattern in (_PARTY_ALIAS, _PARTY_ENTITY):
        for m in pattern.finditer(text):
            anchors.append(Anchor("party", m.group(0), m.start(), m.end()))
    return anchors


def build_alias_table(text: str) -> dict[str, str]:
    """Build a {defined-term -> canonical} map from a document's own definitions.

    Two T0 sources: the parenthetical alias form `(the "Buyer")` and the
    definition form `"Confidential Information" means ...`. canonical is the
    defined term itself (the normalization key); a richer canonical (what the term
    resolves to) is left to a later unit. Pass the result to `extract_anchors` as
    `alias_table` to detect occurrences of these terms as `defined_term` anchors.
    """
    table: dict[str, str] = {}
    for pattern in (_PARTY_ALIAS, _DEFN):
        for m in pattern.finditer(text):
            term = m.group(1)
            table[term] = term
    return table


def _defined_term_anchors(text: str, alias_table: dict[str, str]) -> list[Anchor]:
    # Occurrences of an actually-defined term. Precision is structural: only terms
    # the document itself defined are in the table, so this cannot fire on an
    # undefined capitalized word. canonical_value is the term's canonical form
    # (from the table, not the matched text). Terms are matched literally
    # (re.escape) at word boundaries; a term whose edge char is non-word (e.g.
    # "U.S.") may not match - build_alias_table only ever produces word-edge terms.
    anchors: list[Anchor] = []
    for term, canonical in alias_table.items():
        for m in re.finditer(rf"\b{re.escape(term)}\b", text):
            anchors.append(Anchor("defined_term", m.group(0), m.start(), m.end(), canonical))
    return anchors


def extract_anchors(span: str, *, alias_table: dict[str, str] | None = None) -> list[Anchor]:
    """Return every verifiable anchor in ``span`` (possibly several types).

    ``alias_table`` ({defined-term -> canonical}, e.g. from
    :func:`build_alias_table`) turns on the defined-term detector: occurrences of
    each defined term become ``defined_term`` anchors. With the default ``None``,
    no defined-term anchors are emitted and the result is identical to the other
    detectors alone. Anchors are returned sorted in document order.
    """
    if not span or not span.strip():
        return []
    anchors: list[Anchor] = []
    citation_spans: list[tuple[int, int]] = []
    for ref in find_citations(span):
        anchors.append(Anchor("citation", ref.matched_text, ref.start, ref.end))
        citation_spans.append((ref.start, ref.end))

    def _within_citation(a: Anchor) -> bool:
        return any(a.start < ce and cs < a.end for cs, ce in citation_spans)

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
        # A "section" hit inside a citation span is that citation's own section
        # symbol (e.g. the "§ 1983" of "42 U.S.C. § 1983"), not an intra-document
        # section reference; drop it so a statute is not double-counted. A
        # standalone section reference has no overlapping citation and survives.
        candidate = Anchor("section", m.group(0), m.start(), m.end())
        if not _within_citation(candidate):
            anchors.append(candidate)
    anchors.extend(_party_anchors(span))
    if alias_table:
        anchors.extend(_defined_term_anchors(span, alias_table))
    anchors.sort(key=lambda a: (a.start, a.end))
    return anchors


def has_anchor(span: str) -> bool:
    """True if ``span`` carries any verifiable anchor."""
    return bool(extract_anchors(span))
