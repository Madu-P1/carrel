"""Date-interval arithmetic consistency detector for the Cachet engine.

Legal drafting states a time period redundantly: endpoint dates and a duration
are one fact written twice, bound by a fixed drafting frame -- "from January 1,
2025 to June 30, 2025, a period of nine (9) months" or "commencing on January
1, 2026 and ending on December 31, 2026 (a period of two (2) years)". When the
calendar arithmetic between the two endpoint dates matches the stated duration
under NO recognized counting convention, the document contradicts itself inside
one contiguous span, and the disagreement is a literal fact a reader can confirm
with a calendar. This module detects that disagreement and stops. It never says
which value controls (the resolution question, like UCC words-vs-figures, is a
human's). Design follows docs/proposals/2026-07-06-held-proposal-r13-new-domain.

Campaign invariants, enforced by construction:

* SILENT on consistent input. A frame whose dates and duration agree under any
  recognized convention (inclusive vs exclusive end date, calendar-month vs day
  counting, day-before-anniversary) produces NO finding. There is no
  supported/verified/green output state anywhere in this module --
  ``IntervalFinding.__post_init__`` rejects any verdict outside {"contradicted",
  "could_not_verify"} -- so a false green is impossible structurally, not by
  tuning.
* NEVER false-accuse. A finding of ``contradicted`` requires a mismatch that NO
  counting convention explains; anything within a near-boundary band (one day of
  a day/week tolerance, three days of a month/year corresponding date) refuses
  with ``could_not_verify`` rather than accuse across a convention the engine
  does not know.
* Every refusal names its own figures. A ``could_not_verify`` names exactly what
  is missing or ambiguous (the ambiguous surface and both readings, the business
  qualifier and the calendar-day span, the conflicting duration numerals), never
  a content-free shrug.
* A conflicted frame the SOURCE carries verbatim is the source's defect, not the
  drafter's: it yields ``could_not_verify`` locating the conflict in the source,
  never ``contradicted``. Callers may pass an explicit ``verbatim_run_present``
  flag; otherwise the check runs a whitespace-normalized substring match against
  ``source``.

Pure stdlib (``re``, ``datetime``, ``calendar``); no network, no LLM, no I/O,
no learned weights anywhere in the call path. Month/year arithmetic is exact
calendar arithmetic with month-end clamping (``calendar.monthrange``), not a
30-day approximation.

    from services.date_duration_conflict import detect_date_duration_conflicts

    findings = detect_date_duration_conflicts(clause_text)
    for f in findings:
        print(f["verdict"], f["computed_span"], f["detail"])
"""

from __future__ import annotations

import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "FrameSite",
    "IntervalFinding",
    "detect_date_duration_conflicts",
    "find_interval_frames",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: a consistent frame emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # DoS bound, structural_integrity precedent.

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Closed spelled-number vocabulary for the duration numeral (1..99), enough for
# every real "N (numeral) unit" drafting form. A spelled word is used ONLY to
# detect a word/figure conflict inside the duration; the numeral drives the
# arithmetic. Anything outside this table leaves the word value None and the
# numeral is trusted alone.
_WORD_UNITS = {
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
}
_WORD_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

# --- Frame grammar ----------------------------------------------------------
#
# A frame is one of a small closed set of drafting shapes binding two dates and
# one duration by nothing but the frame's own fixed connective words. All
# quantifiers are bounded (CWE-1333 hardening). A duration or date outside a
# frame is not a site and produces no output.

# The existing engine date shapes (ISO, "Month D, YYYY", numeric N/N/YYYY). No
# capturing groups inside so the fragment can be wrapped by the frame's own
# named groups.
_DATE_SRC = (
    r"(?:\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+\d{1,2},\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4})"
)

# One duration: optional spelled word, a numeral (bare or parenthesized), an
# optional business-day qualifier, and a calendar unit. Internal named groups
# are unique so the fragment can appear once per compiled frame.
_DURATION_SRC = (
    r"(?P<dword>[A-Za-z]+(?:[- ][A-Za-z]+)?\s+)?"
    r"(?:\((?P<dparen>\d{1,4})\)|(?P<dnum>\d{1,4}))\s+"
    r"(?:(?P<dqual>business|working|trading)\s+)?"
    r"(?P<dunit>day|week|month|year)s?\b"
)


def _wrap(name: str) -> str:
    return rf"(?P<{name}>{_DATE_SRC})"


def _duration_group() -> str:
    return rf"(?P<duration>{_DURATION_SRC})"


# Frame A1: endpoints then a parenthetical duration adjacent to DATE2.
_FRAME_A1 = re.compile(
    r"(?:from|commenc(?:ing|es)(?:\s+on)?|beginning\s+on|begins\s+on)\s+"
    + _wrap("date1")
    + r"\s+(?:to|through|until|and\s+(?:ending|ends|expiring|expires)(?:\s+on)?)\s+"
    + _wrap("date2")
    + r"\s*\(\s*(?:a\s+period\s+of\s+)?"
    + _duration_group()
    + r"\s*\)",
    re.IGNORECASE,
)

# Frame A2: endpoints then a trailing "a period/term of DURATION" prose form
# (no parentheses), e.g. "from D1 to D2, a period of nine (9) months".
_FRAME_A2 = re.compile(
    r"(?:from|commenc(?:ing|es)(?:\s+on)?|beginning\s+on|begins\s+on)\s+"
    + _wrap("date1")
    + r"\s+(?:to|through|until|and\s+(?:ending|ends|expiring|expires)(?:\s+on)?)\s+"
    + _wrap("date2")
    + r"\s*,?\s+(?:for\s+)?a\s+(?:period|term)\s+of\s+"
    + _duration_group(),
    re.IGNORECASE,
)

# Frame B: duration then endpoints, e.g. "a period of thirty (30) days
# commencing D1 and ending D2".
_FRAME_B = re.compile(
    r"a\s+(?:period|term)\s+of\s+"
    + _duration_group()
    + r"\s*,?\s+(?:commenc(?:ing|es)|beginning|begins)(?:\s+on)?\s+"
    + _wrap("date1")
    + r"\s+and\s+(?:ending|ends|expiring|expires|continuing\s+through"
    r"|continuing\s+until)(?:\s+on)?\s+" + _wrap("date2"),
    re.IGNORECASE,
)

_FRAMES = (_FRAME_A1, _FRAME_A2, _FRAME_B)


# --- Parsing helpers --------------------------------------------------------


@dataclass(frozen=True)
class _DateParse:
    iso: str | None  # canonical ISO date, or None when refused
    ambiguous: tuple[str, str] | None  # both readings when locale-ambiguous
    surface: str


def _parse_date(text: str) -> _DateParse:
    """Parse one endpoint surface. iso None + ambiguous set = locale-ambiguous;
    iso None + ambiguous None = unparseable (e.g. an impossible calendar day)."""
    surface = text.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", surface)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        try:
            return _DateParse(date(y, mo, d).isoformat(), None, surface)
        except ValueError:
            return _DateParse(None, None, surface)
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})$", surface)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        if month is None:
            return _DateParse(None, None, surface)
        try:
            return _DateParse(
                date(int(m.group(3)), month, int(m.group(2))).isoformat(), None, surface
            )
        except ValueError:
            return _DateParse(None, None, surface)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", surface)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Genuinely ambiguous: both fields are valid months and differ.
        if a != b and 1 <= a <= 12 and 1 <= b <= 12:
            read_mf = _safe_iso(y, a, b)  # month-first
            read_df = _safe_iso(y, b, a)  # day-first
            if read_mf and read_df:
                return _DateParse(None, (read_mf, read_df), surface)
            return _DateParse(None, None, surface)
        # One field pins the role, or equal fields resolve identically.
        if a > 12:  # a must be the day, b the month
            return _DateParse(_safe_iso(y, b, a), None, surface)
        return _DateParse(_safe_iso(y, a, b), None, surface)
    return _DateParse(None, None, surface)


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _spelled_value(word_text: str) -> int | None:
    """Value of a 1..99 spelled run, or None when outside the closed table."""
    tokens = [t for t in re.split(r"[ -]+", word_text.strip().lower()) if t]
    if not tokens:
        return None
    if len(tokens) == 1:
        t = tokens[0]
        if t in _WORD_UNITS:
            return _WORD_UNITS[t]
        if t in _WORD_TENS:
            return _WORD_TENS[t]
        return None
    if (
        len(tokens) == 2
        and tokens[0] in _WORD_TENS
        and tokens[1] in _WORD_UNITS
        and _WORD_UNITS[tokens[1]] <= 9
    ):
        return _WORD_TENS[tokens[0]] + _WORD_UNITS[tokens[1]]
    return None


@dataclass(frozen=True)
class FrameSite:
    """One located date-range + duration frame, all three anchors parsed."""

    span: str
    start: int
    end: int
    date1: _DateParse
    date2: _DateParse
    duration_surface: str
    stated_value: int  # the numeral driving the arithmetic
    stated_word_value: int | None  # spelled value, when inside the table
    stated_paren_value: int | None  # parenthesized numeral, when present
    unit: str  # day | week | month | year
    business: bool


def find_interval_frames(text: str) -> list[FrameSite]:
    """Locate every interval frame in ``text``, in document order, deduped.

    A frame requires the fixed connective grammar binding two dates and one
    duration; a duration or date anywhere else is not a site. Overlapping
    matches from different frame shapes collapse to the first by start offset.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char interval bound")
    sites: list[FrameSite] = []
    claimed: list[tuple[int, int]] = []
    matches: list[re.Match[str]] = []
    for pattern in _FRAMES:
        matches.extend(pattern.finditer(text))
    matches.sort(key=lambda m: (m.start(), -(m.end() - m.start())))
    for m in matches:
        start, end = m.start(), m.end()
        if any(start < ce and cs < end for cs, ce in claimed):
            continue  # already covered by an earlier frame shape
        claimed.append((start, end))
        word = m.group("dword")
        paren = m.group("dparen")
        num = m.group("dnum")
        word_value = _spelled_value(word) if word else None
        paren_value = int(paren) if paren is not None else None
        stated = paren_value if paren_value is not None else int(num)
        sites.append(
            FrameSite(
                span=m.group(0),
                start=start,
                end=end,
                date1=_parse_date(m.group("date1")),
                date2=_parse_date(m.group("date2")),
                duration_surface=m.group("duration").strip(),
                stated_value=stated,
                stated_word_value=word_value,
                stated_paren_value=paren_value,
                unit=m.group("dunit").lower(),
                business=bool(m.group("dqual")),
            )
        )
    sites.sort(key=lambda s: s.start)
    return sites


# --- Calendar arithmetic ----------------------------------------------------


def _add_months(d: date, months: int) -> date:
    """d shifted by ``months`` calendar months, clamping to month end.

    January 31 + 1 month = February 28 (or 29 in a leap year); leap years are
    handled exactly because the day is clamped to the target month's length.
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _months_breakdown(s: date, e: date) -> tuple[int, int, int]:
    """(full_months, remainder_days, max_convention_months) for s..e, e >= s."""
    m = 0
    while _add_months(s, m + 1) <= e:
        m += 1
    remainder = (e - _add_months(s, m)).days
    max_months = m + (1 if remainder > 0 else 0)
    return m, remainder, max_months


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _span_phrase(s: date, e: date, unit: str) -> str:
    """Human span description naming both endpoints and both conventions."""
    excl = (e - s).days
    if e < s:
        return (
            f"{s.isoformat()} to {e.isoformat()} = a negative span of {excl} days "
            "(the end date precedes the start date)"
        )
    incl = excl + 1
    if unit in ("day", "week"):
        return (
            f"{s.isoformat()} to {e.isoformat()} = {excl} days exclusive "
            f"({incl} counting both endpoints)"
        )
    m, rem, max_m = _months_breakdown(s, e)
    return (
        f"{s.isoformat()} to {e.isoformat()} = {_plural(m, 'month')} {_plural(rem, 'day')} "
        f"({excl} days exclusive; max across conventions: {_plural(max_m, 'month')})"
    )


# --- Finding shape ----------------------------------------------------------


@dataclass(frozen=True)
class IntervalFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing a
    finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    detail: str
    stated_duration: str
    computed_span: str
    span: str
    start: int
    end: int
    start_date: str
    end_date: str

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "date_duration detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _run_in_source(run: str, source: str) -> bool:
    """True iff ``run`` appears as a whitespace-normalized substring of source.

    No fuzzy fallback by design: this attributes a defect to a faithful copy,
    so only an exact (normalized) match counts.
    """
    norm_run = _normalize(run)
    if not norm_run or not source:
        return False
    return norm_run in _normalize(source)


# --- Disposition ------------------------------------------------------------


def detect_date_duration_conflicts(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict[str, object]]:
    """Check every interval frame in ``text``; return only non-green findings.

    Returns ``[]`` when every frame is consistent under a recognized convention
    (or when there is no frame at all): silence is the consistent-input output,
    and this function has no way to say "supported". Per frame, exactly one of:

    * unparseable element (ambiguous/impossible date, business-day unit, a
      word/figure conflict inside the duration): ``could_not_verify`` naming the
      exact figures the frame carries.
    * consistent under a convention: SILENT.
    * near-boundary mismatch (within one day of a day/week tolerance, or three
      days of the month/year corresponding date): ``could_not_verify`` naming
      both computed figures; the engine refuses across a convention it does not
      know rather than accuse.
    * clear mismatch (including a reversed, negative span): ``contradicted`` when
      the frame is NOT verbatim in ``source``; ``could_not_verify`` (source
      defect) when it is. ``verbatim_run_present``, when passed, overrides the
      source check.

    Deterministic: same inputs, same output list, always.
    """
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    findings: list[IntervalFinding] = []
    for site in find_interval_frames(text):
        try:
            finding = _dispose(site, source, verbatim_run_present)
        except (ValueError, OverflowError):
            # A stated duration so large the calendar arithmetic overflows date's year
            # range (e.g. "9999 years") cannot be placed on a calendar. Refuse THIS frame
            # with could_not_verify rather than raise -- so the detector never crashes a
            # caller and never loses the other, computable frames in the same draft.
            finding = _refuse(
                site,
                "date_interval_uncomputable",
                f"The stated interval {site.duration_surface!r} is too large to place on "
                "the calendar; the span cannot be computed.",
                "not computed (interval out of calendar range)",
            )
        if finding is not None:
            findings.append(finding)
    return [asdict(f) for f in findings]


def _refuse(site: FrameSite, kind: str, detail: str, computed_span: str) -> IntervalFinding:
    return IntervalFinding(
        verdict=COULD_NOT_VERIFY,
        kind=kind,
        detail=detail,
        stated_duration=site.duration_surface,
        computed_span=computed_span,
        span=site.span,
        start=site.start,
        end=site.end,
        start_date=site.date1.iso or site.date1.surface,
        end_date=site.date2.iso or site.date2.surface,
    )


def _dispose(
    site: FrameSite, source: str, verbatim_override: bool | None
) -> IntervalFinding | None:
    stated = f"{site.stated_value} {site.unit}{'' if site.stated_value == 1 else 's'}"

    # 1. Word/figure conflict inside the duration itself (the prior proposal's
    #    domain): name both numerals, never adopt one.
    if (
        site.stated_word_value is not None
        and site.stated_paren_value is not None
        and site.stated_word_value != site.stated_paren_value
    ):
        return _refuse(
            site,
            "date_interval_duration_pair_conflict",
            f"The stated interval '{site.duration_surface}' spells one number but "
            f"writes another: the words give {site.stated_word_value} and the numeral "
            f"gives {site.stated_paren_value}. Cannot compute the span until the "
            "duration's own figures agree; review the pair manually.",
            "not computed (duration numerals disagree)",
        )

    # 2. Business/working/trading days need a holiday calendar the engine lacks.
    if site.business:
        span = _calendar_days_phrase(site)
        return _refuse(
            site,
            "date_interval_business_days",
            f"The stated interval '{site.duration_surface}' counts business days, which "
            f"cannot be computed without a holiday calendar; {span}. Review manually.",
            span,
        )

    # 3. Endpoint parse failures (locale-ambiguous or impossible calendar dates).
    for label, dp in (("start", site.date1), ("end", site.date2)):
        if dp.iso is None:
            if dp.ambiguous is not None:
                a, b = dp.ambiguous
                return _refuse(
                    site,
                    "date_interval_ambiguous_endpoint",
                    f"The {label} date '{dp.surface}' is locale-ambiguous (it could mean "
                    f"{a} or {b}); the stated interval is {stated}. Cannot compute the "
                    "span until the date is disambiguated.",
                    f"not computed ({label} endpoint ambiguous: {a} or {b})",
                )
            return _refuse(
                site,
                "date_interval_unparseable_endpoint",
                f"The {label} date '{dp.surface}' is not a valid calendar date; the "
                f"stated interval is {stated}. Cannot compute the span.",
                f"not computed ({label} endpoint invalid: {dp.surface})",
            )

    iso1, iso2 = site.date1.iso, site.date2.iso
    assert iso1 is not None and iso2 is not None  # the loop above refuses on any None iso
    s = date.fromisoformat(iso1)
    e = date.fromisoformat(iso2)
    computed = _span_phrase(s, e, site.unit)

    # 4. Arithmetic under the recognized-conventions tolerance set.
    if e >= s and site.unit in ("day", "week"):
        target = site.stated_value * (7 if site.unit == "week" else 1)
        excl = (e - s).days
        tolerance = {excl, excl + 1}
        if target in tolerance:
            return None  # consistent under exclusive or inclusive counting
        if target in {excl - 1, excl + 2}:  # differs from tolerance by one day
            return _refuse(
                site,
                "date_interval_near_boundary",
                f"The period {computed}; the stated interval is {stated}. The difference "
                "is within one day of a recognized counting convention; review which "
                "convention was intended.",
                computed,
            )
        return _flag_or_source(site, source, verbatim_override, stated, computed, s, e)

    if e >= s:  # month/year units
        months = site.stated_value * (12 if site.unit == "year" else 1)
        corresponding = _add_months(s, months)
        if e in (corresponding, corresponding - timedelta(days=1)):
            return None  # corresponding-date or day-before-anniversary
        delta = abs((e - corresponding).days)
        if delta <= 3:
            return _refuse(
                site,
                "date_interval_near_boundary",
                f"The period {computed}; the stated interval is {stated}, whose "
                f"corresponding date is {corresponding.isoformat()} (the endpoint is "
                f"{delta} day{'' if delta == 1 else 's'} off). Within a few days of a "
                "recognized convention; review which was intended.",
                computed,
            )
        return _flag_or_source(site, source, verbatim_override, stated, computed, s, e)

    # e < s: a reversed, negative span is a clear mismatch under every convention.
    return _flag_or_source(site, source, verbatim_override, stated, computed, s, e)


def _calendar_days_phrase(site: FrameSite) -> str:
    if site.date1.iso and site.date2.iso:
        s = date.fromisoformat(site.date1.iso)
        e = date.fromisoformat(site.date2.iso)
        return f"the endpoints {s.isoformat()} to {e.isoformat()} span {(e - s).days} calendar days"
    return f"the endpoints '{site.date1.surface}' to '{site.date2.surface}' were provided"


def _flag_or_source(
    site: FrameSite,
    source: str,
    verbatim_override: bool | None,
    stated: str,
    computed: str,
    s: date,
    e: date,
) -> IntervalFinding:
    verbatim = verbatim_override
    if verbatim is None:
        verbatim = _run_in_source(site.span, source)
    if verbatim:
        return _refuse(
            site,
            "date_interval_source_defect",
            f"The period {computed}, but the stated interval is {stated}; the source "
            "carries this same frame verbatim. The conflict originates in the source, "
            "not the draft; review which value was intended.",
            computed,
        )
    return IntervalFinding(
        verdict=CONTRADICTED,
        kind="date_interval_conflict",
        detail=(
            f"The period {computed}, but the stated interval is '{site.duration_surface}'. "
            "The endpoint dates and the stated duration disagree under every recognized "
            "counting convention; this document states one period two ways. The engine "
            "does not decide which value controls."
        ),
        stated_duration=site.duration_surface,
        computed_span=computed,
        span=site.span,
        start=site.start,
        end=site.end,
        start_date=s.isoformat(),
        end_date=e.isoformat(),
    )
