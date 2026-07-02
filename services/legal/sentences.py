"""Legal-aware sentence splitter (T0).

The stdlib and AFM splitters fragment legal abbreviations ("U.S.",
"F.3d", "v.", "Fed. R. Civ. P."), which would split a citation or party
name mid-sentence and break anchor extraction. This splitter protects a
known abbreviation list and single-letter initials so a sentence
boundary is only taken at a real one.

Pure regex + a static set, no learned weights.
"""

from __future__ import annotations

import re

from .citations_eyecite import find_citations

_ABBREVIATIONS = {
    "u.s",
    "u.s.c",
    "v",
    "no",
    "sec",
    "art",
    "inc",
    "ltd",
    "co",
    "corp",
    "llc",
    "l.p",
    "e.g",
    "i.e",
    "cf",
    "id",
    "ibid",
    "al",
    "mr",
    "mrs",
    "ms",
    "dr",
    "fed",
    "civ",
    "crim",
    "proc",
    "evid",
    "app",
    "cir",
    "sup",
    "ct",
    "rev",
    "ed",
    "vol",
    "pp",
    "para",
    "ch",
    "pt",
}

# A sentence end is [.!?] + whitespace then EITHER a hard line break (a real
# terminator immediately before a newline is a boundary regardless of the next
# line's case) OR, on the same line, an opening quote/bracket? + a capital or
# digit. We re-merge if the token before the punctuation is a known abbreviation
# or a single-letter initial. The hard-line-break arm is case-insensitive on
# purpose: a lowercase continuation ("...unequal.\nbrown 347 U.S. 483 confirms
# it.") used to merge two genuinely-separate sentences into one logical group,
# widening the opinion pool the altered-quote attribution pass checks against
# (xhigh review finding 6). It only fires on the whole-draft logical split:
# split_sentences splits on newlines first, so the per-line core never sees one.
#
# NOTE: we deliberately do NOT treat a closing-quote boundary ("...unequal." Brown
# v. Board, 347 U.S. 483.) as a split point. Doing so severs a quoted holding from
# the citation that immediately follows it (the litigator pattern), which is worse
# than the cost it would fix: a brief of quoted holdings WITHOUT inline citations
# collapses into one claim. The newline arm preserves this: the terminator must sit
# immediately before the line break, so a period inside a closing quote (".\n) does
# not split. Splitting the same-line closing-quote case correctly needs citation-
# aware lookahead (eyecite spans start at the reporter, not the party name), which
# is not yet built. See docs/notes on the unit-of-grounding limitation.
_BOUNDARY = re.compile(
    # The (?<![.!?]) run-boundary guard + possessive quantifiers keep the scan
    # linear on adversarial punctuation floods (CodeQL py/polynomial-redos,
    # PR #194): a boundary may only start at the head of a terminator run.
    r"(?<![.!?])[.!?]++(?:"
    r"(?P<ws_nl>[ \t]*+[\r\n]+\s*)"  # hard line break: a boundary at any next-char case
    r"|(?P<ws_inline>\s+)(?=[\"'(\[]?[A-Z0-9])"  # same line: next opens with a cap/digit
    r")"
)


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences without breaking legal abbreviations.

    Hard line boundaries are sentence boundaries too. Drafts pasted from slide
    decks, bullet lists, or outline-style notes routinely carry NO terminal
    punctuation, so a ``[.!?]``-only split collapses an entire multi-bullet
    draft into ONE giant "sentence". Downstream (the deterministic verify
    envelope) that means a single altered figure flags the whole draft as one
    claim, the examination drawer reads "nothing supports this statement", the
    per-claim surface has no span to point at, and no supported statement is
    ever surfaced beside the flagged one. Splitting on newlines first restores
    the unit a reader actually reasons about (one line / one bullet); each line
    is then sentence-split exactly as before. Single-line input is unchanged
    (no newline -> one line -> byte-identical to the prior behavior), and the
    per-line trim keeps each returned sentence a whitespace-collapsed substring
    of the draft, so claim-to-draft alignment (services.legal.align) still
    places every line.
    """
    text = text.strip()
    if not text:
        return []
    sentences: list[str] = []
    for line in re.split(r"[\r\n]+", text):
        line = line.strip()
        if line:
            sentences.extend(_split_line_sentences(line))
    return sentences


def split_sentences_with_groups(text: str) -> tuple[list[str], list[int]]:
    """Per-line surface segments plus, for each, the id of its LOGICAL sentence.

    ``segments`` is exactly ``split_sentences(text)`` -- one unit per physical
    line, the surface a reader points at and the alignment layer places (the
    slide/bullet fix). ``groups[i]`` is the id of the logical sentence segment
    ``i`` belongs to: the line-unaware unit grounding used BEFORE the per-line
    split. When a logical sentence hard-wraps across physical lines (a quoted
    holding and the citation that grounds it, say), its several consecutive
    segments share one group id, so an attribution pass (the altered-quote check)
    can pool by logical sentence -- restoring same-sentence attribution across a
    soft line wrap -- while the surface stays per-line.

    Ground truth is the pre-line-split splitter (``_split_line_sentences`` over
    the whole draft, which is exactly what ``split_sentences`` was before the
    per-line change): the per-line segments are a strict refinement of it (every
    line-split boundary is also one of its boundaries, plus extra cuts at soft
    wraps), so consecutive segments are merged until their space-joined,
    whitespace-collapsed text equals the next logical sentence. A real sentence
    boundary (a period mid-line) stays a boundary in BOTH, so it is never merged:
    "proximity is not attribution" holds -- only soft wraps merge. Defensive: if
    the two ever fail to line up exactly, every segment gets its own group
    (identity) -- the pre-fix per-segment behavior, never a mis-group or a crash.
    """
    segments = split_sentences(text)
    # The line-unaware core over the whole draft == the pre-regression logical split.
    logical = _split_line_sentences(text)
    return segments, _logical_groups(segments, logical)


def _collapse(text: str) -> str:
    """Whitespace-collapsed form: every run of whitespace becomes a single space."""
    return " ".join(text.split())


def _logical_groups(segments: list[str], logical: list[str]) -> list[int]:
    """Map each surface segment to the index of the logical sentence it falls in.

    Greedy: accumulate consecutive segments until their collapsed space-join equals
    the current logical sentence, then advance. On any mismatch (the segments are
    not a clean refinement of ``logical``) fall back to identity grouping, so the
    caller degrades to per-segment attribution rather than mis-grouping or raising.
    """
    groups: list[int] = []
    gid = 0
    acc = ""
    for seg in segments:
        if gid >= len(logical):
            return list(range(len(segments)))
        target = _collapse(logical[gid])
        acc = f"{acc} {seg}" if acc else seg
        collapsed = _collapse(acc)
        if not target.startswith(collapsed):
            return list(range(len(segments)))
        groups.append(gid)
        if collapsed == target:
            gid += 1
            acc = ""
    if acc or gid != len(logical):
        return list(range(len(segments)))
    return groups


def _split_line_sentences(text: str) -> list[str]:
    """Split a single physical line into sentences (the legal-aware core)."""
    text = text.strip()
    if not text:
        return []

    # Never split inside a citation. A reporter cite ("100 F. Supp. 2d 200",
    # "123 So. 3d 456", "500 B.R. 100") and a statute cite ("17 C.F.R. 240.501")
    # carry internal periods the abbreviation list alone does not cover; a split
    # there shatters the cite across sentences and defeats case-existence and quote
    # grounding. eyecite gives the exact span, so any boundary whose punctuation
    # falls inside a detected citation is suppressed. Plain prose ("I think so.")
    # has no citation span, so its boundaries are unaffected.
    def _with_trailing_parenthetical(end: int) -> int:
        # eyecite's span stops at the reporter number; a cite is usually followed by
        # a "(court year)" parenthetical whose own abbreviations ("S.D.N.Y.", "Fla.",
        # "Bankr. D. Del.") would split. Absorb one immediately-following balanced
        # parenthetical so the whole citation unit stays in one sentence. Safe on an
        # unbalanced or absent paren (returns the original end).
        i = end
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text) or text[i] != "(":
            return end
        depth = 0
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return end

    cite_spans = [
        (ref.start, _with_trailing_parenthetical(ref.end)) for ref in find_citations(text)
    ]

    def _inside_citation(pos: int) -> bool:
        return any(s <= pos < e for s, e in cite_spans)

    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        if _inside_citation(m.start()):
            continue
        ws = m.group("ws_nl") or m.group("ws_inline")
        punct_end = m.start() + len(m.group(0)) - len(ws)
        segment = text[start:punct_end]
        last_token = re.split(r"[\s(]+", segment.strip())[-1].rstrip(".!?")
        if last_token.lower() in _ABBREVIATIONS or (len(last_token) == 1 and last_token.isupper()):
            continue
        sentences.append(segment.strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences
