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

# A sentence end is [.!?] + whitespace + an opening quote/bracket? + a capital
# or digit. We re-merge if the token before the punctuation is a known
# abbreviation or a single-letter initial.
#
# NOTE: we deliberately do NOT treat a closing-quote boundary ("...unequal." Brown
# v. Board, 347 U.S. 483.) as a split point. Doing so severs a quoted holding from
# the citation that immediately follows it (the litigator pattern), which is worse
# than the cost it would fix: a brief of quoted holdings WITHOUT inline citations
# collapses into one claim. Splitting that case correctly needs citation-aware
# lookahead (eyecite spans start at the reporter, not the party name), which is not
# yet built. See docs/notes on the unit-of-grounding limitation.
_BOUNDARY = re.compile(r"[.!?]+(\s+)(?=[\"'(\[]?[A-Z0-9])")


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
        punct_end = m.start() + len(m.group(0)) - len(m.group(1))
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
