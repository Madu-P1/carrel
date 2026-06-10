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
from decimal import Decimal

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

    type: str  # citation | slip_op | quote | money | duration | date | percent | section | party | defined_term
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

# Word-form money with no numeral ("one million dollars", "five hundred thousand
# dollars", "a billion dollars"). Bounded on purpose: a single leading number word
# (one..twenty, or "a"), an optional "hundred", and a scale word. An AI summary that
# paraphrases "$1,000,000" as "one million dollars" drops the numeral the digit
# _MONEY detector needs; without this the claim carries no money anchor and the
# parametric-contradiction catch cannot fire. The trailing negative lookahead
# defers to the digit form in the "one million dollars ($1,000,000)" convention so
# the figure is counted once. Compound numbers ("twenty-five million", "twenty
# five million", "one and a half million") and bare hundreds ("five hundred
# dollars") are outside the bounded grammar and must yield NO anchor, never a
# wrong value: the (?<![\w-]) guard stops "five" matching inside "twenty-five",
# and _NUMBER_WORD_BEFORE rejects a match whose preceding text ends with a
# number word ("twenty five million" must not anchor as $5M). A sentence whose
# only candidate anchor is rejected here carries no anchor at all and renders
# UNTREATED (plain draft text, no card) per the 2026-06-08 untreated split — a
# pinned recall gap (tests/test_anchors.py), not a hidden one.
_MONEY_WORD = re.compile(
    r"(?<![\w\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212])"
    r"(?P<unit>one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|a)\s+"
    r"(?:(?P<hundred>hundred)\s+)?"
    r"(?P<scale>thousand|million|billion)\s+(?:dollars|USD)\b"
    r"(?!\s*\(?\s*\$)",
    re.IGNORECASE,
)

# The compound rejector for _MONEY_WORD: a match is refused when the text right
# before it ends with a number word, because then the spelled-out amount is a
# space-separated compound the bounded grammar cannot represent and any
# canonical we minted would be the TAIL of the real number (a manufactured
# value in both verdict directions). Deliberately broader than
# _MONEY_WORD_UNITS: tens words and scale words reject too ("ninety five
# thousand", "hundred twenty five million").
_NUMBER_WORD_BEFORE = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion)[\s,.\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]*$",
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
    # Word keywords need a word boundary; the section sign (and its plural, §§)
    # does not. A leading \b before § never asserts (a space-to-§ run is non-word
    # to non-word), which is why a bare "§ 1983" / "§ 7.2" matched nothing before.
    r"(?:\b(?:Section|Sec\.|Clause|Article|Schedule|Exhibit)\s+|§§?\s?)"
    r"\d+(?:\.\d+)*(?:\([a-z0-9]+\))?",
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

# Percent / rate, DIGIT forms only with the unit marker in-span: "5%", "12.5
# percent", "12 per cent", "50 bps", "50 basis points". Canonical value is
# basis points via exact decimal arithmetic, so "0.5%" and "50 bps" compare
# equal with no float drift and no tolerance. Refusals, each pinned by tests,
# never a guessed value: word-form percent ("five percent" — the same
# bounded-grammar lesson as _MONEY_WORD), range forms ("5-10%": the leading
# lookbehind rejects a digit-dash-digit tail, so anchoring either end cannot
# manufacture a verdict against a clause stating the other), and "percentage
# points" (an additive quantity, not a rate; `percent\b` fails inside
# "percentage" and `points` is required after `basis` only).
_PERCENT = re.compile(
    # num accepts a plain digit run or VALID US thousands grouping only; a
    # European decimal comma ("12,5%") fits neither branch and the comma in the
    # lookbehind stops the tail ("5%") from anchoring alone, so the whole form
    # refuses rather than canonicalize 12,5% as 1250%. The lookbehind also
    # carries the Unicode dash family so "5\u201310%" and minus-signed rates
    # refuse the same way the ASCII range form does.
    r"(?<![\w.,\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212])"
    r"(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent\b|per\s?cent\b|bps\b|basis\s+points?\b)",
    re.IGNORECASE,
)

# Worded/spaced range rejector for _PERCENT: a match whose preceding text ends
# with a bare number and a range connector ("5 to ", "between 5 and ", "5 - ")
# is the TOP END of a range. Anchoring it would manufacture a verdict against a
# clause stating any other point of the range (the same rule the dash lookbehind
# enforces for "5-10%"). "from 5% to 10%" is NOT rejected: both ends carry the
# unit, two anchors emerge, and the multi-value refusal handles them honestly.
_PERCENT_RANGE_BEFORE = re.compile(
    r"\d\s*(?:[-\u2010\u2011\u2012\u2013\u2014\u2015\u2212]|\b(?:to|and|or|through)\b)\s*$",
    re.IGNORECASE,
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
_MONEY_WORD_UNITS = {
    "a": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


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


def _money_word_cents(unit: str, hundred: str | None, scale: str) -> int:
    """Canonical integer cents for a spelled-out money span (no numeral)."""
    amount = _MONEY_WORD_UNITS[unit.lower()]
    if hundred:
        amount *= 100
    amount *= _MONEY_SCALE[scale.lower()]
    return amount * 100


def _duration_days(num: int, unit: str) -> int:
    """Canonical day count (year=365, month=30, week=7, day=1, approximate)."""
    return num * _DURATION_DAYS[unit.lower()]


def _percent_bps(num_text: str, unit: str) -> Decimal:
    """Canonical basis points for a percent/rate span, exact decimal arithmetic."""
    value = Decimal(num_text.replace(",", ""))
    u = unit.lower()
    if u == "bps" or u.startswith("basis"):
        return value
    return value * 100


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
    for m in _MONEY_WORD.finditer(span):
        if _NUMBER_WORD_BEFORE.search(span[: m.start()]):
            # A space-separated compound ("twenty five million dollars"): the
            # match is only the tail of the real number. Refuse the anchor
            # rather than mint a wrong canonical value.
            continue
        cents = _money_word_cents(m.group("unit"), m.group("hundred"), m.group("scale"))
        anchors.append(Anchor("money", m.group(0), m.start(), m.end(), cents))
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
    for m in _PERCENT.finditer(span):
        if _PERCENT_RANGE_BEFORE.search(span[: m.start()]):
            # The top end of a worded/spaced range ("between 5 and 10%"):
            # refuse the anchor rather than collapse a range to one endpoint.
            continue
        anchors.append(
            Anchor(
                "percent",
                m.group(0),
                m.start(),
                m.end(),
                _percent_bps(m.group("num"), m.group("unit")),
            )
        )
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
