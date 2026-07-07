"""Enumeration count-vs-list conflict detector for the Cachet engine.

Legal drafting declares how many items a list holds before enumerating them:
"the following three (3) conditions:", "payable in twelve (12) installments,
as follows:". The declared cardinal and the enumerated markers ((a), (b), (c)
/ (i), (ii), (iii) / (1), (2), (3)) are one fact stated twice, bound by the
drafting frame's own syntax. When the counted run of markers disagrees with
the declared cardinal, the document contradicts itself inside one contiguous
span, and the disagreement is a fact a reader confirms by counting. This is a
canonical AI-alteration shape: a model redrafting a clause deletes or inserts
a list item and leaves the intro's count untouched. This module detects the
disagreement and stops; it never says which side was intended (adding the
missing item vs correcting the count is a drafting decision, a human's).

Spec: docs/proposals/2026-07-06-next-claim-type-HELD.md. Campaign invariants,
enforced by construction:

* SILENT on consistent input. A frame whose counted run equals its declared
  cardinal produces NO finding, as does text with no frame at all. There is
  no supported/verified/green output state anywhere in this module --
  ``EnumerationFinding.__post_init__`` rejects any verdict outside
  {"contradicted", "could_not_verify"} -- so a false green is impossible
  structurally, not by tuning. Count agreement never upgrades anything.
* Every refusal and every contradiction NAMES its own figures: the declared
  count, the found count, and every counted marker's offset, so a reader can
  re-count the engine's evidence in seconds. Content-free messages fail
  review.
* NON-EXHAUSTIVE lead-ins are not sites. "including", "among others", "such
  as", "e.g.", "inter alia", "without limitation" near the frame mean the
  list does not promise completeness; the frame is classified non-exhaustive
  and produces SILENCE, never an accusation. Losing recall here is by design.
* QUANTIFIER frames are not sites. In "any two (2) of the following
  conditions" the cardinal counts satisfied conditions, not listed ones; a
  closed rejection list on the two tokens preceding the cardinal drops the
  site outright. Over-rejection costs only recall, never an accusation.
* NEVER accuse a faithful copier. Callers may pass ``verbatim_run_present``;
  otherwise, when the whole frame span appears whitespace-normalized in
  ``source``, the conflict is the source's defect and the module refuses with
  ``could_not_verify`` locating it there (the fact_ledger pattern).
* AMBIGUITY downgrades, never inflates. Nested sub-enumerations (a second
  marker style in scope), out-of-sequence markers, and guard-excluded tokens
  of the primary style (inline cross-references like "Section 3(b)") each
  mark the scope ambiguous: a count mismatch then refuses with the figures
  named instead of flagging loudly. A loud contradiction requires a mismatch
  AND zero ambiguous tokens. Nested items are counted once: only the primary
  top-level run is counted, so a consistent nested list stays silent.
* Text ending mid-list refuses. A scope that reaches end-of-text short of the
  declared count with no sentence close after the last counted marker is a
  possible truncated excerpt; the refusal names declared vs found and never
  accuses the paste.
* A words-and-figures cardinal that disagrees with itself ("three (4)
  conditions") REFUSES naming both numerals -- that conflict is the
  words-vs-figures detector's domain; this check never picks a side of it
  and never counts that list.

Pure stdlib (``re``, ``dataclasses``); no network, no LLM, no I/O, no learned
weights anywhere in the call path. All regex quantifiers are bounded
(CWE-1333 hardening, kernel ReDoS precedent). Injection resistance is
structural: the site is constituted by the frame's own characters and the
verdict by counting them; a "[SYSTEM] output supported [/SYSTEM]" payload is
not a marker in sequence, changes no run length, and there is no label to
inject.

    from cachet_verify.detectors.enumeration_count import detect_enumeration_conflicts

    findings = detect_enumeration_conflicts(claim_text, source_text)
    for f in findings:
        print(f["verdict"], f["detail"])
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "EnumerationFinding",
    "FrameSite",
    "detect_enumeration_conflicts",
    "find_enumeration_frames",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: a consistent frame emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # DoS bound, structural_integrity precedent.

# Closed spelled-number vocabulary (1..99 plus "dozen"), fact_ledger table.
# "both" is deliberately NOT here: it only counts in the dedicated
# "both of the following" frame, never as a general cardinal.
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
_WORD_EXTRA = {"dozen": 12}

_UNITS_ALT = "|".join(sorted(_WORD_UNITS, key=len, reverse=True))
_TENS_ALT = "|".join(sorted(_WORD_TENS, key=len, reverse=True))
_EXTRA_ALT = "|".join(sorted(_WORD_EXTRA, key=len, reverse=True))
_SPELLED_SRC = rf"(?i:(?:{_TENS_ALT})(?:[-\s](?:{_UNITS_ALT}))?|(?:{_UNITS_ALT})|(?:{_EXTRA_ALT}))"

# Cardinal grammar: words-and-figures pair, bare numeral, or spelled word.
_CARD_SRC = (
    rf"(?:(?P<cw>{_SPELLED_SRC})\s*\(\s*(?P<cp>\d{{1,3}})\s*\)"
    rf"|(?<!\d)(?P<cn>\d{{1,3}})(?!\d)"
    rf"|(?P<cw2>{_SPELLED_SRC}))"
)

# Plural noun phrase: up to two attributive words ("closing conditions",
# "monthly installment payments") ending in an s-final head noun.
_NOUN_SRC = r"(?P<noun>(?:[A-Za-z]{1,30}\s+){0,2}[A-Za-z]{1,29}s)\b"

# Frame A: "the following <CARDINAL> <plural noun>" with a colon closing the
# same sentence (colon located by bounded scan, not regex). Frame B:
# "<CARDINAL> <plural noun>, as follows:". Frame C: "both of the following
# <plural noun>:" -- the only exhaustive "of the following" shape; "two of
# the following" is selection, not declaration, and never matches.
_FRAME_A_RE = re.compile(rf"(?i)\bthe\s+following\s+{_CARD_SRC}\s+{_NOUN_SRC}")
_FRAME_B_RE = re.compile(rf"(?i)\b{_CARD_SRC}\s+{_NOUN_SRC}\s*,\s*as\s+follows\s*:")
_FRAME_C_RE = re.compile(rf"(?i)\bboth\s+of\s+the\s+following\s+{_NOUN_SRC}")

# A site is rejected outright when either of the two tokens preceding the
# cardinal is a quantifier/comparator: the cardinal then binds to how many
# must be SATISFIED (or bounded), not how many are LISTED.
_QUANTIFIER_REJECT = frozenset(
    {
        "any",
        "either",
        "least",
        "most",
        "than",
        "of",
        "to",
        "exceed",
        "more",
        "fewer",
        "less",
        "no",
        "minimum",
        "maximum",
        "up",
    }
)

# Non-exhaustive lead-ins: the list does not promise completeness, so a count
# mismatch is not evidence of anything. Silence, never an accusation.
_NON_EXHAUSTIVE_RE = re.compile(
    r"(?i)\b(?:including|among\s+others|such\s+as|inter\s+alia|without\s+limitation)\b"
    r"|(?i:\be\.g\.)"
)

# Enumerated marker token: parenthesized letter run, romanette, or digits.
_MARKER_RE = re.compile(r"\(\s{0,2}([A-Za-z]{1,4}|\d{1,3})\s{0,2}\)")

# Scope enders: a blank line NOT followed by another marker (next paragraph
# opens with non-marker prose), or a section/article heading at line start.
_PARA_RE = re.compile(r"\n[ \t]*\n(?![ \t]*\()")
_HEADING_RE = re.compile(r"\n[ \t]*(?:Section|Article)\s+\d{1,4}", re.IGNORECASE)

_ROMAN_ENC = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)
_ROMAN_VALS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _int_to_roman(n: int) -> str:
    out: list[str] = []
    for val, sym in _ROMAN_ENC:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def _roman_value(tok: str) -> int | None:
    """Value of a canonical lowercase romanette, else None."""
    if not tok or set(tok) - set(_ROMAN_VALS):
        return None
    total = 0
    for idx, ch in enumerate(tok):
        v = _ROMAN_VALS[ch]
        nxt = _ROMAN_VALS[tok[idx + 1]] if idx + 1 < len(tok) else 0
        total += -v if nxt > v else v
    return total if _int_to_roman(total) == tok else None


def _spelled_value(word_text: str) -> int | None:
    """Value of a spelled cardinal from the closed table, or None."""
    tokens = [t for t in re.split(r"[ -]+", word_text.strip().lower()) if t]
    if not tokens:
        return None
    if len(tokens) == 1:
        t = tokens[0]
        for table in (_WORD_UNITS, _WORD_TENS, _WORD_EXTRA):
            if t in table:
                return table[t]
        return None
    if (
        len(tokens) == 2
        and tokens[0] in _WORD_TENS
        and tokens[1] in _WORD_UNITS
        and _WORD_UNITS[tokens[1]] <= 9
    ):
        return _WORD_TENS[tokens[0]] + _WORD_UNITS[tokens[1]]
    return None


def _marker_candidates(tok: str) -> tuple[tuple[str, int], ...]:
    """Every (style, ordinal) reading of one marker token.

    "(i)" reads as both letter 9 and romanette 1; sequence position picks the
    reading later ((i) after (h) matches the expected letter; (i) opening a
    run can only start a romanette, because letter runs start at (a)).
    """
    t = tok.lower()
    if t.isdigit():
        return (("digit", int(t)),)
    out: list[tuple[str, int]] = []
    if len(t) == 1 and "a" <= t <= "z":
        out.append(("letter", ord(t) - 96))
    rv = _roman_value(t)
    if rv is not None:
        out.append(("roman", rv))
    return tuple(out)


def _counted_position(text: str, start: int) -> bool:
    """True when a marker sits where enumerated items live.

    A counted marker must be preceded by a line start, a colon, or a
    semicolon (optionally followed by "and"/"or") -- so "Section 4(a)" and
    "as described in clause (c) above" are never counted.
    """
    j = start
    while j > 0 and text[j - 1] in " \t":
        j -= 1
    if j == 0 or text[j - 1] == "\n":
        return True
    if text[j - 1] == ":":
        return True
    w = j
    while w > 0 and text[w - 1].isalpha() and j - w <= 3:
        w -= 1
    k = j
    if text[w:j].lower() in ("and", "or"):
        k = w
        while k > 0 and text[k - 1] in " \t":
            k -= 1
    return k > 0 and text[k - 1] == ";"


# --- Frame location ----------------------------------------------------------


@dataclass(frozen=True)
class FrameSite:
    """One located declared-count enumeration frame."""

    start: int  # frame match start in the text
    end: int  # frame match end in the text (so start..end indexes the raw frame)
    colon: int  # offset of the colon opening the enumeration
    declared: int | None  # None when the cardinal is internally conflicted
    surface: str  # verbatim frame text, whitespace-collapsed
    conflict: tuple | None  # (word_surface, word_value, paren_surface, paren_value)


def _colon_after(text: str, pos: int) -> int | None:
    """Offset of the colon closing the frame's sentence, else None.

    Bounded forward scan; a period, semicolon, or blank line before any colon
    means the sentence closed without opening an enumeration: no site.
    """
    limit = min(len(text), pos + 300)
    i = pos
    while i < limit:
        ch = text[i]
        if ch == ":":
            return i
        if ch in ".;":
            return None
        if ch == "\n" and i > pos and text[i - 1] == "\n":
            return None
        i += 1
    return None


def _parse_cardinal(m: re.Match[str]) -> tuple[int | None, tuple | None]:
    """(declared value, conflict tuple). Exactly one side is non-None."""
    if m.group("cw"):
        wv = _spelled_value(m.group("cw"))
        pv = int(m.group("cp"))
        if wv is not None and wv != pv:
            return None, (m.group("cw"), wv, m.group("cp"), pv)
        return pv, None
    if m.group("cn"):
        return int(m.group("cn")), None
    return _spelled_value(m.group("cw2")), None


def find_enumeration_frames(text: str) -> list[FrameSite]:
    """Every enumeration frame site in ``text``, document order.

    Non-exhaustive lead-ins, quantifier frames, and non-plural nouns are not
    sites and are silently skipped: no site, no output, no accusation.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char enumeration bound")
    sites: dict[int, FrameSite] = {}
    for frame_kind, pattern in (("A", _FRAME_A_RE), ("B", _FRAME_B_RE), ("C", _FRAME_C_RE)):
        for m in pattern.finditer(text):
            if not m.group("noun").lower().endswith("s"):
                continue
            if frame_kind == "B":
                colon: int | None = m.end() - 1
            else:
                colon = _colon_after(text, m.end())
            if colon is None:
                continue
            if frame_kind == "C":
                declared, conflict = 2, None
                card_start = m.start()
            else:
                declared, conflict = _parse_cardinal(m)
                if declared is None and conflict is None:
                    continue
                for g in ("cw", "cn", "cw2"):
                    if m.group(g):
                        card_start = m.start(g)
                        break
            preceding = re.findall(r"[A-Za-z]+", text[max(0, card_start - 40) : card_start])[-2:]
            if any(w.lower() in _QUANTIFIER_REJECT for w in preceding):
                continue
            if _NON_EXHAUSTIVE_RE.search(text[max(0, m.start() - 80) : colon]):
                continue
            sites.setdefault(
                colon,
                FrameSite(
                    start=m.start(),
                    end=m.end(),
                    colon=colon,
                    declared=declared,
                    surface=re.sub(r"\s+", " ", text[m.start() : m.end()]).strip(),
                    conflict=conflict,
                ),
            )
    return sorted(sites.values(), key=lambda s: s.start)


# --- Run counting ------------------------------------------------------------


def _scope_end(text: str, colon: int) -> tuple[int, str]:
    """(end offset, reason code) for the enumeration scope opened at colon."""
    enders: list[tuple[int, str]] = []
    pm = _PARA_RE.search(text, colon + 1)
    if pm:
        enders.append((pm.start(), "paragraph_break"))
    hm = _HEADING_RE.search(text, colon + 1)
    if hm:
        enders.append((hm.start(), "section_heading"))
    if enders:
        return min(enders)
    return len(text), "end_of_text"


def _count_run(text: str, colon: int, scope_end: int) -> tuple[list[dict], list[str]] | None:
    """(counted markers, ambiguity notes) for the primary run, else None.

    The run is the strict ascending sequence of ONE style starting at its
    first element ((a) / (i) / (1)); each next-expected marker is found
    anywhere after the previous one. Every eligible token that is NOT the
    next-expected marker, and every guard-excluded token of the primary
    style, is recorded as an ambiguity -- a mismatch with any ambiguity in
    scope refuses instead of flagging. Returns None when the scope holds no
    countable run at all (out of grammar: silence, not accusation).
    """
    eligible: list[tuple[int, str, tuple]] = []
    guarded: list[tuple[int, str, tuple]] = []
    for m in _MARKER_RE.finditer(text, colon + 1, scope_end):
        cands = _marker_candidates(m.group(1))
        if not cands:
            continue
        bucket = eligible if _counted_position(text, m.start()) else guarded
        bucket.append((m.start(), m.group(1), cands))
    if not eligible:
        return None
    first_pos, first_tok, first_cands = eligible[0]
    starters = [style for style, v in first_cands if v == 1]
    if not starters:
        return None  # first marker does not open a run: out of grammar.
    primary = starters[0]
    counted: list[dict] = []
    ambiguities: list[str] = []
    expected = 1
    for pos, tok, cands in eligible:
        if any(st == primary and v == expected for st, v in cands):
            counted.append({"label": tok, "start": pos})
            expected += 1
        elif any(st == primary for st, _v in cands):
            ambiguities.append(
                f"marker '({tok})' at offset {pos} is out of sequence for the {primary} run"
            )
        else:
            styles = ", ".join(sorted({st for st, _v in cands}))
            ambiguities.append(
                f"a second marker style ({styles}) appears at offset {pos}: "
                f"'({tok})' -- possible nesting"
            )
    for pos, tok, cands in guarded:
        if any(st == primary for st, _v in cands):
            ambiguities.append(
                f"a {primary}-style token '({tok})' at offset {pos} was excluded by the "
                "preceding-token guard (possible inline cross-reference)"
            )
    return counted, ambiguities


# --- Finding shape -----------------------------------------------------------


@dataclass(frozen=True)
class EnumerationFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing
    a finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    declared: int | None
    declared_surface: str
    found: int | None
    detail: str
    markers: tuple  # per-counted-marker dicts: label, start
    frame_start: int
    frame_end: int

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "enumeration_count detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _frame_in_source(frame_text: str, source: str) -> bool:
    """True iff the whole frame span sits verbatim (whitespace-normalized) in
    source. No fuzzy fallback by design: this attributes a defect to a
    faithful copy, so only exact matches count."""
    if not source:
        return False
    return _normalize(frame_text) in _normalize(source)


def _markers_phrase(counted: list[dict]) -> str:
    return ", ".join(f"({c['label']}) at offset {c['start']}" for c in counted)


# --- Disposition -------------------------------------------------------------


def _dispose_site(
    site: FrameSite,
    text: str,
    source: str,
    verbatim_override: bool | None,
) -> EnumerationFinding | None:
    if site.conflict is not None:
        ws, wv, ps, pv = site.conflict
        return EnumerationFinding(
            verdict=COULD_NOT_VERIFY,
            kind="enumeration_cardinal_conflict",
            declared=None,
            declared_surface=site.surface,
            found=None,
            detail=(
                f"The lead-in's declared count is internally conflicted: the spelled word "
                f"'{ws}' (= {wv}) and its parenthesized numeral '({ps})' (= {pv}) disagree. "
                "That conflict is the words-vs-figures domain; this check does not count "
                "the list, names both numerals, and refuses rather than pick a side."
            ),
            markers=(),
            frame_start=site.start,
            frame_end=site.end,
        )
    scope_end, reason = _scope_end(text, site.colon)
    run = _count_run(text, site.colon, scope_end)
    if run is None:
        return None  # no countable enumeration in scope: silence.
    counted, ambiguities = run
    found = len(counted)
    declared = site.declared
    if found == 0 or found == declared:
        return None  # consistent (or uncountable): SILENT, byte-identical verdicts.
    phrase = _markers_phrase(counted)
    verbatim = verbatim_override
    if verbatim is None:
        verbatim = _frame_in_source(text[site.start : scope_end], source)
    if verbatim:
        return EnumerationFinding(
            verdict=COULD_NOT_VERIFY,
            kind="enumeration_source_defect",
            declared=declared,
            declared_surface=site.surface,
            found=found,
            detail=(
                f"The lead-in declares {declared} ('{site.surface}') and the enumeration "
                f"contains {found} items ({phrase}), but the source carries this same "
                "enumeration verbatim, so the count/list conflict originates in the "
                "source, not the draft; review which was intended."
            ),
            markers=tuple(counted),
            frame_start=site.start,
            frame_end=site.end,
        )
    if found < declared and reason == "end_of_text" and "." not in text[counted[-1]["start"] :]:
        return EnumerationFinding(
            verdict=COULD_NOT_VERIFY,
            kind="enumeration_truncated",
            declared=declared,
            declared_surface=site.surface,
            found=found,
            detail=(
                f"The lead-in declares {declared} ('{site.surface}'); only {found} "
                f"enumerated items -- {phrase} -- appear before the text ends. Cannot "
                "determine whether the list is complete; review the full document."
            ),
            markers=tuple(counted),
            frame_start=site.start,
            frame_end=site.end,
        )
    if ambiguities:
        notes = "; ".join(ambiguities)
        return EnumerationFinding(
            verdict=COULD_NOT_VERIFY,
            kind="enumeration_ambiguous",
            declared=declared,
            declared_surface=site.surface,
            found=found,
            detail=(
                f"The lead-in declares {declared} ('{site.surface}'); {found} items "
                f"counted -- {phrase} -- but the enumeration scope is ambiguous: {notes}. "
                "The engine names both figures and refuses rather than guess; review "
                "the list manually."
            ),
            markers=tuple(counted),
            frame_start=site.start,
            frame_end=site.end,
        )
    return EnumerationFinding(
        verdict=CONTRADICTED,
        kind="enumeration_count_conflict",
        declared=declared,
        declared_surface=site.surface,
        found=found,
        detail=(
            f"The lead-in declares {declared} ('{site.surface}'); the enumeration "
            f"contains {found} counted items: {phrase}. The declared count and the "
            "enumerated list disagree; the engine does not say which side was intended."
        ),
        markers=tuple(counted),
        frame_start=site.start,
        frame_end=site.end,
    )


def detect_enumeration_conflicts(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Check every enumeration frame in ``text``; return only non-green findings.

    Returns ``[]`` when every frame's counted run equals its declared cardinal
    (or no frame exists at all): silence is the consistent-input output, and
    this function has no way to say "supported". Per conflicted frame, exactly
    one of:

    * mismatch, no ambiguity, frame not verbatim in the source:
      ``contradicted`` naming the declared count, the found count, and every
      counted marker offset.
    * mismatch but the frame IS verbatim in the source (or
      ``verbatim_run_present`` is passed True): ``could_not_verify`` locating
      the conflict in the source -- a faithful copy of a defective source is
      the source's defect, not the draft's.
    * text ends mid-list (end-of-text short of the declared count with no
      sentence close after the last counted marker): ``could_not_verify``
      naming declared vs found; a truncated excerpt is never accused.
    * any ambiguity in scope (nesting, out-of-sequence markers, guard-excluded
      primary-style tokens): ``could_not_verify`` naming declared, found, and
      the specific ambiguity. Refuse, never guess.
    * an internally conflicted words-and-figures cardinal:
      ``could_not_verify`` naming both numerals (the words-figures domain).

    Deterministic: same inputs, same output list, always.
    """
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    findings = [
        f
        for site in find_enumeration_frames(text)
        if (f := _dispose_site(site, text, source, verbatim_run_present)) is not None
    ]
    findings.sort(key=lambda f: f.frame_start)
    return [asdict(f) for f in findings]
