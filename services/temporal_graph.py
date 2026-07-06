"""Whole-document temporal obligation graph for the Cachet engine.

The shipped date/duration detector (``services/date_duration_conflict.py``)
compares two values inside ONE contiguous span: a pair of endpoint dates and a
stated duration written next to each other. This module is the architectural
departure that primitive's arithmetic was built toward: it reads an ENTIRE
document, extracts every dated event and every relative ordering constraint
scattered across separate paragraphs -- "at least 30 days before", "within N
days of", "no earlier than N days after", "before", "after", explicit calendar
dates -- and composes them into a single directed constraint graph whose edges
carry exact day-count bounds. Whether every clause can hold at once is then a
decidable arithmetic question, answered here with certainty and no LLM.

Two impossibilities emerge only at document scale, never inside one span:

* A directed ORDERING CYCLE. Clause 3 puts the Filing before the Hearing,
  clause 7 puts the Hearing before the Filing: no calendar satisfies both, and
  neither clause alone is wrong. This is a pure cycle among ordering edges.
* An ARITHMETIC IMPOSSIBILITY that surfaces only when three or more constraints
  from different paragraphs compose. "Notice at least 30 days before
  Termination; Termination at least 45 days before the Hearing; but Notice is
  fixed at 2026-03-01 and the Hearing at 2026-04-15" -- the two relative bounds
  demand at least 75 days between Notice and Hearing while the two explicit
  dates leave 45. No single clause contradicts another; the three compose to a
  contradiction a calendar confirms.

Both reduce to the same exact computation. Every constraint is encoded as a
difference constraint over integer day variables (an edge ``u -> v`` of weight
``w`` asserting ``day(v) - day(u) <= w``); explicit dates are pinned against a
reference node. The whole clause set is jointly satisfiable if and only if the
constraint graph has NO negative-weight cycle -- the classic Bellman-Ford
result. A negative cycle IS the certificate of impossibility, and the module
extracts it, names every contributing clause with its figures, and quotes each
span. Pure stdlib integer arithmetic; the verdict is arithmetic, not heuristic.

Campaign invariants, enforced by construction:

* SILENT on any jointly-satisfiable document. A schedule that some assignment
  of dates satisfies -- including constraint sets that merely LOOK circular
  ("A within 30 days of B, B within 30 days of C", mutual "on or before" which
  is satisfied by equal dates) -- produces NO finding. There is no
  supported/verified/green output state anywhere in this module;
  ``TemporalFinding.__post_init__`` rejects any verdict outside {"contradicted",
  "could_not_verify"}, so a false green is impossible structurally.
* A contradiction NAMES the full chain. Every contributing clause is described
  with its events and day figures and quoted verbatim; the arithmetic deficit
  (the number of days by which the cycle over-constrains the calendar) is
  stated as a concrete number. Never a content-free shrug.
* An ambiguous date is a REFUSAL, never a guessed accusation. A schedule-
  relevant event whose explicit date has no year, an ambiguous day/month order,
  or an impossible calendar day yields ``could_not_verify`` naming both
  readings; the engine never adopts one reading to manufacture a contradiction.
  A relative day count that spells one number and writes another refuses the
  same way. Business/working/court-day bounds that need a holiday calendar the
  engine lacks refuse rather than accuse.
* A contradiction the SOURCE carries verbatim is the source's defect, not the
  drafter's: when every contributing clause appears whitespace-normalized in
  ``source`` it yields ``could_not_verify`` locating the conflict in the source,
  never ``contradicted``. Callers may force this with ``verbatim_run_present``;
  otherwise a normalized substring match against ``source`` runs, mirroring the
  date/duration sibling.

Event identity is the exact (whitespace-collapsed, leading-"the"-stripped)
surface string, inherited in spirit from the fact ledger's exact-string keys:
"the Closing Date" never silently merges with "Closing", so the module can only
find a cycle a drafter actually wrote by reusing the same defined term. This is
conservative by design -- it refuses to invent a contradiction by guessing that
two differently-named references are the same event.

Date parsing and the spelled-number vocabulary are reused by import from
``services.date_duration_conflict`` (``_parse_date``, ``_DATE_SRC``,
``_spelled_value``, ``_normalize``, ``_run_in_source``); no parsing logic is
duplicated. Pure stdlib (``re``, ``datetime``, ``dataclasses``); no network, no
LLM, no I/O, no learned weights anywhere in the call path. Deterministic: same
input, same output list, always.

    from services.temporal_graph import detect_temporal_contradictions

    findings = detect_temporal_contradictions(document_text)
    for f in findings:
        print(f["verdict"], f["kind"], f["detail"])
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

# Reuse the sibling detector's date parsing, date-shape regex, spelled-number
# vocabulary, and source-guard helpers rather than duplicating any of them.
from services.date_duration_conflict import (
    _DATE_SRC,
    _normalize,
    _parse_date,
    _run_in_source,
    _spelled_value,
)

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "Constraint",
    "TemporalFinding",
    "detect_temporal_contradictions",
    "extract_constraints",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: a satisfiable schedule emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # DoS bound, structural_integrity precedent.
_MAX_CONSTRAINTS = 2_000  # bound on the graph the arithmetic runs over.
_MAX_FINDINGS = 32  # bound on the multiple-cycle extraction loop.

# The reference node explicit calendar dates are pinned against. day(event) is
# an integer day ordinal; day(ANCHOR) is fixed at 0, so an explicit date d gives
# day(event) - day(ANCHOR) == d.toordinal(). No real event can carry this key
# (it is not a valid capitalized/quoted surface), so it cannot collide.
_ANCHOR = "§anchor-reference"


# --- Grammar fragments ------------------------------------------------------
#
# Everything is matched case-sensitively so capitalization stays meaningful for
# event references; the lowercase connective keywords are matched as literals.
# All quantifiers are bounded (CWE-1333 hardening).


def _event_group(name: str) -> str:
    """A capturing group for one event reference: a quoted term, or a Title-Case
    phrase of one to four capitalized words. An optional leading 'the' is
    consumed OUTSIDE the group so it never pollutes the surface."""
    return (
        r"(?:[Tt]he\s+)?"
        rf"(?P<{name}>"
        r"\"[^\"\n]{1,60}\""  # "Defined Term"
        r"|'[^'\n]{1,60}'"  # 'Defined Term'
        r"|[A-Z][A-Za-z]{1,20}(?:\s+[A-Z][A-Za-z]{1,20}){0,3}"  # Title Case run
        r")"
    )


def _days_group(prefix: str) -> str:
    """A capturing group set for a day count: either a spelled number bound to a
    parenthesized numeral ('thirty (30)') or a bare numeral, an optional
    business/working/court/calendar qualifier, then 'day(s)'.

    The spelled word is accepted ONLY in the ``word (numeral)`` adjacency: a
    free-standing ``[A-Za-z]+`` would greedily swallow lowercase filler
    ('must fall within') and shadow the relation's qualifier. Bounding it to the
    paren form keeps the word/figure-conflict check without leaking.
    """
    return (
        r"(?:"
        rf"(?P<{prefix}word>[A-Za-z][A-Za-z-]{{1,20}}?)\s*\((?P<{prefix}num>\d{{1,4}})\)"
        rf"|(?P<{prefix}num2>\d{{1,4}})"
        r")\s+"
        rf"(?:(?P<{prefix}qual>business|working|court|calendar)\s+)?"
        r"days?"
    )


# Lowercase filler between an event reference and the relation keyword ("shall
# occur", "must be given", "is due"). Lowercase-only so it can never swallow the
# next capitalized event reference; bounded to six words. LAZY (``{0,6}?``) so it
# consumes as few words as possible and stops at the FIRST relation keyword --
# otherwise a greedy run would eat a qualifier ("at least") or a multiword
# connective prefix ("on or"), silently downgrading the constraint's semantics.
_GLUE = r"(?:\s+[a-z]+){0,6}?\s+"

# Pattern D: EVENT_A <glue> [qualifier] N days <prep> EVENT_B.
_REL_DAYS = re.compile(
    _event_group("eva")
    + _GLUE
    + r"(?:(?P<qual>at\s+least|no\s+later\s+than|no\s+earlier\s+than|within)\s+)?"
    + _days_group("d")
    + r"\s+(?P<prep>before|after|prior\s+to|following|of)\s+"
    + _event_group("evb")
)

# Pattern R: EVENT_A <glue> <prep> EVENT_B, no day count. Multiword connectives
# are listed before their prefixes so the longest form wins.
_REL_BARE = re.compile(
    _event_group("eva")
    + _GLUE
    + r"(?P<prep>on\s+or\s+before|on\s+or\s+after|no\s+later\s+than|no\s+earlier\s+than"
    r"|prior\s+to|before|after|following)\s+" + _event_group("evb")
)

# The closed anchor-verb list, shared by the dated and yearless anchor patterns
# so arbitrary prose does not mint anchors.
_ANCHOR_VERBS = (
    r"\s+(?:is|are|shall\s+be|will\s+be|shall\s+occur|occurs|shall\s+take\s+place"
    r"|takes\s+place|is\s+scheduled|is\s+set|falls|is\s+due|shall\s+be\s+held"
    r"|shall\s+be\s+completed|shall\s+be\s+made|shall\s+be\s+filed|be\s+held)"
    r"(?:\s+(?:on|for))?\s+"
)

_MONTH_ALT = (
    r"(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December)"
)

# Pattern A: EVENT_A <anchor verb> [on|for] DATE (a fully resolved date).
_ANCHOR_RE = re.compile(_event_group("eva") + _ANCHOR_VERBS + rf"(?P<adate>{_DATE_SRC})")

# Pattern A-noyear: the same anchor context but a month/day with NO year. A date
# with no year cannot be placed on a calendar, so it is a refusal target, never
# an accusation. The lookaheads keep it from stealing a fully-dated anchor.
_ANCHOR_NOYEAR_RE = re.compile(
    _event_group("eva") + _ANCHOR_VERBS + rf"(?P<nydate>{_MONTH_ALT}\s+\d{{1,2}})(?!\s*,?\s*\d)"
)


# --- Event + day-count normalization ----------------------------------------


def _event_identity(surface: str) -> tuple[str, str]:
    """(canonical key, display surface) for an event reference.

    The key lowercases, strips a leading 'the' and surrounding quotes, and
    collapses whitespace; the display keeps the drafter's casing minus quotes.
    Two references bind to one node only when their keys are byte-identical, so
    the module never merges 'the Closing Date' with 'Closing'.
    """
    disp = surface.strip().strip("\"'").strip()
    disp = re.sub(r"\s+", " ", disp)
    disp = re.sub(r"^[Tt]he\s+", "", disp)
    key = disp.lower()
    return key, disp


@dataclass(frozen=True)
class _DayCount:
    value: int  # the numeral that drives the arithmetic
    business: bool  # needs a holiday calendar the engine lacks
    word_conflict: tuple[int, int] | None  # (spelled, numeral) when they differ
    surface: str


def _read_days(word: str | None, num: str, qual: str | None) -> _DayCount:
    value = int(num)
    business = bool(qual) and qual.lower() in {"business", "working", "court"}
    word_conflict = None
    if word:
        wv = _spelled_value(word)
        if wv is not None and wv != value:
            word_conflict = (wv, value)
    surface = (f"{word} " if word else "") + (f"{num} ") + (f"{qual} " if qual else "") + "days"
    return _DayCount(value=value, business=business, word_conflict=word_conflict, surface=surface)


# --- Constraint model -------------------------------------------------------


@dataclass(frozen=True)
class Constraint:
    """One extracted temporal clause and the difference-constraint edges it
    implies. ``edges`` is a tuple of ``(u, v, w)`` triples each asserting
    ``day(v) - day(u) <= w``; a negative-weight cycle across a document's edges
    is the certificate that its clauses cannot all hold."""

    cid: int
    is_anchor: bool
    label: str
    phrase: str  # human description naming events + figures
    span: str  # verbatim clause text
    start: int
    end: int
    a_key: str
    a_disp: str
    b_key: str  # the ANCHOR sentinel for an anchor constraint
    b_disp: str
    days: int | None
    business: bool
    anchor_iso: str  # populated for anchor constraints
    edges: tuple[tuple[str, str, int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _Ambiguity:
    """A schedule-relevant clause the engine refuses on: an ambiguous or invalid
    explicit date, or a relative day count whose spelled and written numbers
    disagree. Always a refusal, never an accusation."""

    kind: str
    event_key: str
    detail: str
    span: str
    start: int
    end: int


def _relation_edges(
    a_key: str, b_key: str, qual: str | None, prep: str, days: int | None
) -> tuple[str, list[tuple[str, str, int]]]:
    """Map (qualifier, preposition, day count) to a human label and the
    difference-constraint edges. Only unambiguous legal forms produce edges;
    genuinely ambiguous phrasings return no edges (the engine stays silent
    rather than guess a bound). Edge convention: ``(u, v, w)`` == ``v - u <= w``.
    """
    p = prep.lower().replace("  ", " ")
    if p == "prior to":
        base = "before"
    elif p == "following":
        base = "after"
    else:
        base = p  # before | after | of

    if days is None:
        # Bare event-vs-event ordering.
        if base == "before":
            return "before", [(b_key, a_key, -1)]  # A < B
        if base == "after":
            return "after", [(a_key, b_key, -1)]  # A > B
        if base == "on or before":
            return "on or before", [(b_key, a_key, 0)]  # A <= B
        if base == "on or after":
            return "on or after", [(a_key, b_key, 0)]  # A >= B
        if base == "no later than":
            return "no later than", [(b_key, a_key, 0)]  # A <= B
        if base == "no earlier than":
            return "no earlier than", [(a_key, b_key, 0)]  # A >= B
        return "", []

    d = days
    if qual is None:
        if base == "before":  # exact: B - A == d
            return f"{d} days before", [(a_key, b_key, d), (b_key, a_key, -d)]
        if base == "after":  # exact: A - B == d
            return f"{d} days after", [(b_key, a_key, d), (a_key, b_key, -d)]
        if base == "of":  # "N days of" reads as within: |A - B| <= d
            return f"within {d} days of", [(b_key, a_key, d), (a_key, b_key, d)]
        return "", []

    q = qual.lower()
    q = re.sub(r"\s+", " ", q)
    if q == "at least":
        if base == "before":  # B - A >= d
            return f"at least {d} days before", [(b_key, a_key, -d)]
        if base == "after":  # A - B >= d
            return f"at least {d} days after", [(a_key, b_key, -d)]
        return "", []
    if q == "no earlier than":
        if base == "after":  # A - B >= d
            return f"no earlier than {d} days after", [(a_key, b_key, -d)]
        return "", []
    if q == "no later than":
        if base == "after":  # A - B <= d
            return f"no later than {d} days after", [(b_key, a_key, d)]
        return "", []
    if q == "within":
        if base == "after":  # 0 <= A - B <= d
            return f"within {d} days after", [(b_key, a_key, d), (a_key, b_key, 0)]
        if base == "of":  # |A - B| <= d
            return f"within {d} days of", [(b_key, a_key, d), (a_key, b_key, d)]
        return "", []
    return "", []


# --- Extraction -------------------------------------------------------------


def extract_constraints(text: str) -> tuple[list[Constraint], list[_Ambiguity]]:
    """Every temporal constraint and refusal-worthy clause in ``text``.

    Returns ``(constraints, ambiguities)`` in document order. Overlapping
    matches from different pattern shapes collapse to the first by start offset
    (day-bearing relations claim their span before bare relations), so no clause
    is counted twice.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char temporal bound")

    claimed: list[tuple[int, int]] = []
    constraints: list[Constraint] = []
    ambiguities: list[_Ambiguity] = []
    cid = 0

    def _overlaps(s: int, e: int) -> bool:
        return any(s < ce and cs < e for cs, ce in claimed)

    # 1. Anchors first: an explicit date pins an event against the reference.
    for m in _ANCHOR_RE.finditer(text):
        s, e = m.start(), m.end()
        if _overlaps(s, e):
            continue
        a_key, a_disp = _event_identity(m.group("eva"))
        dp = _parse_date(m.group("adate"))
        claimed.append((s, e))
        if dp.iso is None:
            if dp.ambiguous is not None:
                r1, r2 = dp.ambiguous
                ambiguities.append(
                    _Ambiguity(
                        kind="temporal_ambiguous_date",
                        event_key=a_key,
                        detail=(
                            f"the {a_disp} is fixed to the locale-ambiguous date "
                            f"'{dp.surface}' (it could mean {r1} or {r2})"
                        ),
                        span=m.group(0),
                        start=s,
                        end=e,
                    )
                )
            else:
                ambiguities.append(
                    _Ambiguity(
                        kind="temporal_unparseable_date",
                        event_key=a_key,
                        detail=(
                            f"the {a_disp} is fixed to '{dp.surface}', which is not a valid "
                            "calendar date"
                        ),
                        span=m.group(0),
                        start=s,
                        end=e,
                    )
                )
            continue
        ordinal = date.fromisoformat(dp.iso).toordinal()
        constraints.append(
            Constraint(
                cid=cid,
                is_anchor=True,
                label="on",
                phrase=f"the {a_disp} is fixed at {dp.iso}",
                span=m.group(0),
                start=s,
                end=e,
                a_key=a_key,
                a_disp=a_disp,
                b_key=_ANCHOR,
                b_disp=_ANCHOR,
                days=None,
                business=False,
                anchor_iso=dp.iso,
                edges=((_ANCHOR, a_key, ordinal), (a_key, _ANCHOR, -ordinal)),
            )
        )
        cid += 1

    # 1b. Yearless anchor dates: a month/day with no year is unplaceable, so it
    #     is recorded as a refusal (surfaced only when schedule-relevant).
    for m in _ANCHOR_NOYEAR_RE.finditer(text):
        s, e = m.start(), m.end()
        if _overlaps(s, e):
            continue
        a_key, a_disp = _event_identity(m.group("eva"))
        claimed.append((s, e))
        ambiguities.append(
            _Ambiguity(
                kind="temporal_ambiguous_date",
                event_key=a_key,
                detail=(
                    f"the {a_disp} is fixed to '{m.group('nydate')}', which carries no year "
                    "and cannot be placed on a calendar"
                ),
                span=m.group(0),
                start=s,
                end=e,
            )
        )

    # 2. Relations with an explicit day count, then bare orderings.
    for pattern, has_days in ((_REL_DAYS, True), (_REL_BARE, False)):
        for m in pattern.finditer(text):
            s, e = m.start(), m.end()
            if _overlaps(s, e):
                continue
            a_key, a_disp = _event_identity(m.group("eva"))
            b_key, b_disp = _event_identity(m.group("evb"))
            if a_key == b_key:
                continue  # a self-referential relation binds nothing.
            qual = m.group("qual") if has_days else None
            prep = m.group("prep")
            dc: _DayCount | None = None
            if has_days:
                num = m.group("dnum") or m.group("dnum2")
                dc = _read_days(m.group("dword"), num, m.group("dqual"))
                if dc.word_conflict is not None:
                    claimed.append((s, e))
                    spelled, written = dc.word_conflict
                    ambiguities.append(
                        _Ambiguity(
                            kind="temporal_ambiguous_count",
                            event_key=a_key,
                            detail=(
                                f"the clause binding the {a_disp} and the {b_disp} spells "
                                f"one day count ({spelled}) but writes another ({written})"
                            ),
                            span=m.group(0),
                            start=s,
                            end=e,
                        )
                    )
                    continue
            days = dc.value if dc is not None else None
            label, edges = _relation_edges(a_key, b_key, qual, prep, days)
            if not edges:
                continue  # ambiguous phrasing: no bound to assert.
            claimed.append((s, e))
            business = bool(dc and dc.business)
            phrase = (
                f"the {a_disp} must fall {label} the {b_disp}"
                if days is not None
                else f"the {a_disp} must fall {label} the {b_disp}"
            )
            constraints.append(
                Constraint(
                    cid=cid,
                    is_anchor=False,
                    label=label,
                    phrase=phrase,
                    span=m.group(0),
                    start=s,
                    end=e,
                    a_key=a_key,
                    a_disp=a_disp,
                    b_key=b_key,
                    b_disp=b_disp,
                    days=days,
                    business=business,
                    anchor_iso="",
                    edges=tuple(edges),
                )
            )
            cid += 1
            if cid > _MAX_CONSTRAINTS:
                raise ValueError(f"document exceeds the {_MAX_CONSTRAINTS}-constraint bound")

    constraints.sort(key=lambda c: c.start)
    ambiguities.sort(key=lambda a: a.start)
    return constraints, ambiguities


# --- Negative-cycle detection (Bellman-Ford) --------------------------------


def _find_negative_cycle(
    nodes: list[str], edges: list[tuple[str, str, int, int]]
) -> list[tuple[str, str, int, int]] | None:
    """One negative-weight cycle as an ordered edge list, or None.

    Edges are ``(u, v, w, cid)`` == ``day(v) - day(u) <= w``. Initializing every
    distance to zero is equivalent to a virtual super-source with 0-weight edges
    to all nodes, so any negative cycle anywhere in the graph is found. Edges are
    relaxed in a fixed sorted order and predecessors recorded per relaxed node,
    so the extracted cycle is deterministic.
    """
    if not edges:
        return None
    ordered_edges = sorted(edges, key=lambda e: (e[0], e[1], e[2], e[3]))
    dist = {n: 0 for n in nodes}
    pred: dict[str, tuple[str, str, int, int]] = {}
    n = len(nodes)
    relaxed_node: str | None = None
    for _ in range(n):
        relaxed_node = None
        for u, v, w, ec in ordered_edges:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                pred[v] = (u, v, w, ec)
                relaxed_node = v
        if relaxed_node is None:
            return None  # a full pass with no relaxation: no negative cycle.
    # ``relaxed_node`` is reachable from a negative cycle; step back n times to
    # land ON the cycle, then walk predecessors until the node repeats.
    cur = relaxed_node
    for _ in range(n):
        cur = pred[cur][0]
    start = cur
    cycle: list[tuple[str, str, int, int]] = []
    guard = 0
    while True:
        e = pred[cur]
        cycle.append(e)
        cur = e[0]
        guard += 1
        if cur == start or guard > n + 1:
            break
    cycle.reverse()
    return cycle


# --- Finding shape ----------------------------------------------------------


@dataclass(frozen=True)
class TemporalFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing a
    finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code path
    in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    detail: str
    deficit_days: int | None
    chain: tuple  # per-clause dicts: event_a, event_b, relation, days, span, ...
    events: tuple  # per-anchor dicts naming the fixed dates in the chain
    span: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "temporal_graph detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _chain_payload(clauses: list[Constraint]) -> tuple:
    return tuple(
        {
            "event_a": c.a_disp,
            "event_b": (None if c.is_anchor else c.b_disp),
            "relation": c.label,
            "days": c.days,
            "anchor_date": (c.anchor_iso or None),
            "business": c.business,
            "span": c.span,
            "start": c.start,
            "end": c.end,
        }
        for c in clauses
    )


def _events_payload(clauses: list[Constraint]) -> tuple:
    return tuple(
        {"event": c.a_disp, "date": c.anchor_iso, "span": c.span} for c in clauses if c.is_anchor
    )


def _cycle_to_finding(
    cycle: list[tuple[str, str, int, int]],
    by_cid: dict[int, Constraint],
    source: str,
    verbatim_override: bool | None,
) -> TemporalFinding:
    # Distinct contributing clauses in cycle order; the deficit is the number of
    # days by which the composed bounds over-constrain the calendar.
    deficit = -sum(w for _, _, w, _ in cycle)
    seen: set[int] = set()
    clauses: list[Constraint] = []
    for _, _, _, ec in cycle:
        if ec not in seen:
            seen.add(ec)
            clauses.append(by_cid[ec])
    has_anchor = any(c.is_anchor for c in clauses)
    business = any(c.business for c in clauses)
    non_anchor = [c for c in clauses if not c.is_anchor]
    start = min(c.start for c in clauses)
    end = max(c.end for c in clauses)
    span = "; ".join(c.span for c in clauses)
    chain_str = "; ".join(f"{c.phrase} ('{c.span}')" for c in clauses)

    if business:
        return TemporalFinding(
            verdict=COULD_NOT_VERIFY,
            kind="temporal_business_days",
            detail=(
                "The document's temporal constraints form an ordering the engine cannot "
                f"resolve without a holiday calendar: {chain_str}. At least one bound counts "
                "business/working/court days, which the engine does not compute; it names "
                "every clause and refuses rather than accuse. Review manually."
            ),
            deficit_days=deficit,
            chain=_chain_payload(clauses),
            events=_events_payload(clauses),
            span=span,
            start=start,
            end=end,
        )

    verbatim = verbatim_override
    if verbatim is None and non_anchor:
        verbatim = all(_run_in_source(c.span, source) for c in non_anchor)
    if verbatim:
        return TemporalFinding(
            verdict=COULD_NOT_VERIFY,
            kind="temporal_source_defect",
            detail=(
                "The document's temporal constraints cannot all hold, but every "
                f"contributing clause is carried verbatim from the source: {chain_str}. The "
                "conflict originates in the source, not the draft; the engine names the "
                "chain and refuses to accuse a faithful copier. Review which clause controls."
            ),
            deficit_days=deficit,
            chain=_chain_payload(clauses),
            events=_events_payload(clauses),
            span=span,
            start=start,
            end=end,
        )

    if has_anchor:
        detail = (
            "The document's temporal constraints cannot all hold. "
            f"{chain_str}. Composed across these clauses the schedule is over-constrained by "
            f"{deficit} day{'' if deficit == 1 else 's'}: no assignment of dates satisfies "
            "every clause at once. The engine reports the conflict verbatim and does not "
            "decide which clause controls."
        )
        kind = "temporal_arithmetic_impossibility"
    else:
        detail = (
            "The document's ordering constraints form a cycle no schedule can satisfy. "
            f"{chain_str}. Following the chain returns to its start, so each event would "
            f"have to precede itself (the ordering is over-constrained by {deficit} "
            f"day{'' if deficit == 1 else 's'}). The engine reports the cycle and does not "
            "decide which clause controls."
        )
        kind = "temporal_ordering_cycle"

    return TemporalFinding(
        verdict=CONTRADICTED,
        kind=kind,
        detail=detail,
        deficit_days=deficit,
        chain=_chain_payload(clauses),
        events=_events_payload(clauses),
        span=span,
        start=start,
        end=end,
    )


# --- Entry point ------------------------------------------------------------


def detect_temporal_contradictions(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Detect temporal-graph contradictions across a whole document.

    Returns ``[]`` when the extracted constraints are jointly satisfiable (or
    when there are none): silence is the satisfiable-input output, and this
    function has no way to say "supported". Otherwise it returns one finding per
    independent contradiction plus one refusal per schedule-relevant ambiguous
    clause, each either ``contradicted`` or ``could_not_verify``:

    * ORDERING CYCLE or ARITHMETIC IMPOSSIBILITY: ``contradicted`` naming the
      full chain, its figures, and the day deficit; ``could_not_verify`` instead
      when a business-day bound blocks computation or when every contributing
      clause is verbatim in ``source`` (a source defect, not the drafter's).
      ``verbatim_run_present`` overrides the source check.
    * AMBIGUOUS DATE / COUNT: ``could_not_verify`` naming both readings; the
      engine never guesses a reading to accuse.

    Deterministic: same inputs, same output list, always.
    """
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")

    constraints, ambiguities = extract_constraints(text)
    by_cid = {c.cid: c for c in constraints}

    # Relative (non-anchor) clauses define which events are schedule-relevant;
    # an ambiguous explicit date on an isolated event is nothing to verify.
    relation_keys: set[str] = set()
    for c in constraints:
        if not c.is_anchor:
            relation_keys.add(c.a_key)
            relation_keys.add(c.b_key)

    findings: list[TemporalFinding] = []

    # Contradictions: strip the edges of a reported cycle's clauses and repeat,
    # so independent conflicts each surface once, bounded against a runaway loop.
    live = list(constraints)
    for _ in range(_MAX_FINDINGS):
        nodes: set[str] = set()
        edges: list[tuple[str, str, int, int]] = []
        for c in live:
            for u, v, w in c.edges:
                nodes.add(u)
                nodes.add(v)
                edges.append((u, v, w, c.cid))
        cycle = _find_negative_cycle(sorted(nodes), edges)
        if cycle is None:
            break
        finding = _cycle_to_finding(cycle, by_cid, source, verbatim_run_present)
        findings.append(finding)
        involved = {ec for _, _, _, ec in cycle}
        live = [c for c in live if c.cid not in involved]

    # Refusals for schedule-relevant ambiguous/invalid clauses.
    for amb in ambiguities:
        if amb.kind == "temporal_ambiguous_count" or amb.event_key in relation_keys:
            findings.append(
                TemporalFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind=amb.kind,
                    detail=(
                        f"The document's schedule cannot be verified because {amb.detail}. "
                        "The engine names the ambiguity and refuses rather than adopt one "
                        "reading to accuse. Review manually."
                    ),
                    deficit_days=None,
                    chain=(),
                    events=(),
                    span=amb.span,
                    start=amb.start,
                    end=amb.end,
                )
            )

    findings.sort(key=lambda f: (f.start, f.end, f.kind))
    return [asdict(f) for f in findings]
