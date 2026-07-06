"""Document-scale fact-ledger contradiction detector for the Cachet engine.

Every existing Cachet detector decides inside a single span. This module reads
the WHOLE document and builds a deterministic ledger of facts a legal draft
states redundantly: an exact defined-term string ("Term", "Purchase Price",
"Notice Period") bound to a figure (duration, money, percent, count) by a
closed set of drafting connectives. When the SAME (term, dimension) key
surfaces in two places with two different normalized values -- Section 1 says
'the "Term" means twenty-four (24) months' and Section 9 says 'during the
36-month Term' -- the document contradicts itself, and the disagreement is a
literal fact a reader can confirm by looking at both places. This module
detects that disagreement and stops. It never says which value controls (the
resolution question is a human's), and it never affirms anything: per ADR-0013
there is no regex path to a green verdict here -- the module only contradicts
on exact-term double-binding or refuses with named figures.

Campaign invariants, enforced by construction:

* SILENT on consistent input. A term whose every binding normalizes to one
  value produces NO finding, as does a document with no bindings at all. There
  is no supported/verified/green output state anywhere in this module --
  ``LedgerFinding.__post_init__`` rejects any verdict outside {"contradicted",
  "could_not_verify"} -- so a false green is impossible structurally, not by
  tuning.
* EXACT string match only. The ledger keys on the exact defined-term string;
  no fuzzy, stemmed, or synonym matching, because that is how false
  accusations happen. "Renewal Term" never feeds the "Term" key: quoted
  patterns require the quotes to hug the exact string, and unquoted usage
  sites are guarded so a term occurrence preceded or followed by a capitalized
  word (part of a longer defined name) never binds.
* DIMENSION-COMPARABLE keys only. Durations normalize within convertible
  units (years x12 -> months; weeks x7 -> days) but months and days are
  distinct dimensions: "24 months" vs "730 days" is never compared for
  contradiction, because no deterministic conversion exists. A term bound to
  durations in BOTH families refuses with ``could_not_verify`` naming both
  figures ("30 days" is not provably "1 month") -- never ``contradicted``,
  never a guess. A term reused across unrelated dimensions (a duration here,
  a money amount there) stays silent: those are different facts.
* HEDGES refuse unless both sides share the semantics. Figures hedged with
  'approximately'/'about' are inherently tolerant with no deterministic
  tolerance, so a difference refuses with the figures named. Figures that all
  share one bound-style hedge class ('up to' caps, 'at least' floors) state
  the same fact-form twice and may contradict.
* NEVER accuse a faithful copier. Callers may pass ``verbatim_run_present``;
  otherwise, when every conflicting binding's sentence appears
  whitespace-normalized in ``source``, the conflict is the source's defect and
  the module refuses with ``could_not_verify`` locating it there.
* Every refusal names its own figures. A ``could_not_verify`` carries every
  figure surface, normalized value, and offset it refused over; content-free
  refusals fail review.

Pure stdlib (``re``, ``decimal``, ``dataclasses``); no network, no LLM, no
I/O, no learned weights anywhere in the call path. All regex quantifiers are
bounded (CWE-1333 hardening, kernel ReDoS precedent).

    from services.fact_ledger import detect_fact_contradictions

    findings = detect_fact_contradictions(document_text)
    for f in findings:
        print(f["verdict"], f["term"], f["detail"])
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from decimal import Decimal

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "Binding",
    "LedgerFinding",
    "build_fact_ledger",
    "detect_fact_contradictions",
    "extract_bindings",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: a consistent ledger emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # DoS bound, structural_integrity precedent.

# Closed spelled-number vocabulary (1..99), same table as the date-interval
# detector. A spelled word is trusted alone only when no numeral accompanies
# it; when a word and its parenthesized numeral disagree, the figure is
# internally conflicted (the words-figures detector's domain) and this module
# does not bind it at all.
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

_UNITS_ALT = "|".join(sorted(_WORD_UNITS, key=len, reverse=True))
_TENS_ALT = "|".join(sorted(_WORD_TENS, key=len, reverse=True))
_SPELLED_SRC = rf"(?i:(?:{_TENS_ALT})(?:[-\s](?:{_UNITS_ALT}))?|(?:{_UNITS_ALT}))"

# Hedge vocabulary. 'approx' figures are tolerant with no deterministic
# tolerance; 'cap'/'floor' figures state a bound and are comparable when both
# sides share the class.
_HEDGE_CLASSES = {
    "approximately": "approx",
    "about": "approx",
    "roughly": "approx",
    "up to": "cap",
    "no more than": "cap",
    "not more than": "cap",
    "at most": "cap",
    "at least": "floor",
    "no less than": "floor",
    "not less than": "floor",
}
_HEDGE_SRC = (
    r"(?i:approximately|about|roughly|up\s+to|no\s+more\s+than|not\s+more\s+than"
    r"|at\s+most|at\s+least|no\s+less\s+than|not\s+less\s+than)"
)

# --- Figure grammar ----------------------------------------------------------
#
# Each figure shape is anchored so partial-digit captures are impossible: a
# money amount may not be followed by more digits, a bare numeral may not sit
# inside a longer digit run. All quantifiers are bounded.

_MONEY_SRC = (
    r"(?:\$|(?i:USD)\s?)\s?"
    r"(?P<mamt>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,12}(?:\.\d{1,2})?)(?!,?\d)(?!\.\d)"
)

_PCT_SRC = r"(?<![\d.])(?P<pval>\d{1,3}(?:\.\d{1,4})?)\s?(?:%|(?i:percent|per\s+cent)(?![A-Za-z]))"

_DUR_SRC = (
    rf"(?:(?P<dword>{_SPELLED_SRC})\s*\(\s*(?P<dparen>\d{{1,4}})\s*\)"
    rf"|(?<!\d)(?P<dnum>\d{{1,4}})(?!\d)"
    rf"|(?P<dword2>{_SPELLED_SRC}))"
    r"[\s-]+(?P<dunit>(?i:day|week|month|year))s?(?![A-Za-z])"
)

_COUNT_SRC = (
    rf"(?:(?P<cword>{_SPELLED_SRC})\s*\(\s*(?P<cparen>\d{{1,4}})\s*\)"
    rf"|(?<!\d)(?P<cnum>\d{{1,4}})(?!\d)"
    rf"|(?P<cword2>{_SPELLED_SRC}))"
    r"\s+(?P<cnoun>[A-Za-z]+)(?![A-Za-z])"
)

# Nouns that must never key a count dimension: time/money units belong to the
# duration and money shapes, and qualifier words are not countable things.
_COUNT_NOUN_BLOCKLIST = frozenset(
    {
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "dollar",
        "dollars",
        "cent",
        "cents",
        "percent",
        "per",
        "business",
        "working",
        "trading",
        "calendar",
        "monthly",
        "annual",
        "of",
        "the",
    }
)

_FIGURE_SRC = (
    rf"(?P<figure>(?:(?P<hedge>{_HEDGE_SRC})\s+)?"
    rf"(?:{_MONEY_SRC}|{_PCT_SRC}|{_DUR_SRC}|{_COUNT_SRC}))"
)

# --- Binding grammar ---------------------------------------------------------
#
# A figure binds to a term ONLY through this closed connective grammar; a
# figure that merely co-occurs in the same sentence is not a binding and
# produces no ledger entry (that is how 'figure near but not bound' stays
# silent).

_DEF_VERBS_SRC = (
    r"(?i:is\s+defined\s+as|shall\s+consist\s+of|shall\s+be\s+composed\s+of"
    r"|shall\s+mean|shall\s+equal|shall\s+be|will\s+be|is\s+composed\s+of"
    r"|consists?\s+of|comprises?|refers\s+to|means|equals|is)"
)
_USE_VERBS_SRC = (
    r"(?i:shall\s+consist\s+of|shall\s+be\s+composed\s+of|is\s+composed\s+of"
    r"|shall\s+be|will\s+be|shall\s+equal|equal\s+to|consists?\s+of|comprises?"
    r"|equals|is|of|at)"
)
# Bounded, closed-vocabulary filler between a connective and its figure ("a
# period of", "an amount equal to", "a rate of"). Lazy so the nearest figure
# binds; digits and '$' are excluded so a figure can never be skipped over.
_FILLER_SRC = (
    r"(?:(?i:a|an|the|of|to|equal|amount|sum|period|term|rate|total|price|fee"
    r"|in|cash|per|annum|annual|aggregate|initial)\s+){0,6}?"
)

# Words that may safely precede an unquoted term occurrence even when
# capitalized (sentence-initial determiners/conjunctions/prepositions). Any
# OTHER capitalized preceding word marks a longer defined name ("Renewal
# Term") and the occurrence never binds.
_SAFE_PRECEDING = frozenset(
    {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "such",
        "said",
        "each",
        "any",
        "every",
        "all",
        "its",
        "their",
        "his",
        "her",
        "our",
        "your",
        "one",
        "no",
        "if",
        "and",
        "or",
        "when",
        "while",
        "before",
        "after",
        "during",
        "under",
        "upon",
        "within",
    }
)

# Quoted capitalized strings are candidate defined terms. A candidate that
# never binds a figure contributes nothing; over-collection is harmless.
_TERM_RE = re.compile(r'"(?P<t>[A-Z][A-Za-z0-9][A-Za-z0-9 \-]{0,58})"')


def _term_patterns(term: str) -> tuple[tuple[re.Pattern[str], bool], ...]:
    """The four binding shapes for one exact term string.

    Returns (pattern, quoted) pairs; unquoted shapes additionally pass the
    capitalized-neighbor guard before binding.
    """
    e = re.escape(term)
    # P1: quoted definition, term first: the "T" means/shall be ... FIGURE.
    p1 = re.compile(
        rf"(?:(?i:the)\s+)?\"(?P<termocc>{e})\"\s+{_DEF_VERBS_SRC}\s+{_FILLER_SRC}{_FIGURE_SRC}"
    )
    # P2: parenthetical definition, figure first: FIGURE ... (the "T").
    p2 = re.compile(
        rf"{_FIGURE_SRC}(?:\s+[a-z]+,?){{0,4}}\s*\(\s*"
        rf"(?:(?i:collectively,?\s+the|each\s+an?|the)\s+)?\"(?P<termocc>{e})\"\s*\)"
    )
    # P3: attributive duration usage: the 36-month T.
    p3 = re.compile(rf"(?P<figure>{_DUR_SRC})\s+(?<![A-Za-z0-9])(?P<termocc>{e})(?![A-Za-z0-9])")
    # P4: usage connective: T of/is/shall be ... FIGURE.
    p4 = re.compile(
        rf"(?<![A-Za-z0-9])(?P<termocc>{e})\s+{_USE_VERBS_SRC}\s+{_FILLER_SRC}{_FIGURE_SRC}"
    )
    return ((p1, True), (p2, True), (p3, False), (p4, False))


# --- Parsing helpers ---------------------------------------------------------


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


def _numeral_value(
    word: str | None, paren: str | None, num: str | None, word2: str | None
) -> int | None:
    """One figure's numeric value, or None when its own numerals disagree.

    A 'thirty (36)' figure is internally conflicted -- that is the
    words-figures detector's domain -- so it never enters the ledger.
    """
    w = word or word2
    wv = _spelled_value(w) if w else None
    if paren is not None:
        pv = int(paren)
        if w and wv is not None and wv != pv:
            return None
        return pv
    if num is not None:
        return int(num)
    return wv


def _parse_figure(gd: dict) -> tuple[str, str] | None:
    """(dimension, canonical value) from a binding match's groupdict."""
    if gd.get("mamt"):
        cents = int(Decimal(gd["mamt"].replace(",", "")) * 100)
        return "money_usd", f"USD {cents // 100}.{cents % 100:02d}"
    if gd.get("pval"):
        return "percent", f"{format(Decimal(gd['pval']).normalize(), 'f')}%"
    if gd.get("dunit"):
        n = _numeral_value(gd.get("dword"), gd.get("dparen"), gd.get("dnum"), gd.get("dword2"))
        if n is None:
            return None
        unit = gd["dunit"].lower()
        if unit in ("month", "year"):
            months = n * 12 if unit == "year" else n
            return "duration_months", f"{months} month"
        days = n * 7 if unit == "week" else n
        return "duration_days", f"{days} day"
    if gd.get("cnoun"):
        n = _numeral_value(gd.get("cword"), gd.get("cparen"), gd.get("cnum"), gd.get("cword2"))
        if n is None:
            return None
        noun = gd["cnoun"].lower()
        if noun in _COUNT_NOUN_BLOCKLIST:
            return None
        singular = (
            noun[:-1] if noun.endswith("s") and not noun.endswith("ss") and len(noun) > 3 else noun
        )
        return f"count_{singular}", f"{n} {singular}"
    return None


_SENTENCE_BOUND = ".;\n"


def _snippet(text: str, start: int, end: int) -> str:
    """The contiguous sentence slice around one binding, collapsed, capped."""
    lo = start
    while lo > 0 and text[lo - 1] not in _SENTENCE_BOUND:
        lo -= 1
    hi = end
    while hi < len(text) and text[hi] not in _SENTENCE_BOUND:
        hi += 1
    if hi < len(text):
        hi += 1
    return re.sub(r"\s+", " ", text[lo:hi]).strip()[:240]


def _neighbor_guard_ok(text: str, start: int, end: int) -> bool:
    """False when an unquoted term occurrence abuts a longer defined name.

    Preceding word capitalized and not a safe determiner/preposition
    ("Renewal Term" for term "Term"), or the next word capitalized ("Term
    Sheet"), means this occurrence is part of a different exact string and
    must not bind. Losing recall here is by design; accusing is not.
    """
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i >= 0 and (text[i].isalnum() or text[i] == "-"):
        j = i
        while j >= 0 and (text[j].isalnum() or text[j] == "-"):
            j -= 1
        word = text[j + 1 : i + 1]
        if word and word[0].isupper() and word.lower() not in _SAFE_PRECEDING:
            return False
    k = end
    while k < len(text) and text[k] in " \t":
        k += 1
    if k < len(text) and text[k].isupper():
        return False
    return True


# --- Ledger construction -----------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """One (exact term, dimension, figure) binding located in the document."""

    term: str
    dimension: str  # duration_months | duration_days | money_usd | percent | count_<noun>
    value: str  # canonical normalized value, e.g. "24 month", "USD 500000.00"
    surface: str  # verbatim figure text, hedge included when present
    hedge: str | None  # approx | cap | floor | None
    start: int  # figure character offsets in the document
    end: int
    snippet: str


def _classify_hedge(hedge_text: str | None) -> str | None:
    if not hedge_text:
        return None
    return _HEDGE_CLASSES[re.sub(r"\s+", " ", hedge_text.strip().lower())]


def _binding_from_match(m: re.Match[str], term: str, text: str) -> Binding | None:
    gd = m.groupdict()
    parsed = _parse_figure(gd)
    if parsed is None:
        return None
    dimension, value = parsed
    fig_start, fig_end = m.span("figure")
    return Binding(
        term=term,
        dimension=dimension,
        value=value,
        surface=m.group("figure").strip(),
        hedge=_classify_hedge(gd.get("hedge")),
        start=fig_start,
        end=fig_end,
        snippet=_snippet(text, fig_start, fig_end),
    )


def _collect_defined_terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in _TERM_RE.finditer(text):
        seen.setdefault(m.group("t").strip(), None)
    return list(seen)


def extract_bindings(text: str, *, extra_terms: Iterable[str] = ()) -> list[Binding]:
    """Every (term, dimension, figure) binding in ``text``, document order.

    Longer terms claim their occurrences first, so an occurrence inside a
    longer defined name ("Renewal Term") is never re-bound by a shorter one
    ("Term"). Exact string match only.

    ``extra_terms`` additively widens the candidate defined-term list with
    exact strings defined elsewhere (e.g. quoted in a sibling document, for
    the cross-document detector). Each extra term must satisfy the same shape
    rule as quoted collection; non-conforming strings are ignored, so the
    widening can never loosen the exact-match guarantee. The default ``()``
    preserves prior behavior exactly.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char fact-ledger bound")
    candidates: dict[str, None] = {}
    for t in _collect_defined_terms(text):
        candidates.setdefault(t, None)
    for t in extra_terms:
        if isinstance(t, str) and _TERM_RE.fullmatch(f'"{t}"'):
            candidates.setdefault(t, None)
    bindings: dict[tuple[str, str, int], Binding] = {}
    claimed: list[tuple[int, int]] = []
    for term in sorted(candidates, key=lambda t: (-len(t), t)):
        for pattern, quoted in _term_patterns(term):
            for m in pattern.finditer(text):
                occ_start, occ_end = m.span("termocc")
                if any(occ_start < ce and cs < occ_end for cs, ce in claimed):
                    continue  # occurrence already bound under a longer term
                if not quoted and not _neighbor_guard_ok(text, occ_start, occ_end):
                    continue
                b = _binding_from_match(m, term, text)
                if b is None:
                    continue
                claimed.append((occ_start, occ_end))
                bindings.setdefault((b.term, b.dimension, b.start), b)
    return sorted(bindings.values(), key=lambda b: b.start)


def build_fact_ledger(
    text: str, *, extra_terms: Iterable[str] = ()
) -> dict[tuple[str, str], list[Binding]]:
    """Bindings grouped by (exact term string, dimension) -- the fact ledger."""
    ledger: dict[tuple[str, str], list[Binding]] = {}
    for b in extract_bindings(text, extra_terms=extra_terms):
        ledger.setdefault((b.term, b.dimension), []).append(b)
    return ledger


# --- Finding shape -----------------------------------------------------------


@dataclass(frozen=True)
class LedgerFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing
    a finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    term: str
    dimension: str
    detail: str
    figures: tuple  # per-figure dicts: surface, normalized, hedge, start, end, snippet

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "fact_ledger detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _figure_payloads(bindings: list[Binding]) -> tuple:
    return tuple(
        {
            "surface": b.surface,
            "normalized": b.value,
            "hedge": b.hedge,
            "start": b.start,
            "end": b.end,
            "snippet": b.snippet,
        }
        for b in bindings
    )


def _distinct_values(bindings: list[Binding]) -> list[str]:
    seen: dict[str, None] = {}
    for b in bindings:
        seen.setdefault(b.value, None)
    return list(seen)


def _dim_label(dimension: str) -> str:
    if dimension == "duration_months":
        return "duration (calendar months)"
    if dimension == "duration_days":
        return "duration (calendar days)"
    if dimension == "money_usd":
        return "money (USD)"
    if dimension == "percent":
        return "percentage"
    if dimension.startswith("count_"):
        return f"count of {dimension[len('count_') :]}s"
    return dimension


def _figure_phrase(bindings: list[Binding]) -> str:
    return "; ".join(f"'{b.surface}' (= {b.value}) at offset {b.start}" for b in bindings)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _all_snippets_in_source(bindings: list[Binding], source: str) -> bool:
    """True iff every conflicting binding's sentence sits verbatim in source.

    No fuzzy fallback by design: this attributes a defect to a faithful copy,
    so only exact (whitespace-normalized) matches count.
    """
    if not source:
        return False
    norm_source = _normalize(source)
    return all(_normalize(b.snippet) in norm_source for b in bindings)


# --- Disposition -------------------------------------------------------------


def detect_fact_contradictions(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Check the document's fact ledger; return only non-green findings.

    Returns ``[]`` when every (term, dimension) key carries one normalized
    value (or no key exists at all): silence is the consistent-input output,
    and this function has no way to say "supported". Per double-bound key,
    exactly one of:

    * two or more distinct unhedged values: ``contradicted`` naming every
      figure verbatim with offsets and sentence snippets -- unless the source
      carries the same conflicting sentences verbatim (or
      ``verbatim_run_present`` is passed True), in which case
      ``could_not_verify`` locating the defect in the source. The engine
      never accuses a drafter who faithfully copied a defective source.
    * distinct values that all share one bound-style hedge class ('up to'
      caps, 'at least' floors): the same fact-form stated twice ->
      ``contradicted`` (same source carve-out applies).
    * distinct values involving 'approximately'-class or mixed hedging:
      ``could_not_verify`` naming every figure; hedge tolerance is not
      deterministically computable, so the engine refuses rather than guess.

    Additionally, a term bound to durations in BOTH the day family and the
    month family (e.g. "30 days" here, "one (1) month" there) refuses with
    ``could_not_verify`` naming every duration figure: calendar days and
    calendar months have no deterministic conversion, so equality is not
    provable and the engine will not guess in either direction.

    A term reused across unrelated dimensions, a figure not bound by the
    connective grammar, or a figure whose own numerals disagree never enters
    a comparison at all. Deterministic: same inputs, same output list, always.
    """
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    findings: list[tuple[int, str, LedgerFinding]] = []
    ledger = build_fact_ledger(text)
    for (term, dimension), group in ledger.items():
        finding = _dispose_group(term, dimension, group, source, verbatim_run_present)
        if finding is not None:
            findings.append((min(b.start for b in group), dimension, finding))
    for anchor, finding in _incommensurable_duration_findings(ledger):
        findings.append((anchor, finding.dimension, finding))
    findings.sort(key=lambda kv: (kv[0], kv[1], kv[2].term))
    return [asdict(f) for _, _, f in findings]


def _incommensurable_duration_findings(
    ledger: dict[tuple[str, str], list[Binding]],
) -> list[tuple[int, LedgerFinding]]:
    """One refusal per term bound in BOTH duration families. Never contradicted:
    days<->months has no deterministic conversion, so a difference here is not
    provable and equality is not provable either."""
    out: list[tuple[int, LedgerFinding]] = []
    terms = sorted(
        {t for (t, dim) in ledger if dim == "duration_days"}
        & {t for (t, dim) in ledger if dim == "duration_months"}
    )
    for term in terms:
        both = sorted(
            ledger[(term, "duration_days")] + ledger[(term, "duration_months")],
            key=lambda b: b.start,
        )
        out.append(
            (
                both[0].start,
                LedgerFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="fact_ledger_incommensurable_units",
                    term=term,
                    dimension="duration_days+duration_months",
                    detail=(
                        f'The defined term "{term}" is bound to durations in '
                        f"incommensurable units: {_figure_phrase(both)}. Calendar days "
                        "and calendar months have no deterministic conversion, so the "
                        "engine cannot prove these figures equal or unequal; it names "
                        "both and refuses rather than guess. Review manually."
                    ),
                    figures=_figure_payloads(both),
                ),
            )
        )
    return out


def _dispose_group(
    term: str,
    dimension: str,
    group: list[Binding],
    source: str,
    verbatim_override: bool | None,
) -> LedgerFinding | None:
    ordered = sorted(group, key=lambda b: b.start)
    if len(_distinct_values(ordered)) < 2:
        return None  # one value however many times: consistent, SILENT.

    label = _dim_label(dimension)
    unhedged = [b for b in ordered if b.hedge is None]
    hedge_classes = {b.hedge for b in ordered}

    if len(_distinct_values(unhedged)) >= 2:
        relevant = unhedged
        hedge_note = ""
    elif hedge_classes == {"cap"} or hedge_classes == {"floor"}:
        relevant = ordered
        bound_word = (
            "upper-bound ('up to')" if hedge_classes == {"cap"} else ("lower-bound ('at least')")
        )
        hedge_note = f" Every figure shares the same {bound_word} hedge semantics."
    else:
        # 'approximately'-class or mixed hedging: no deterministic comparison
        # exists. Refuse, naming every figure this key carries.
        return LedgerFinding(
            verdict=COULD_NOT_VERIFY,
            kind="fact_ledger_hedged_figures",
            term=term,
            dimension=dimension,
            detail=(
                f'The defined term "{term}" is bound to differing {label} figures that are '
                f"hedged: {_figure_phrase(ordered)}. Hedged figures without shared bound "
                "semantics cannot be compared deterministically; the engine names the figures "
                "and refuses rather than guess. Review manually."
            ),
            figures=_figure_payloads(ordered),
        )

    values = _distinct_values(relevant)
    verbatim = verbatim_override
    if verbatim is None:
        verbatim = _all_snippets_in_source(relevant, source)
    if verbatim:
        return LedgerFinding(
            verdict=COULD_NOT_VERIFY,
            kind="fact_ledger_source_defect",
            term=term,
            dimension=dimension,
            detail=(
                f'The defined term "{term}" is bound to {len(values)} different {label} '
                f"values: {_figure_phrase(relevant)}. The source carries these same "
                "conflicting passages verbatim, so the conflict originates in the source, "
                "not the draft; review which value was intended."
            ),
            figures=_figure_payloads(relevant),
        )
    return LedgerFinding(
        verdict=CONTRADICTED,
        kind="fact_ledger_conflict",
        term=term,
        dimension=dimension,
        detail=(
            f'The document binds the defined term "{term}" to {len(values)} different '
            f"{label} values: {_figure_phrase(relevant)}. The same fact surfaces in "
            "two places with two different figures; this document states one fact two "
            f"ways.{hedge_note} The engine does not decide which value controls."
        ),
        figures=_figure_payloads(relevant),
    )
