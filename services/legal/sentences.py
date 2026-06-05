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
_BOUNDARY = re.compile(r"[.!?]+(\s+)(?=[\"'(\[]?[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences without breaking legal abbreviations."""
    text = text.strip()
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
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
