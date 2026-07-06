"""Internal cross-reference and defined-term integrity for the Cachet engine.

Every shipped detector adjudicates a NUMERIC fact: two surfaces of one number,
a table footing, a temporal graph over day counts. This module opens a
structurally different certainty domain: whether the document's own internal
skeleton is sound. "Section 4.2 is cited but no Section 4 exists anywhere in
the document" and "'Confidential Information' is defined twice with different
definitions" are truths about the text itself, decidable by exact string and
set arithmetic with no model, no network, and no judgment call.

Four defect classes, each decidable from the document alone:

* DANGLING SECTION REFERENCE. The text cites ``Section N[.M]``, ``Article N``,
  ``Exhibit X`` (also Clause / Schedule / Appendix / Annex) but no heading of
  that family matches. Fires ONLY when the document demonstrably uses that
  numbering family: at least one heading of the SAME family must parse,
  otherwise the reference stays silent (the false-accusation guard -- a
  contract that never headings its exhibits proves nothing by not heading
  Exhibit C). Resolution is prefix-tolerant both ways: a cite of Section 4.2
  is satisfied by a bare ``Section 4`` heading (subsections are often inline,
  not headed), and a cite of Section 4 is satisfied by a ``Section 4.2``
  heading. Only a cite whose entire numbering node is absent is dangling.
* UNDEFINED DEFINED-TERM. A term used in defined-term style -- quoted
  mid-sentence, or a determiner-led Title Case multiword phrase used at least
  twice -- has no definition anywhere in the document. Fires ONLY when the
  document provably drafts with definitions (at least one ``"X" means ...`` /
  ``"X" has the meaning ...`` / ``(the "X")`` definition or a Definitions
  heading), and always as a REFUSAL (``could_not_verify``), never an
  accusation: a definition can exist in a form this parser does not read, so
  "no definition found" is decidable but "never defined" is not.
* CONFLICTING DUPLICATE DEFINITION. The same term is defined twice via the
  ``"X" means ...`` form with textually different bodies. Both definition
  spans are quoted verbatim in the verdict. An identical (whitespace- and
  case-normalized) restatement is NOT a conflict and stays silent.
* DEFINED-BUT-NEVER-USED TERM. A term defined via any of the recognized
  definition forms whose surface never recurs anywhere else in the document
  (searched case-insensitively, so a lowercase reuse counts as a use and
  silences the check). Reported as an INFORMATIONAL refusal
  (``could_not_verify``, kind ``crossref_unused_term``) quoting the
  definition span verbatim: dead definitions are drafting signal, not an
  accusation, and a use may exist in a form the parser does not read. A term
  whose definitions already conflict is not double-reported here.

Campaign invariants, enforced by construction:

* SILENT on clean documents. There is no supported/verified/green output state
  anywhere in this module; ``CrossrefFinding.__post_init__`` rejects any
  verdict outside {"contradicted", "could_not_verify"}, so a false green is
  impossible structurally. A document with resolvable references and coherent
  definitions produces zero findings -- silence, not a green badge.
* EVERY verdict names its own evidence verbatim: the exact reference string
  and the sentence it appears in, the term and its usage spans, or both
  conflicting definition spans.
* A defect carried verbatim from the source is the source's defect, not the
  drafter's: when every evidence span appears whitespace-normalized in
  ``source`` the finding is ``could_not_verify`` locating the defect in the
  source, never ``contradicted``. Callers may force either disposition with
  ``verbatim_run_present``; otherwise the normalized substring check runs,
  mirroring the date/duration and temporal-graph siblings.
* Ambiguity is SILENCE, never a guess. A reference into another document
  ("Section 4.2 of the Prior Agreement", "Exhibit C to the Purchase
  Agreement", "Section 9 thereof") never fires. Plural ranges ("Sections 4.1
  through 4.3"), lowercase "section 4" prose, and single-word capitalized
  terms are all out of scope by design and stay silent.
* A bare dotted-number heading line ("4.2. Indemnity Procedures.") is an
  ANCHOR: it resolves a numeric reference ("Section 4.2") so a drafter who
  headings subsections without the keyword is never falsely accused. It does
  NOT establish that a numbering family is in play -- only a keyworded
  heading proves the family -- so bare list enumerators can only ever
  suppress an accusation, never enable one.

Identity is exact-string, inherited in spirit from the fact ledger: term keys
are whitespace-collapsed case-folded surfaces, so "Confidential Information"
never silently merges with "Confidential Materials", and singular never merges
with plural. Conservative by design.

The whitespace-normalization and source-guard helpers are reused by import
from ``services.date_duration_conflict`` (``_normalize``, ``_run_in_source``);
nothing is duplicated. Pure stdlib (``re``, ``dataclasses``); no network, no
LLM, no I/O, no learned weights anywhere in the call path. Deterministic: same
input, same output list, always.

    from services.crossref_integrity import check_crossref_integrity, detect

    findings = detect(document_text)
    findings = check_crossref_integrity(document_text, {"source": source_text})
    for f in findings:
        print(f["verdict"], f["kind"], f["detail"])
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# Reuse the sibling detectors' normalization and source-guard helpers rather
# than duplicating them.
from services.date_duration_conflict import _normalize, _run_in_source

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "CrossrefFinding",
    "check_crossref_integrity",
    "detect",
    "detect_crossref_defects",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: a clean document emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # DoS bound, structural_integrity precedent.
_MAX_FINDINGS = 64  # bound on the emitted list.
_MAX_EVIDENCE = 5  # occurrences quoted per finding.
_MIN_UNQUOTED_USES = 2  # determiner-led usages needed before a term is flagged.

# --- Numbering grammar --------------------------------------------------------
#
# All quantifiers are bounded (CWE-1333 hardening). Keywords are matched
# case-sensitively in their two drafted forms (Section / SECTION); lowercase
# "section 4" prose is deliberately out of scope.

_NUM_SRC = r"\d{1,3}(?:\.\d{1,3}){0,4}"
_ROMAN_SRC = r"[IVXLC]{1,7}(?![A-Za-z])"
_LETTER_SRC = r"[A-Z](?![A-Za-z])"

_FAMILY_NUM_SRC = {
    "Section": _NUM_SRC,
    "Clause": _NUM_SRC,
    "Article": rf"(?:{_NUM_SRC}|{_ROMAN_SRC})",
    "Exhibit": rf"(?:\d{{1,3}}|{_LETTER_SRC})",
    "Schedule": rf"(?:{_NUM_SRC}|{_LETTER_SRC})",
    "Appendix": rf"(?:\d{{1,3}}|{_LETTER_SRC})",
    "Annex": rf"(?:\d{{1,3}}|{_LETTER_SRC})",
}

_FAMILY_TOKENS = frozenset(
    tok for fam in _FAMILY_NUM_SRC for tok in (fam, fam + "s", fam.upper(), fam.upper() + "S")
)

# A heading is the keyword + number at line start, closed by punctuation or the
# line end. "Section 4.2 of the Prior Agreement ..." at line start is NOT a
# heading (the number runs into prose), so an external cite cannot mint a
# heading and mask danglingness.
_HEADING_RES = {
    fam: re.compile(
        rf"^[ \t]*(?:{fam.upper()}|{fam})\s+({src})(?=\s*[.:–—-]|[ \t\r]*$)",
        re.MULTILINE,
    )
    for fam, src in _FAMILY_NUM_SRC.items()
}

# A bare dotted-number heading: "4.2. Indemnity Procedures." at line start,
# with or without the trailing dot, followed by a capitalized/quoted title or
# nothing. Registers a resolution ANCHOR only (see the module docstring): it
# can silence a would-be dangling accusation but never prove a family is in
# play, so over-matching a list enumerator ("1. The party shall ...") errs
# toward silence, never toward accusation.
_BARE_NUM_HEADING_RE = re.compile(
    rf"^[ \t]*({_NUM_SRC})\.?(?=\s+[\"(A-Z]|\s*$|\s*[:–—-])",
    re.MULTILINE,
)

# A reference is the same shape anywhere in prose. Plural forms ("Sections 4.1
# and 4.3") do not match -- ranges are ambiguous and ambiguity is silence.
_REF_RES = {
    fam: re.compile(rf"\b(?:{fam.upper()}|{fam})\s+({src})(?=[\s.:;,)('–—-]|$)")
    for fam, src in _FAMILY_NUM_SRC.items()
}

# What follows a reference decides whether it points OUTSIDE this document.
# "Section 4.2 of the Prior Agreement", "Exhibit C to the Purchase Agreement",
# "Section 9 thereof" are external and never fire; "Section 4.2 of this
# Agreement" and "Section 9 hereof" are internal. A capitalized word after
# of/to/under/in ("of Exhibit A") also reads as another container and is
# skipped: conservative silence.
_AFTER_EXTERNAL = re.compile(
    r"(?:\s*\([A-Za-z0-9]{1,6}\))*\s+"
    r"(?:thereof\b|(?:of|to|under|in)\s+(?:the\s|that\s|such\s|any\s|said\s|each\s|[A-Z]))"
)

# --- Definition grammar -------------------------------------------------------

_TERM_SRC = r"[A-Z][^\"\n]{0,79}"

# "X" means ... : the definition form whose BODY is comparable, so it is the
# only form duplicate-conflict detection runs over. The body is read to the
# first sentence-ish stop; the truncation is applied identically to every
# definition, so comparison stays apples-to-apples.
_MEANS_DEF_RE = re.compile(rf"\"({_TERM_SRC})\"\s+(?:shall\s+mean|means)\s+([^.;\n]{{1,400}})")

# "X" has the meaning ... : defines the term (a pointer), body not comparable.
_POINTER_DEF_RE = re.compile(rf"\"({_TERM_SRC})\"\s+(?:shall\s+have|has|have)\s+the\s+meaning\b")

# ... (the "X") : parenthetical definition.
_PAREN_DEF_RE = re.compile(
    r"\(\s*(?:(?:individually|collectively|hereinafter)\s*,?\s+)?"
    rf"(?:the|an?|each)?\s*\"({_TERM_SRC})\"\s*\)"
)

# Any quoted capitalized run: a defined-term-style USE when it is not itself a
# definition site.
_QUOTED_USE_RE = re.compile(rf"\"({_TERM_SRC})\"")

# A Definitions heading proves the drafting convention even with no parseable
# individual definition.
_DEFS_HEADING_RE = re.compile(
    r"^[ \t]*(?:(?:SECTION|Section|ARTICLE|Article|CLAUSE|Clause)"
    r"\s+[\dIVXLC.]{1,10}\s*[.:–—-]?\s*)?"
    r"(?:DEFINITIONS|Definitions)\b",
    re.MULTILINE,
)

# Determiner-led Title Case multiword phrase: unquoted defined-term-style use.
# Two-to-four capitalized words; single words ("the Client") are deliberately
# out of scope -- too many proper nouns, and ambiguity is silence.
_CAND_RE = re.compile(
    r"\b(?:[Tt]he|[Aa]ny|[Ss]uch|[Ee]ach|[Aa]ll|[Nn]o)\s+"
    r"((?:[A-Z][A-Za-z]{1,24})(?:\s+[A-Z][A-Za-z]{1,24}){1,3})\b"
)

# "X (as defined in <elsewhere>)" imports the term from another document: that
# term is externally defined and never flagged here.
_AS_DEFINED_RE = re.compile(r"\s*\(as\s+defined\s+in\b")

# Sentence-ish boundary that never splits inside a dotted section number.
_SENT_BOUND = re.compile(r"(?<!\d)[.;!?](?=\s|$)")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


# --- Small helpers ------------------------------------------------------------


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _roman_to_int(s: str) -> int | None:
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return None
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total if total > 0 else None


def _canonical_key(family: str, raw: str) -> tuple | None:
    """Family-internal canonical key for a heading/reference number.

    Dotted numerals become integer tuples so 'Section 4.2' and 'Section 4.20'
    stay distinct; Article roman numerals canonicalize to integers so a cite of
    'Article 4' resolves against an 'ARTICLE IV' heading; attachment letters
    stay single-character tuples. None means unreadable, and unreadable means
    the reference is silently skipped, never guessed at.
    """
    raw = raw.strip()
    parts = raw.split(".")
    if parts and all(p.isdigit() for p in parts):
        return tuple(int(p) for p in parts)
    if family == "Article":
        r = _roman_to_int(raw)
        if r is not None:
            return (r,)
    if len(raw) == 1 and raw.isalpha():
        return (raw.upper(),)
    return None


def _prefix_related(a: tuple, b: tuple) -> bool:
    n = min(len(a), len(b))
    return n > 0 and a[:n] == b[:n]


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence-ish span containing [start, end): the quotable evidence."""
    lo = max(0, start - 300)
    hi = min(len(text), end + 300)
    left = lo
    for m in _SENT_BOUND.finditer(text, lo, start):
        left = m.end()
    left = max(left, text.rfind("\n", lo, start) + 1)
    right = hi
    m = _SENT_BOUND.search(text, end, hi)
    if m is not None:
        right = m.end()
    nl = text.find("\n", end, right)
    if nl != -1:
        right = nl
    return _collapse(text[left:right])


def _overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s < end and start < e for s, e in spans)


def _is_verbatim(spans: list[str], source: str, verbatim_run_present: bool | None) -> bool:
    if verbatim_run_present is not None:
        return verbatim_run_present
    if not source or not spans:
        return False
    return all(_run_in_source(sp, source) for sp in spans)


# --- Finding shape ------------------------------------------------------------


@dataclass(frozen=True)
class CrossrefFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing a
    finding with any verdict outside ``ALLOWED_VERDICTS`` raises, so no code
    path in (or importing) this module can mint a supported state from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str
    subject: str  # the reference string or the term at issue
    detail: str
    evidence: tuple  # per-occurrence dicts: role, span, start, end
    span: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "crossref_integrity detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


# --- Extraction ---------------------------------------------------------------


def _extract_headings(
    text: str,
) -> tuple[
    dict[str, dict[tuple, list[dict]]],
    list[tuple[int, int]],
    list[tuple[int, int]],
    frozenset[tuple],
]:
    """(headings by family by key, heading match spans, heading TITLE spans,
    bare-number anchor keys).

    A title span runs from the heading's line start through the first sentence
    boundary after the number ("Section 2. Obligations."), NOT the whole line:
    a heading often opens a single-line paragraph, and the paragraph's prose
    must stay eligible as defined-term-usage evidence.

    Bare anchor keys are the integer tuples of keyword-less dotted-number
    heading lines ("4.2. Indemnity."). They resolve references only; they
    never put a family in play.
    """
    headings: dict[str, dict[tuple, list[dict]]] = {}
    spans: list[tuple[int, int]] = []
    title_spans: list[tuple[int, int]] = []
    for family, rx in _HEADING_RES.items():
        for m in rx.finditer(text):
            key = _canonical_key(family, m.group(1))
            if key is None:
                continue
            headings.setdefault(family, {}).setdefault(key, []).append(
                {"raw": m.group(1), "start": m.start(), "end": m.end()}
            )
            spans.append((m.start(), m.end()))
            ls = text.rfind("\n", 0, m.start()) + 1
            le = text.find("\n", m.end())
            le = len(text) if le == -1 else le
            tb = _SENT_BOUND.search(text, min(m.end() + 1, le), le)
            title_spans.append((ls, tb.end() if tb is not None else le))
    bare_keys = frozenset(
        key
        for m in _BARE_NUM_HEADING_RE.finditer(text)
        if (key := _canonical_key("Section", m.group(1))) is not None
    )
    return headings, spans, title_spans, bare_keys


def _extract_references(text: str, heading_spans: list[tuple[int, int]]) -> list[dict]:
    refs: list[dict] = []
    for family, rx in _REF_RES.items():
        for m in rx.finditer(text):
            if any(hs <= m.start() < he for hs, he in heading_spans):
                continue  # the heading itself is not a reference.
            if _AFTER_EXTERNAL.match(text, m.end()):
                continue  # points into another document: silence.
            key = _canonical_key(family, m.group(1))
            if key is None:
                continue
            refs.append(
                {
                    "family": family,
                    "key": key,
                    "ref": _collapse(m.group(0)),
                    "start": m.start(),
                    "end": m.end(),
                }
            )
    refs.sort(key=lambda r: (r["start"], r["end"]))
    return refs


def _extract_definitions(
    text: str,
) -> tuple[list[dict], dict[str, str], list[tuple[int, int]], dict[str, list[dict]], bool]:
    """(means-defs with bodies, all defined term keys->display, definition-site
    spans, per-term definition sites, whether the definitions convention is
    provably in play)."""
    means: list[dict] = []
    defined: dict[str, str] = {}
    site_spans: list[tuple[int, int]] = []
    def_sites: dict[str, list[dict]] = {}

    def _site(key: str, m: re.Match) -> None:
        def_sites.setdefault(key, []).append(
            {"span": _collapse(m.group(0)), "start": m.start(), "end": m.end()}
        )
        site_spans.append((m.start(), m.end()))

    for m in _MEANS_DEF_RE.finditer(text):
        disp = _collapse(m.group(1))
        key = _normalize(disp)
        means.append(
            {
                "key": key,
                "disp": disp,
                "body": _normalize(m.group(2)),
                "span": _collapse(m.group(0)),
                "start": m.start(),
                "end": m.end(),
            }
        )
        defined.setdefault(key, disp)
        _site(key, m)
    for rx in (_POINTER_DEF_RE, _PAREN_DEF_RE):
        for m in rx.finditer(text):
            disp = _collapse(m.group(1))
            key = _normalize(disp)
            defined.setdefault(key, disp)
            _site(key, m)
    for sites in def_sites.values():
        sites.sort(key=lambda s: (s["start"], s["end"]))
    convention = bool(defined) or _DEFS_HEADING_RE.search(text) is not None
    return means, defined, site_spans, def_sites, convention


# --- Defect class (a): dangling references ------------------------------------


def _dangling_findings(
    text: str,
    headings: dict[str, dict[tuple, list[dict]]],
    bare_keys: frozenset[tuple],
    refs: list[dict],
    source: str,
    verbatim_run_present: bool | None,
) -> list[CrossrefFinding]:
    findings: list[CrossrefFinding] = []
    seen: set[tuple[str, tuple]] = set()
    for ref in refs:
        family = ref["family"]
        fam_heads = headings.get(family)
        if not fam_heads:
            continue  # family not demonstrably in play: silence.
        if any(_prefix_related(ref["key"], hk) for hk in fam_heads):
            continue  # resolved (exactly, or via a parent/child heading).
        if all(isinstance(p, int) for p in ref["key"]) and any(
            _prefix_related(ref["key"], bk) for bk in bare_keys
        ):
            continue  # resolved by a keyword-less "4.2." heading line.
        ident = (family, ref["key"])
        if ident in seen:
            continue
        seen.add(ident)
        occs = [r for r in refs if r["family"] == family and r["key"] == ref["key"]]
        evidence = tuple(
            {
                "role": "reference",
                "span": _sentence_around(text, o["start"], o["end"]),
                "start": o["start"],
                "end": o["end"],
            }
            for o in occs[:_MAX_EVIDENCE]
        )
        first = evidence[0]["span"]
        labels = sorted({f"{family} {occ['raw']}" for occs_ in fam_heads.values() for occ in occs_})
        head_list = ", ".join(labels)
        verbatim = _is_verbatim([ev["span"] for ev in evidence], source, verbatim_run_present)
        if verbatim:
            findings.append(
                CrossrefFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="crossref_source_defect",
                    subject=ref["ref"],
                    detail=(
                        f'The document cites "{ref["ref"]}" ("{first}") but no matching '
                        f"{family} heading exists (the document's {family} headings are "
                        f"{head_list}); the citing text is carried verbatim from the source. "
                        "The dangling reference originates in the source, not the draft; the "
                        "engine refuses to accuse a faithful copier. Review the source's "
                        "cross-references."
                    ),
                    evidence=evidence,
                    span=first,
                    start=occs[0]["start"],
                    end=occs[-1]["end"],
                )
            )
        else:
            findings.append(
                CrossrefFinding(
                    verdict=CONTRADICTED,
                    kind="crossref_dangling_reference",
                    subject=ref["ref"],
                    detail=(
                        f'The document cites "{ref["ref"]}" ("{first}", offset '
                        f"{occs[0]['start']}) but no {family} matching it exists in the "
                        f"document: its {family} headings are {head_list}. The reference is "
                        "dangling; the engine quotes the citation verbatim and does not guess "
                        "an intended target."
                    ),
                    evidence=evidence,
                    span=first,
                    start=occs[0]["start"],
                    end=occs[-1]["end"],
                )
            )
    return findings


# --- Defect class (b): undefined defined-terms --------------------------------


def _undefined_term_findings(
    text: str,
    defined: dict[str, str],
    site_spans: list[tuple[int, int]],
    convention: bool,
    heading_line_spans: list[tuple[int, int]],
    source: str,
    verbatim_run_present: bool | None,
) -> list[CrossrefFinding]:
    if not convention:
        return []  # the drafting convention is not provably in play: silence.

    usage: dict[str, dict] = {}
    external: set[str] = set()

    def _record(key: str, disp: str, start: int, end: int, quoted: bool) -> None:
        slot = usage.setdefault(key, {"disp": disp, "occs": []})
        slot["occs"].append({"start": start, "end": end, "quoted": quoted})

    for m in _QUOTED_USE_RE.finditer(text):
        if _overlaps_any(m.start(), m.end(), site_spans):
            continue  # the definition site itself is not a use.
        disp = _collapse(m.group(1))
        key = _normalize(disp)
        if _AS_DEFINED_RE.match(text, m.end()):
            external.add(key)
            continue
        _record(key, disp, m.start(), m.end(), quoted=True)

    for m in _CAND_RE.finditer(text):
        if _overlaps_any(m.start(1), m.end(1), heading_line_spans):
            continue  # heading titles are not defined-term uses.
        disp = _collapse(m.group(1))
        if any(tok in _FAMILY_TOKENS for tok in disp.split()):
            continue  # "Section", "Exhibit", ... are numbering, not terms.
        key = _normalize(disp)
        if _AS_DEFINED_RE.match(text, m.end(1)):
            external.add(key)
            continue
        _record(key, disp, m.start(1), m.end(1), quoted=False)

    example = next(iter(defined.values()), None)
    convention_note = (
        f'a document that otherwise defines its terms (e.g. "{example}")'
        if example
        else "a document that carries a Definitions heading"
    )

    findings: list[CrossrefFinding] = []
    for key, slot in usage.items():
        if key in defined or key in external:
            continue
        occs = sorted(slot["occs"], key=lambda o: o["start"])
        quoted_n = sum(1 for o in occs if o["quoted"])
        if quoted_n == 0 and len(occs) < _MIN_UNQUOTED_USES:
            continue  # one bare Title Case phrase proves nothing: silence.
        evidence = tuple(
            {
                "role": "usage",
                "span": _sentence_around(text, o["start"], o["end"]),
                "start": o["start"],
                "end": o["end"],
            }
            for o in occs[:_MAX_EVIDENCE]
        )
        first = evidence[0]["span"]
        disp = slot["disp"]
        n = len(occs)
        verbatim = _is_verbatim([ev["span"] for ev in evidence], source, verbatim_run_present)
        if verbatim:
            detail = (
                f'The term "{disp}" is used in defined-term style ({n} occurrence'
                f'{"" if n == 1 else "s"}, e.g. "{first}") with no definition found, but every '
                "use is carried verbatim from the source: the gap originates in the source, "
                "not the draft. The engine refuses to accuse a faithful copier; review the "
                "source's definitions."
            )
            kind = "crossref_source_defect"
        else:
            detail = (
                f'The term "{disp}" is used in defined-term style ({n} occurrence'
                f'{"" if n == 1 else "s"}, e.g. "{first}") but the engine found no definition '
                f'of "{disp}" in {convention_note}. A definition may exist in a form the '
                "engine does not read, so it refuses to adjudicate the term rather than "
                "accuse; review manually."
            )
            kind = "crossref_undefined_term"
        findings.append(
            CrossrefFinding(
                verdict=COULD_NOT_VERIFY,
                kind=kind,
                subject=disp,
                detail=detail,
                evidence=evidence,
                span=first,
                start=occs[0]["start"],
                end=occs[-1]["end"],
            )
        )
    return findings


# --- Defect class (c): conflicting duplicate definitions -----------------------


def _conflicting_definition_findings(
    means: list[dict], source: str, verbatim_run_present: bool | None
) -> list[CrossrefFinding]:
    by_key: dict[str, list[dict]] = {}
    for d in means:
        by_key.setdefault(d["key"], []).append(d)

    findings: list[CrossrefFinding] = []
    for defs in by_key.values():
        if len(defs) < 2:
            continue
        distinct: list[dict] = []
        seen_bodies: set[str] = set()
        for d in defs:
            if d["body"] not in seen_bodies:
                seen_bodies.add(d["body"])
                distinct.append(d)
        if len(distinct) < 2:
            continue  # an identical restatement is not a conflict: silence.
        disp = defs[0]["disp"]
        quoted = " versus ".join(f'"{d["span"]}"' for d in distinct)
        evidence = tuple(
            {"role": "definition", "span": d["span"], "start": d["start"], "end": d["end"]}
            for d in defs[:_MAX_EVIDENCE]
        )
        verbatim = _is_verbatim([d["span"] for d in distinct], source, verbatim_run_present)
        if verbatim:
            findings.append(
                CrossrefFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="crossref_source_defect",
                    subject=disp,
                    detail=(
                        f'The term "{disp}" is defined {len(defs)} times with textually '
                        f"different definitions ({quoted}), but every definition is carried "
                        "verbatim from the source: the conflict originates in the source, not "
                        "the draft. The engine names both spans and refuses to accuse a "
                        "faithful copier; review which definition controls."
                    ),
                    evidence=evidence,
                    span="; ".join(d["span"] for d in distinct),
                    start=defs[0]["start"],
                    end=defs[-1]["end"],
                )
            )
        else:
            findings.append(
                CrossrefFinding(
                    verdict=CONTRADICTED,
                    kind="crossref_conflicting_definition",
                    subject=disp,
                    detail=(
                        f'The term "{disp}" is defined {len(defs)} times with textually '
                        f"different definitions: {quoted}. Both cannot control; the engine "
                        "quotes each definition verbatim and does not decide which one "
                        "governs."
                    ),
                    evidence=evidence,
                    span="; ".join(d["span"] for d in distinct),
                    start=defs[0]["start"],
                    end=defs[-1]["end"],
                )
            )
    return findings


# --- Defect class (d): defined-but-never-used terms ----------------------------


def _unused_term_findings(
    text: str,
    defined: dict[str, str],
    def_sites: dict[str, list[dict]],
    conflicted_keys: set[str],
) -> list[CrossrefFinding]:
    """Informational refusals for definitions whose term never recurs.

    "Used" is read generously -- ANY case-insensitive recurrence of the term's
    word sequence outside the term's own definition sites counts, including a
    lowercase reuse or a mention inside another term's definition body -- so
    the check errs toward silence. A term already reported as a conflicting
    duplicate is not double-reported here.
    """
    findings: list[CrossrefFinding] = []
    for key, disp in defined.items():
        if key in conflicted_keys:
            continue
        sites = def_sites.get(key)
        if not sites:
            continue
        own_spans = [(s["start"], s["end"]) for s in sites]
        rx = re.compile(
            r"\b" + r"\s+".join(re.escape(w) for w in disp.split()) + r"\b",
            re.IGNORECASE,
        )
        if any(not _overlaps_any(m.start(), m.end(), own_spans) for m in rx.finditer(text)):
            continue  # used somewhere, in any casing: silence.
        evidence = tuple(
            {"role": "definition", "span": s["span"], "start": s["start"], "end": s["end"]}
            for s in sites[:_MAX_EVIDENCE]
        )
        first = evidence[0]["span"]
        findings.append(
            CrossrefFinding(
                verdict=COULD_NOT_VERIFY,
                kind="crossref_unused_term",
                subject=disp,
                detail=(
                    f'The term "{disp}" is defined ("{first}") but the engine finds no use '
                    f'of "{disp}" anywhere else in the document (searched '
                    "case-insensitively). Informational: an unused definition is dead "
                    "weight or a sign its intended uses were dropped in drafting. A use "
                    "may exist in a form the engine does not read, so it refuses to "
                    "adjudicate rather than accuse; review whether the definition or its "
                    "uses are missing."
                ),
                evidence=evidence,
                span=first,
                start=sites[0]["start"],
                end=sites[-1]["end"],
            )
        )
    return findings


# --- Entry point ----------------------------------------------------------------


def detect_crossref_defects(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Detect internal cross-reference and defined-term defects in a document.

    Returns ``[]`` for a structurally coherent document: silence is the clean
    output, and this function has no way to say "supported". Otherwise it
    returns one finding per defect, each either ``contradicted`` or
    ``could_not_verify``:

    * DANGLING REFERENCE: ``contradicted`` quoting the exact citation, its
      sentence, and the family's real headings; fires only when the numbering
      family is demonstrably in play, and never for a reference into another
      document.
    * UNDEFINED DEFINED-TERM: ``could_not_verify`` naming the term and quoting
      its uses; fires only when the definitions convention is provably in play
      and never for a term imported "(as defined in ...)" from elsewhere.
    * CONFLICTING DUPLICATE DEFINITION: ``contradicted`` quoting BOTH
      definition spans verbatim; an identical restatement stays silent.
    * DEFINED-BUT-NEVER-USED TERM: informational ``could_not_verify`` (kind
      ``crossref_unused_term``) quoting the definition span; any
      case-insensitive reuse of the term silences it.
    * Any of the above whose evidence is carried verbatim in ``source`` (or
      when ``verbatim_run_present=True``) becomes ``could_not_verify`` locating
      the defect in the source instead: a faithful copier is never accused.

    Deterministic: same inputs, same output list, always.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char crossref bound")

    headings, heading_spans, heading_line_spans, bare_keys = _extract_headings(text)
    refs = _extract_references(text, heading_spans)
    means, defined, site_spans, def_sites, convention = _extract_definitions(text)

    findings: list[CrossrefFinding] = []
    findings.extend(
        _dangling_findings(text, headings, bare_keys, refs, source, verbatim_run_present)
    )
    findings.extend(
        _undefined_term_findings(
            text,
            defined,
            site_spans,
            convention,
            heading_line_spans,
            source,
            verbatim_run_present,
        )
    )
    conflicts = _conflicting_definition_findings(means, source, verbatim_run_present)
    findings.extend(conflicts)
    findings.extend(
        _unused_term_findings(text, defined, def_sites, {_normalize(f.subject) for f in conflicts})
    )

    findings.sort(key=lambda f: (f.start, f.end, f.kind, f.subject))
    return [asdict(f) for f in findings[:_MAX_FINDINGS]]


def check_crossref_integrity(text: str, context: dict | None = None) -> list[dict]:
    """The mandated engine surface: ``context`` carries the optional knobs.

    Recognized context keys, both optional:

    * ``source``: the source document; evidence carried verbatim from it
      refuses as a source defect instead of accusing the drafter.
    * ``verbatim_run_present``: force the source-defect disposition (``True``)
      or the accusation disposition (``False``) regardless of the substring
      check; ``None``/absent runs the check.

    Everything else about the verdict surface is ``detect_crossref_defects``:
    silence on coherent documents, only ``contradicted`` /
    ``could_not_verify`` findings, every finding naming its own evidence
    verbatim.
    """
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise TypeError(f"context must be dict or None, got {type(context).__name__}")
    return detect_crossref_defects(
        text,
        context.get("source", ""),
        verbatim_run_present=context.get("verbatim_run_present"),
    )


# The mandated short name: ``detect(document_text)``.
detect = detect_crossref_defects
