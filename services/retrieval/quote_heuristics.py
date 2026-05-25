"""Quote-string content-shape detector for the structural-citation gate.

Gate 1 (chunks-path heuristic, ADR 0004) catches verbatim-correct
quotes that are structure not answer content. A section heading, a
bare reference, or a page number can pass `validated_citation_quote`
because the quote IS a substring of its source node, yet it carries
no informational value. The detector here is pure and lives at quote
granularity: it inspects the cited quote string after the LLM has
emitted it.

Used in two places per the Gate 1 plan §"Where the predicate plugs in":

1. `evals/run_evals.py` chunks branch (T2.0, this PR) — counts how
   often surviving quotes are structural, producing the
   `structural_citation_rate` metric the chunks path has lacked since
   the Gate 0 typed-node-only ship.
2. (T2, future) `services/tutor.py::_resolve_grounded_answer` — when
   `RETRIEVAL_CHUNKS_HEURISTIC=true`, drop structural quotes and move
   their claims to `unsupported_spans`.

Both call sites share this single implementation. No drift.

Three structural signals (any one is sufficient):

- **Heading shape**: short, no terminal sentence punctuation, no
  finite verb, no code/math characters, single line. Catches
  `"Chapter 3: Contract Formation"`.
- **Bare reference**: matches a fixed pattern set for numeric-only,
  author-year (`Smith 2019`), bracketed citation (`[12]`), or
  see-figure shape (`Fig. 4`, `p. 22`).
- **Banner shape**: every word title-cased, at least 2 words, no
  finite verb. Catches `"Photosynthesis And Respiration"`.

Verb detection is closed-class: a token has a finite verb if it
matches a small irregular list (`is`, `are`, `has`, `have`, `do`,
`did`, `can`, `will`, ...) OR ends in `-ed/-ing/-en` with a token
base longer than two characters. `-s` / `-es` are intentionally
excluded so plural nouns (`photosynthesis`, `methods`, `plants`) do
not false-positive; the common third-person-singular `-s` verbs live
in the irregular list. False positives push borderline quotes into
"keep" (the safe direction). Documented kill condition in the plan:
spaCy escalation if false-drop > 5% on the labeled slice.

The terminal-punctuation gate on heading shape is the key fix versus
the original plan draft: a short factual sentence like
`"Photosynthesis is a chemical process."` ends in a period and
survives, even though it would otherwise meet length + verb checks.
"""

from __future__ import annotations

import os
import re
from typing import FrozenSet

HEADING_MAX_CHARS_DEFAULT = 80


def _heading_max_chars() -> int:
    """Resolve from env at call time so tests can override per-call."""
    raw = os.getenv("CARREL_HEADING_MAX_CHARS")
    if raw is None:
        return HEADING_MAX_CHARS_DEFAULT
    try:
        return int(raw)
    except ValueError:
        return HEADING_MAX_CHARS_DEFAULT


_IRREGULAR_FINITE_VERBS: FrozenSet[str] = frozenset(
    {
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "has",
        "have",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "done",
        "can",
        "could",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "go",
        "goes",
        "went",
        "gone",
        "going",
        "say",
        "says",
        "said",
        "saying",
        "see",
        "sees",
        "saw",
        "seen",
        "seeing",
        "make",
        "makes",
        "made",
        "making",
        "take",
        "takes",
        "took",
        "taken",
        "taking",
        "come",
        "comes",
        "came",
        "get",
        "gets",
        "got",
        "gotten",
        "getting",
        "know",
        "knows",
        "knew",
        "known",
        "knowing",
        "think",
        "thinks",
        "thought",
        "thinking",
        "give",
        "gives",
        "gave",
        "given",
        "giving",
    }
)

# Suffixes that strongly signal verb forms when the token base is long
# enough. `-s` and `-es` are excluded because plural nouns
# (`photosynthesis`, `methods`, `plants`) would false-positive; the
# common third-person-singular present verbs (`is`, `has`, `does`,
# `goes`, `says`, `sees`, `makes`, `takes`, `comes`, `gets`, `knows`,
# `thinks`, `gives`) live in the irregular list above.
_VERB_SUFFIXES = ("ed", "ing", "en")

_SENTENCE_TERMINATORS = (".", "!", "?")

# Characters that mark a quote as code, math, markup, or otherwise
# not a section heading. Headings in normal prose don't carry these.
_NON_HEADING_CHARS = frozenset("()[]{}=;<>&|\n\t")

_BARE_REFERENCE_PATTERNS = (
    # Numeric-only after stripping punctuation: "12", "237", "12, 14, 16"
    re.compile(r"^[\d\.,;\-\s]+$"),
    # Author-year: "Smith 2019", "Smith and Jones 2020", "Smith et al. 2018"
    re.compile(
        r"^[A-Z][a-zA-Z\-]+"
        r"(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-zA-Z\-]+))?"
        r"\s*,?\s*\(?\d{4}[a-z]?\)?\.?$"
    ),
    # Bracketed: "[12]", "(12)"
    re.compile(r"^[\[\(]\s*\d+\s*[\]\)]\.?$"),
    # See-figure / page-number: "Fig. 4", "p. 22", "see Table 3"
    re.compile(
        r"^(?:see\s+)?(?:fig(?:ure)?|table|chart|p)\.?\s+\d+[a-z]?\.?$",
        re.IGNORECASE,
    ),
)

_WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_PATTERN.finditer(text)]


def _has_finite_verb(text: str) -> bool:
    for token in _tokens(text):
        if token in _IRREGULAR_FINITE_VERBS:
            return True
        for suffix in _VERB_SUFFIXES:
            if token.endswith(suffix) and (len(token) - len(suffix)) > 2:
                return True
    return False


def _ends_with_sentence_terminator(text: str) -> bool:
    return text.rstrip().endswith(_SENTENCE_TERMINATORS)


def _contains_non_heading_chars(text: str) -> bool:
    return any(ch in _NON_HEADING_CHARS for ch in text)


def is_heading_shape(quote: str) -> bool:
    """Heading detector: short, single line, no terminal punctuation,
    no finite verb, no code/math characters.

    The terminal-punctuation gate distinguishes a heading (no period)
    from a short factual sentence ("Photosynthesis." or "Photosynthesis
    is the process."). The non-heading-chars gate excludes code,
    equations, JSON, and multi-line bullets.
    """
    stripped = quote.strip()
    if not stripped:
        return False
    if len(stripped) > _heading_max_chars():
        return False
    if _ends_with_sentence_terminator(stripped):
        return False
    if _contains_non_heading_chars(stripped):
        return False
    return not _has_finite_verb(stripped)


def is_bare_reference(quote: str) -> bool:
    """True if `quote` matches a bare-reference pattern (Smith 2019, [12], Fig. 4)."""
    stripped = quote.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in _BARE_REFERENCE_PATTERNS)


def is_banner_shape(quote: str) -> bool:
    """Title-case banner detector.

    Every word starts uppercase, at least 2 words, no finite verb. The
    two-word minimum avoids flagging proper nouns; the verb gate
    avoids flagging short title-cased sentences.
    """
    stripped = quote.strip()
    if not stripped or _contains_non_heading_chars(stripped):
        return False
    words = stripped.split()
    if len(words) < 2:
        return False
    for word in words:
        clean = word.strip(".,:;!?\"'()")
        if not clean or not clean[0].isupper():
            return False
    return not _has_finite_verb(stripped)


def is_structural_quote(quote: str) -> bool:
    """True if `quote` is a structural shape (heading, bare reference, banner).

    Public API used by both the eval harness instrumentation (T2.0)
    and the future runtime filter in `_resolve_grounded_answer` (T2).
    """
    return is_heading_shape(quote) or is_bare_reference(quote) or is_banner_shape(quote)


def chunks_heuristic_enabled() -> bool:
    """Whether the runtime structural-citation filter is on.

    Default False until T4 flips the default. The eval-harness
    instrumentation ignores this flag; it always measures.
    """
    return os.getenv("RETRIEVAL_CHUNKS_HEURISTIC", "false").lower() == "true"
