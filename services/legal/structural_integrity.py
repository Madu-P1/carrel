"""Structural integrity: a single legal document verified against itself.

Intra-document, source-free, deterministic. No network, no database, no model.
This is distinct from the cross-document engine in ``deterministic_envelope`` (a
draft checked against a source contract held in the ``nodes`` table); here the
question is whether the document is internally consistent: references that
resolve, defined terms that are used, values that do not contradict themselves.

Disposition vocabulary, mapped onto the product's 3-state tray:

* ``FLAGGED`` - a real, confident defect (the catch).
* ``COULD_NOT_CHECK`` - an honest gap.

There is deliberately no ``verified`` state: a check that passes is silent, which
holds the no-green-badge stance. The safety posture is asymmetric and absolute: a
false LOUD flag (crying wolf) is the catastrophic error.

Per the 2026-06-24 decision (after three adversary fan-out rounds proved that
confidently distinguishing an internal dangling reference from a reference to
another instrument in free legal prose is a semantic problem regex cannot win):

* SI-1 (cross references) emits ONLY ``COULD_NOT_CHECK`` - a reference that does
  not resolve to a declared section surfaces as "review this reference", never a
  loud flag. This closes the entire cry-wolf class by construction. A confident
  dangling-reference flag awaits a stronger (T1) approach.
* SI-2 (defined-term-unused) keeps its loud ``FLAGGED`` - it is a deterministic,
  conservative check (single-pass plural-tolerant stemming) that held across all
  three adversary rounds.
* SI-3 (internal contradiction) emits ONLY ``COULD_NOT_CHECK`` (ADR-0013: bare
  proper-noun subject binding is too coarse for a confident accusation).
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass

from services.legal.anchors import build_alias_table, extract_anchors

# Disposition constants (never bare string literals at call sites: a typo would
# silently misroute a loud catch into an unrecognized state).
FLAGGED = "flagged"
COULD_NOT_CHECK = "could_not_check"

# Leading markup stripped before line-start detection, so a heading written as
# "## Section 4", "- 4.2 Payment", or "> Article 7" still reads as a declaration.
_MARKUP_PREFIX = "#>*•-"

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Bare-number line-start heading ("12. Term", "4.2 indemnification", "4(a) X").
# The title word may be ANY case (real contracts lowercase heading words). Only
# ever ADDS to the declared set, so a generous match is the safe direction.
_DECL_BARE = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\([a-z0-9]+\))?[.)]?\s+\w")
# Roman-numeral heading ("ARTICLE IV"). Keyword case-insensitive, numeral
# uppercase-only so a lowercase prose word is never parsed as a numeral.
_DECL_ROMAN = re.compile(r"(?i:^\s*(?:section|sec\.|clause|article|§§?)\s*)([IVXLCDM]+)\b")

# A run-in / inline declaration: a section introduced mid-sentence, signalled by a
# following parenthetical title ("Section 10 (Force Majeure)") or a preceding
# declaration verb ("...hereby adds Section 10"). Treating these as declarations
# keeps a genuinely-introduced section silent instead of a noisy could-not-check.
_PAREN_TITLE = re.compile(r"\s*\([A-Z][^)]{0,80}\)")
_DECL_VERB = re.compile(
    r"\b(?:add|adds|added|adding|insert|inserts|inserted|inserting|amend|amends|"
    r"amended|restate|restated|introduce|introduces|introducing|new)\b"
)

_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")
_WORD = re.compile(r"[A-Za-z]+")

# SI-2 cost bound. A pasted document this large, or carrying this many defined
# terms, is the adversarial DoS shape: the defined-but-unused check is a tidiness
# signal, not worth unbounded CPU on the verify hot path. Skip it (no findings)
# rather than hang. Mirrors the existing retrieval-budget cap.
_MAX_TEXT_FOR_DEFINED_TERMS = 200_000
_MAX_DEFINED_TERMS = 500

# Whole-pass bound. extract_anchors over a very large draft is superlinear (~16s at
# 200KB), and the structural check is a review surface, not the core verdict, so a
# draft past this skips it entirely (no findings) rather than block the verify
# request on synchronous CPU. ~3s worst case at this bound; real drafts are well under.
_MAX_TEXT_FOR_STRUCTURAL = 100_000

# Common legal/financial Latin-Greek irregular plurals the suffix stemmer cannot
# fold; both forms map to one key so a defined term and its plural use match.
_IRREGULAR_PLURAL = {
    "indices": "index",
    "indexes": "index",
    "analyses": "analysis",
    "bases": "basis",
    "appendices": "appendix",
    "matrices": "matrix",
    "criteria": "criterion",
    "addenda": "addendum",
    "memoranda": "memorandum",
    "data": "datum",
    "people": "person",
    "persons": "person",
    "children": "child",
    "men": "man",
    "women": "woman",
    "feet": "foot",
    "teeth": "tooth",
    "mice": "mouse",
    "geese": "goose",
}


@dataclass(frozen=True)
class StructuralFinding:
    kind: str  # dangling_cross_reference | defined_term_unused | internal_contradiction
    disposition: str  # FLAGGED | COULD_NOT_CHECK
    detail: str
    span: str
    start: int
    end: int
    target: str | None = None


def _normalize_subject(s: str) -> str:
    # Mirrors contract_verify._normalize_subject so SI-3 binds subjects identically
    # to the council-blessed cross-document percent path. A drift-guard test
    # (test_structural_integrity) asserts the two stay byte-identical.
    return s.strip().lower()


def _norm_num(s: str) -> str:
    # Fold full-width / compatibility digits to ASCII so a "Section ５" reference
    # reconciles with a "Section 5" declaration.
    return unicodedata.normalize("NFKC", s)


def _roman_to_int(s: str) -> int | None:
    if not s or any(ch not in _ROMAN_VALUES for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if total > 0 else None


def _section_number(text: str) -> str | None:
    m = _SECTION_NUMBER.search(text)
    return _norm_num(m.group(0)) if m else None


def _line_starts(text: str) -> list[int]:
    starts: list[int] = []
    off = 0
    for line in text.splitlines(keepends=True):
        starts.append(off)
        off += len(line)
    return starts or [0]


def _line_start_of(pos: int, line_starts: list[int]) -> int:
    i = bisect.bisect_right(line_starts, pos) - 1
    return line_starts[i] if i >= 0 else 0


def _is_declaration(text: str, start: int, end: int, line_starts: list[int]) -> bool:
    """True if a section anchor sits in heading / declaration position.

    Three forms count as a declaration (a heading that INTRODUCES a section, rather
    than a cross-reference to one): a line-start heading, a run-in heading named by
    a following parenthetical title, or one introduced by a declaration verb on the
    same line. Over-classifying a declaration only ever makes a reference silent
    instead of could-not-check - it can never cause a false flag.
    """
    line_start = _line_start_of(start, line_starts)
    prefix = text[line_start:start].lstrip().lstrip(_MARKUP_PREFIX).lstrip()
    if prefix == "":
        return True
    if _PAREN_TITLE.match(text[end : end + 90]):
        return True
    return bool(_DECL_VERB.search(prefix.lower()))


def _declared_numbers(text: str, section_anchors: list, line_starts: list[int]) -> set[str]:
    declared: set[str] = set()
    # 1. Keyworded declarations come from the SAME anchors as references (unified
    #    vocabulary + number grammar), filtered to heading position.
    for a in section_anchors:
        if _is_declaration(text, a.start, a.end, line_starts):
            num = _section_number(a.text)
            if num:
                declared.add(num)
    # 2. Bare-number and Roman line-start headings are NOT section anchors (no
    #    keyword / no digit), so they are scanned separately.
    for raw in text.splitlines():
        line = raw.lstrip().lstrip(_MARKUP_PREFIX).lstrip()
        m = _DECL_BARE.match(line)
        if m:
            declared.add(_norm_num(m.group(1)))
        rm = _DECL_ROMAN.match(line)
        if rm:
            value = _roman_to_int(rm.group(1))
            if value is not None:
                declared.add(str(value))
    return declared


def _resolves(number: str, declared: set[str]) -> bool:
    """A reference resolves if its own number, any ANCESTOR, or any DESCENDANT is
    declared.

    "4.2" resolves when "4" is declared (subsection of a declared section);
    "4" resolves when "4.2" is declared (a section whose only headings are its
    subsections).
    """
    if number in declared:
        return True
    parts = number.split(".")
    if any(".".join(parts[:i]) in declared for i in range(1, len(parts))):
        return True
    prefix = number + "."
    return any(d.startswith(prefix) for d in declared)


def check_cross_references(text: str, anchors: list | None = None) -> list[StructuralFinding]:
    """SI-1: section references that do not resolve to a declared section.

    Emits ONLY ``COULD_NOT_CHECK`` (never ``FLAGGED``). A reference whose number
    (or any ancestor / descendant) is declared, or that sits in a heading position,
    is silent; anything else surfaces as "review this reference". Confidently
    distinguishing an internal dangle from a reference to another instrument in
    free prose is beyond a deterministic regex, and the product never cries wolf,
    so the honest output is a review prompt, not an accusation (2026-06-24 decision
    after three adversary fan-out rounds).
    """
    if not text or not text.strip():
        return []
    if anchors is None:
        anchors = extract_anchors(text)
    section_anchors = [a for a in anchors if a.type == "section"]
    if not section_anchors:
        return []
    line_starts = _line_starts(text)
    declared = _declared_numbers(text, section_anchors, line_starts)

    findings: list[StructuralFinding] = []
    for a in section_anchors:
        number = _section_number(a.text)
        if number is None:
            continue
        if _is_declaration(text, a.start, a.end, line_starts):
            continue  # this anchor IS a heading, not a reference
        if _resolves(number, declared):
            continue  # resolves directly or via an ancestor/descendant section
        findings.append(
            StructuralFinding(
                kind="dangling_cross_reference",
                disposition=COULD_NOT_CHECK,
                detail=(
                    f"{a.text} is referenced but was not found among this document's "
                    "declared sections; review whether it is a dangling reference or "
                    "points to another instrument."
                ),
                span=a.text,
                start=a.start,
                end=a.end,
                target=number,
            )
        )
    return findings


def _stem(word: str) -> str:
    """A crude singular stem for plural-tolerant defined-term use counting.

    Folds regular and common irregular plurals to one key in BOTH directions
    (party/parties, holder/holders, notice/notices, service/services,
    index/indices), so a defined term and its plural use count as the same word.
    The ``es`` strip fires only on sibilant endings (boxes -> box, classes ->
    class) so a consonant+e word keeps its ``e`` (notices -> notice, not notic).
    Over-folding only suppresses a flag, the safe direction.
    """
    w = word.lower()
    if w.endswith("'s"):
        w = w[:-2]
    if w in _IRREGULAR_PLURAL:
        return _IRREGULAR_PLURAL[w]
    if w.endswith("ies") and len(w) > 3:
        return w[:-3] + "y"
    if w.endswith(("ses", "xes", "zes", "ches", "shes")) and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "is", "us")) and len(w) > 1:
        # Latin singulars ("basis", "analysis", "status", "corpus") keep their s.
        return w[:-1]
    return w


def _count_subsequence(doc: list[str], sub: list[str]) -> int:
    n = len(sub)
    if n == 0 or n > len(doc):
        return 0
    return sum(1 for i in range(len(doc) - n + 1) if doc[i : i + n] == sub)


def check_defined_terms(text: str, alias_table: dict | None = None) -> list[StructuralFinding]:
    """SI-2: a defined term that is never used outside its own definition.

    Conservative, to never cry wolf. The document is tokenized ONCE into a stem
    multiset (O(document), not O(terms x document)), so a defined term is counted
    as "used" when any word in the document shares its stem - covering plurals in
    both directions, lower-cased and possessive uses. A single-word term that still
    appears only once (its definition) is flagged. Multi-word terms are matched as
    a phrase with a tolerant trailing plural on the final word. An oversized paste
    or a pathological term count is skipped (the DoS bound).

    Used-but-never-defined is deliberately NOT flagged in v1 (capitalised words are
    everywhere); it is a documented recall gap, never a loud verdict.
    """
    if not text or not text.strip() or len(text) > _MAX_TEXT_FOR_DEFINED_TERMS:
        return []
    if alias_table is None:
        alias_table = build_alias_table(text)
    if not alias_table or len(alias_table) > _MAX_DEFINED_TERMS:
        return []
    # Tokenize ONCE into a stem sequence, dropping lone possessive "s" remnants (so
    # "Buyer's Group" tokenizes to buyer/group). Single- AND multi-word terms are
    # counted by STEM, so regular + irregular plurals (via _stem), hyphenated reuses
    # ("Force-Majeure" tokenizes identically to "Force Majeure"), lower-cased, and
    # possessive uses all reconcile with the definition on the same code path.
    doc_stems = [s for s in (_stem(m.group(0)) for m in _WORD.finditer(text)) if s != "s"]
    stem_counts: dict[str, int] = {}
    for s in doc_stems:
        stem_counts[s] = stem_counts.get(s, 0) + 1

    findings: list[StructuralFinding] = []
    for term in alias_table:
        if not term.strip():
            continue
        term_stems = [s for s in (_stem(w) for w in _WORD.findall(term)) if s != "s"]
        if not term_stems:
            continue
        if len(term_stems) == 1:
            count = stem_counts.get(term_stems[0], 0)
        else:
            count = _count_subsequence(doc_stems, term_stems)
        if count > 1:
            continue  # used somewhere beyond its definition
        loc = re.search(rf"\b{re.escape(term)}\b", text)
        findings.append(
            StructuralFinding(
                kind="defined_term_unused",
                disposition=FLAGGED,
                detail=f'The term "{term}" is defined but never used in this document.',
                span=term,
                start=loc.start() if loc else 0,
                end=loc.end() if loc else 0,
                target=term,
            )
        )
    return findings


def check_internal_contradictions(
    text: str, anchors: list | None = None
) -> list[StructuralFinding]:
    """SI-3: the same subject given two different values inside one document.

    PERCENT-ONLY and reuses the conservative D3 percent subject (a proper noun
    IMMEDIATELY following the percent). Per ADR-0013, money/duration/date carry no
    subject and are NEVER compared here. The disposition is ALWAYS
    ``COULD_NOT_CHECK``, never ``FLAGGED``: a bare proper-noun subject cannot tell
    "two values of one quantity" from "two quantities near the same name" (a 10%
    France tax vs a 20% France tariff), and both intra-document statements may be
    true, so the honest output is "review this", not an accusation.
    """
    if not text or not text.strip():
        return []
    if anchors is None:
        anchors = extract_anchors(text)
    by_subject: dict[str, list] = {}
    for a in anchors:
        if a.type == "percent" and a.subject:
            by_subject.setdefault(_normalize_subject(a.subject), []).append(a)
    findings: list[StructuralFinding] = []
    for group in by_subject.values():
        if len({a.canonical_value for a in group}) < 2:
            continue
        ordered = sorted(group, key=lambda a: a.start)
        first = ordered[0]
        second = next(a for a in ordered if a.canonical_value != first.canonical_value)
        findings.append(
            StructuralFinding(
                kind="internal_contradiction",
                disposition=COULD_NOT_CHECK,
                detail=(
                    f"{first.text} and {second.text} both appear near "
                    f'"{first.subject}"; the engine cannot confirm whether they describe '
                    "the same quantity. Review for a possible inconsistency."
                ),
                span=f"{first.text} / {second.text}",
                start=ordered[0].start,
                end=ordered[-1].end,
                target=_normalize_subject(first.subject),
            )
        )
    return findings


def check_structural_integrity(text: str) -> list[StructuralFinding]:
    """Run every structural-integrity check over a single document, source-free.

    SI-1 (dangling cross-references) + SI-2 (defined-term integrity) + SI-3
    (internal contradiction). The document's anchors and alias table are computed
    ONCE here and shared, so a verify request pays for a single anchor pass. A draft
    past _MAX_TEXT_FOR_STRUCTURAL skips the pass (returns []) so a huge adversarial
    paste cannot block the verify path on superlinear anchor extraction.
    """
    if not text or not text.strip() or len(text) > _MAX_TEXT_FOR_STRUCTURAL:
        return []
    anchors = extract_anchors(text)
    alias_table = build_alias_table(text)
    return (
        check_cross_references(text, anchors)
        + check_defined_terms(text, alias_table)
        + check_internal_contradictions(text, anchors)
    )
