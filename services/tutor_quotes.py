"""Quote-validation helpers for the grounded-tutor pipeline.

The tutor must cite the exact substring it used. Models often
paraphrase or smart-quote the source; we accept a fuzzy near-match
as long as it's >= 70% similar and >= 40 normalized characters,
then re-slice the original content so the rendered citation is
verbatim.

`NormalizedText` keeps an index map so we can map back from a
position in the lowercased/whitespace-collapsed form to a span in
the original content. Every quote shown to the user is sliced from
the original — never reconstructed from the normalized form.

Lifted from services/tutor.py to keep the LLM runner focused on
LLM concerns. The public surface (`QuoteMatch`, `validate_quote`)
is re-exported from `services/tutor.py` for callers that already
imported from there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class QuoteMatch:
    quote: str
    repaired: bool


@dataclass(frozen=True)
class NormalizedText:
    text: str
    index_map: tuple[int, ...]


_WHITESPACE_RE = re.compile(r"\s+")
_SMART_QUOTES = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "’": "'",
        "‘": "'",
        "‚": "'",
        "‛": "'",
        " ": " ",
        " ": " ",
        " ": " ",
        "​": " ",
        "\r": " ",
        "\n": " ",
        "\t": " ",
    }
)

# Fuzzy match thresholds — tuned by integration tests.
_MIN_MATCH_CHARS = 40
_MIN_SIMILARITY = 0.7


def normalize(value: str) -> NormalizedText:
    """Lowercase, collapse whitespace, smart-quote-fold; keep an
    index map so positions in the normalized form map back to spans
    in `value`."""
    normalized_chars: list[str] = []
    index_map: list[int] = []
    previous_was_space = True
    canonical = str(value or "").translate(_SMART_QUOTES)
    for index, char in enumerate(canonical):
        lowered = char.lower()
        if lowered.isspace():
            if normalized_chars and not previous_was_space:
                normalized_chars.append(" ")
                index_map.append(index)
                previous_was_space = True
            continue
        normalized_chars.append(lowered)
        index_map.append(index)
        previous_was_space = False
    if normalized_chars and normalized_chars[-1] == " ":
        normalized_chars.pop()
        index_map.pop()
    return NormalizedText(text="".join(normalized_chars), index_map=tuple(index_map))


def slice_original(content: str, normalized: NormalizedText, start: int, size: int) -> str:
    """Map a (start, size) window in normalized space back to the
    original content. Returns "" on out-of-bounds (the caller treats
    that as "no match")."""
    if size <= 0 or not normalized.index_map:
        return ""
    end_position = start + size - 1
    if start < 0 or end_position >= len(normalized.index_map):
        return ""
    start_index = normalized.index_map[start]
    end_index = normalized.index_map[end_position] + 1
    return content[start_index:end_index].strip()


def _fuzzy_match(
    raw_quote: str,
    content: str,
    normalized_quote: NormalizedText,
    normalized_content: NormalizedText,
) -> QuoteMatch | None:
    if not normalized_quote.text or not normalized_content.text:
        return None
    matcher = SequenceMatcher(
        None, normalized_quote.text, normalized_content.text, autojunk=False
    )
    match = matcher.find_longest_match(
        0, len(normalized_quote.text), 0, len(normalized_content.text)
    )
    if match.size <= 0:
        return None
    min_length = min(_MIN_MATCH_CHARS, len(normalized_quote.text))
    similarity = match.size / max(len(normalized_quote.text), 1)
    if match.size < min_length or similarity < _MIN_SIMILARITY:
        return None
    quote = slice_original(content, normalized_content, match.b, match.size)
    if not quote:
        return None
    return QuoteMatch(quote=quote, repaired=quote != raw_quote)


def validate_quote(raw_quote: str, content: str) -> QuoteMatch | None:
    """Return a QuoteMatch if `raw_quote` is verbatim or near-verbatim
    in `content`, else None. The returned `quote` is always sliced
    from `content` so it's safe to display."""
    quote = str(raw_quote or "").strip()
    if not quote or not str(content or "").strip():
        return None
    normalized_quote = normalize(quote)
    normalized_content = normalize(content)
    if not normalized_quote.text or not normalized_content.text:
        return None

    exact_position = normalized_content.text.find(normalized_quote.text)
    if exact_position >= 0:
        actual = slice_original(
            content, normalized_content, exact_position, len(normalized_quote.text)
        )
        if actual:
            return QuoteMatch(quote=actual, repaired=actual != quote)

    return _fuzzy_match(quote, content, normalized_quote, normalized_content)
