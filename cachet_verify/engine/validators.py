"""Stage 3 + post-synthesis validators for the typed-node Ask pipeline.

Implements `docs/algorithms/ask-pipeline.md` Validators section against the
new `nodes` table. The four match functions (`normalize_match_text`,
`slice_original_span`, `fuzzy_quote_match`, `validated_citation_quote`) are
copied verbatim from `services.tutor` lines 342-470, generalized to work on
`node.verbatim_text` instead of `chunk.content`. The underscore-prefixed
originals stay in `services.tutor` until the Pro tutor ports to nodes
(master plan Phase 3); both copies coexist for one release.

Two invariant enforcers per the spec:

1. **Invariant 1** (`enforce_citation_in_retrieved_set`): every emitted
   citation's `node_id` must be in the retrieval result set. A model that
   hallucinates a node id outside what retrieval surfaced gets dropped.
2. **Invariant 2** (`enforce_verbatim_substring`): every quote must be a
   whitespace-normalized exact substring of its cited node's
   `verbatim_text`. NFKC + smart-quote + whitespace-collapse on both sides;
   case is preserved (verbatim means verbatim, not "near enough").

The validators are pure: they take input, return a filtered output. No
logging here. Callers (the Pro tutor in Phase 3, the cards endpoint today)
own observability and log drop counts by comparing input vs output.

The 0.95 fuzzy similarity floor in `fuzzy_quote_match` comes from PR-D1
(commit `aab0b1d8`); lower thresholds let paraphrases through that broke
Carrel's "every cited quote is verbatim" promise.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Structural stand-in for the retrieval node this validator reads. The
    # kernel is frozen self-contained (PyInstaller bundles cachet_verify only),
    # so it must not import from ``services`` even under TYPE_CHECKING -- a
    # type-only import can still be dragged into the freeze by the module graph.
    # This validator only ever touches ``node.verbatim_text``; a Protocol names
    # exactly that contract without a cross-package import.
    from typing import Protocol

    class RetrievedNode(Protocol):
        verbatim_text: str


# Fuzzy similarity floor. Raised from 0.70 to 0.95 in PR-D1.
QUOTE_SIMILARITY_FLOOR = 0.95

# Minimum normalized-match length before the fuzzy path will accept.
# Capped at 40 so short verbatim phrases (single sentences) still pass.
QUOTE_MIN_MATCH_LENGTH = 40

# Smart-quote, whitespace, and dash translation. Mirrors
# services.tutor._SMART_QUOTES (lines 190-208), plus dash folding: the dash
# class (U+2010..U+2015, U+2212) folds to one ASCII hyphen so a typist's "-"
# matches an opinion's en/em dash. Without this a verbatim quote that swaps a
# dash variant would false-positive as altered (the cry-wolf risk PR4 guards).
_SMART_QUOTES = str.maketrans(
    {
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "„": '"',  # double low-9 quote
        "‟": '"',  # double high-reversed-9 quote
        "’": "'",  # right single quote / apostrophe
        "‘": "'",  # left single quote
        "‚": "'",  # single low-9 quote
        "‛": "'",  # single high-reversed-9 quote
        "‐": "-",  # U+2010 hyphen
        "‑": "-",  # U+2011 non-breaking hyphen
        "‒": "-",  # U+2012 figure dash
        "–": "-",  # U+2013 en dash
        "—": "-",  # U+2014 em dash
        "―": "-",  # U+2015 horizontal bar
        "−": "-",  # U+2212 minus sign
        " ": " ",  # non-breaking space
        " ": " ",  # thin space
        " ": " ",  # narrow non-breaking space
        "​": " ",  # zero-width space
        "\r": " ",
        "\n": " ",
        "\t": " ",
    }
)


@dataclass(frozen=True)
class QuoteMatch:
    """Result of a successful quote-to-source match.

    `quote` is the original-form substring of the source text (preserves
    NFKC pre-normalization, e.g. the literal `ﬁnance` ligature). `repaired`
    is True when the matched span differs from the raw LLM-emitted quote
    (case fix, ligature expansion, whitespace normalization). Always False
    on the exact-substring path; True when the fuzzy path repaired.
    """

    quote: str
    repaired: bool


@dataclass(frozen=True)
class NormalizedText:
    """Whitespace-collapsed, NFKC + lowercase normalized text with an index
    map back into the original string. `index_map[i]` is the source index
    in the pre-normalization string that produced `text[i]`.

    Used by `slice_original_span` to return original-form substrings even
    when NFKC expansion produced multi-char output (e.g. ligatures).
    """

    text: str
    index_map: tuple[int, ...]


@dataclass(frozen=True)
class NodeCitation:
    """Citation keyed by `node_id` (the typed-node Pro tutor shape).

    Phase 3 of the master plan ports the Pro tutor to emit this shape
    instead of the legacy `services.tutor.Citation` (keyed by `chunk_id`).
    Defined here so Phase 2 validators are testable independently of the
    tutor port.

    Only `node_id` and `quote` are validator-relevant. The metadata fields
    (`doc_id`, `page`, `section`) pass through unchanged for downstream
    rendering.
    """

    node_id: int
    quote: str
    doc_id: str = ""
    page: int | None = None
    section: str | None = None


def normalize_match_text(value: str) -> NormalizedText:
    """NFKC + smart-quote + lowercase + whitespace-collapse normalization.

    Per-char NFKC preserves a mapping from each normalized output char
    back to its source index in the original string, so ligature
    expansion (e.g. `ﬁ` -> `fi`) doesn't break the slice-back invariant.
    Both expanded normalized chars point at the source ligature index;
    `slice_original_span` then returns the literal ligature.

    Mirrors `services.tutor._normalize_match_text` (lines 342-394). Public
    rename per master plan Phase 2.
    """
    raw = str(value or "")

    # Pass 1: per-char NFKC + smart-quote translate, carrying source index.
    expanded_chars: list[str] = []
    source_indices: list[int] = []
    for source_index, char in enumerate(raw):
        nfkc_expanded = unicodedata.normalize("NFKC", char)
        translated = nfkc_expanded.translate(_SMART_QUOTES)
        for output_char in translated:
            expanded_chars.append(output_char)
            source_indices.append(source_index)

    # Pass 2: lowercase + whitespace-collapse. Index map carries through.
    normalized_chars: list[str] = []
    index_map: list[int] = []
    previous_was_space = True
    for expanded_idx, char in enumerate(expanded_chars):
        source_idx = source_indices[expanded_idx]
        lowered = char.lower()
        if lowered.isspace():
            if normalized_chars and not previous_was_space:
                normalized_chars.append(" ")
                index_map.append(source_idx)
                previous_was_space = True
            continue
        normalized_chars.append(lowered)
        index_map.append(source_idx)
        previous_was_space = False
    # Strip trailing whitespace placeholder.
    if normalized_chars and normalized_chars[-1] == " ":
        normalized_chars.pop()
        index_map.pop()
    return NormalizedText(text="".join(normalized_chars), index_map=tuple(index_map))


def slice_original_span(
    content: str,
    normalized: NormalizedText,
    start: int,
    size: int,
) -> str:
    """Slice the original (pre-normalization) text using the normalized
    span's index map. Returns an empty string on out-of-bounds.
    """
    if size <= 0 or not normalized.index_map:
        return ""
    end_position = start + size - 1
    if start < 0 or end_position >= len(normalized.index_map):
        return ""
    start_index = normalized.index_map[start]
    end_index = normalized.index_map[end_position] + 1
    return content[start_index:end_index].strip()


def fuzzy_quote_match(
    raw_quote: str,
    content: str,
    normalized_quote: NormalizedText,
    normalized_content: NormalizedText,
) -> QuoteMatch | None:
    """Repair an LLM-emitted quote against the source text via longest
    common substring (via `difflib.SequenceMatcher`).

    PR-D1 raised the similarity floor from 0.70 to 0.95: anything looser
    silently accepts paraphrases that no longer literally back the claim.
    Drops to `unsupported_spans` on the caller side instead of being
    silently rewritten.

    Mirrors `services.tutor._fuzzy_quote_match` (lines 408-450). Public
    rename per master plan Phase 2.
    """
    if not normalized_quote.text or not normalized_content.text:
        return None
    matcher = SequenceMatcher(None, normalized_quote.text, normalized_content.text, autojunk=False)
    match = matcher.find_longest_match(
        0,
        len(normalized_quote.text),
        0,
        len(normalized_content.text),
    )
    if match.size <= 0:
        return None
    min_length = min(QUOTE_MIN_MATCH_LENGTH, len(normalized_quote.text))
    similarity = match.size / max(len(normalized_quote.text), 1)
    if match.size < min_length or similarity < QUOTE_SIMILARITY_FLOOR:
        return None
    quote = slice_original_span(content, normalized_content, match.b, match.size)
    if not quote:
        return None
    return QuoteMatch(quote=quote, repaired=quote != raw_quote)


def validated_citation_quote(raw_quote: str, content: str) -> QuoteMatch | None:
    """Resolve an LLM-emitted quote against the source content.

    Tries exact normalized-substring match first; falls back to fuzzy
    longest-match with the 0.95 similarity floor. Returns None when neither
    path passes. The returned `QuoteMatch.quote` is the original-form span
    of `content` (NFKC pre-normalization preserved).

    Mirrors `services.tutor._validated_citation_quote` (lines 453-470).
    Public rename per master plan Phase 2.
    """
    quote = str(raw_quote or "").strip()
    if not quote or not str(content or "").strip():
        return None
    normalized_quote = normalize_match_text(quote)
    normalized_content = normalize_match_text(content)
    if not normalized_quote.text or not normalized_content.text:
        return None

    exact_position = normalized_content.text.find(normalized_quote.text)
    if exact_position >= 0:
        actual = slice_original_span(
            content, normalized_content, exact_position, len(normalized_quote.text)
        )
        if actual:
            return QuoteMatch(quote=actual, repaired=actual != quote)

    return fuzzy_quote_match(quote, content, normalized_quote, normalized_content)


def normalize_for_verbatim(value: str) -> str:
    """NFKC + smart-quote + dash-fold + whitespace collapse, case preserved.

    Strictly stricter than `normalize_match_text`: no lowercase. Used by
    `enforce_verbatim_substring` (Invariant 2) where case mismatch is a
    drop signal, not a normalize signal, and by the PR4 draft-quote check
    (`verbatim_run_present`) so the draft-quote check and the engine's own
    quote validation share one source of normalization truth.
    """
    raw = unicodedata.normalize("NFKC", str(value or ""))
    translated = raw.translate(_SMART_QUOTES)
    return " ".join(translated.split())


# Back-compat private alias: pre-PR4 call sites import the underscored name.
_normalize_for_verbatim = normalize_for_verbatim


# A footnote call number in plain-text opinion extraction: a 1-3 digit run
# glued to sentence-terminal punctuation that itself follows a letter, e.g.
# "applied.5 It" or "statute;2 the". Legal quoters routinely drop these, so a
# correct verbatim quote omits the digit; stripping it from the SOURCE before
# matching prevents a cry-wolf flag.
#
# DELIBERATELY narrow: it requires the punctuation between the word and the
# digits. A bare letter-then-digit token (WD40, COVID19, Chapter7, iPhone12) is
# NOT a footnote call and must survive, or a verbatim quote of that token would
# false-flag as altered. We also never strip a digit run with a space before it
# ("Title 18", "26 U.S.C."). The captured punctuation is kept; only the digits
# (and an optional trailing letter like a footnote "5a") are removed.
_FOOTNOTE_CALL = re.compile(r"(?<=[A-Za-z])([.,;:])\d{1,3}[a-z]?(?=\s|$)")


def strip_footnote_calls(value: str) -> str:
    """Remove footnote-call digit markers from opinion/source text.

    Keeps the sentence-terminal punctuation the digit was glued to (so
    "applied.5 It" becomes "applied. It", not "applied It"). Applied to the
    SOURCE side only; the draft quote is never mutated. Does NOT touch digits
    welded directly to a word (WD40, COVID19): those are part of the token, not
    footnote calls, and stripping them would false-flag a verbatim quote.
    """
    return _FOOTNOTE_CALL.sub(r"\1", str(value or ""))


def verbatim_run_present(run: str, source: str) -> bool:
    """True if `run` appears as an exact (normalized) substring of `source`.

    The deterministic core of the PR4 draft-quote check. Both sides pass
    through `normalize_for_verbatim` (NFKC + smart-quote + dash-fold +
    whitespace collapse, case PRESERVED) and the source additionally through
    `strip_footnote_calls`. No fuzzy fallback by design: this detects
    alterations, so a near-miss must NOT be accepted (the fuzzy path in
    `validated_citation_quote` can accept a <5% alteration, which is a
    false negative for an alteration detector). An empty run is vacuously
    present (callers filter empties before calling).
    """
    norm_run = normalize_for_verbatim(run)
    if not norm_run:
        return True
    norm_source = normalize_for_verbatim(strip_footnote_calls(source))
    if not norm_source:
        return False
    return norm_run in norm_source


def enforce_citation_in_retrieved_set(
    citations: list[NodeCitation],
    retrieved_node_ids: set[int],
) -> list[NodeCitation]:
    """Invariant 1: drop citations whose `node_id` is not in the retrieval
    result set.

    A model that emits a citation pointing at a node id outside what
    retrieval surfaced is hallucinating coverage. The drop happens before
    quote validation so downstream callers don't pay for verifying a
    citation that was never sourced.

    Pure function; callers compute drop count by comparing input vs output
    list length and emit their own observability events.
    """
    return [c for c in citations if c.node_id in retrieved_node_ids]


def enforce_verbatim_substring(
    citation: NodeCitation,
    node: "RetrievedNode",
) -> NodeCitation | None:
    """Invariant 2: drop the citation if its quote is not a whitespace-
    normalized exact substring of the cited node's `verbatim_text`.

    **Contract:** `citation.quote` must be a single pre-extracted quoted
    span, NOT a full claim sentence. Phase 3 of the master plan introduces
    an upstream `extract_quoted_spans(claim.text)` pass that produces one
    citation per quoted substring; this validator gates each extracted
    span. Passing a full claim sentence here will reject almost everything
    because the claim text is not a verbatim substring of the source.

    NFKC + smart-quote + whitespace collapse on both sides; case is
    preserved. A quote that matches only after lowercasing or after fuzzy
    repair is dropped here even though `validated_citation_quote` would
    have accepted it. Use this gate when the caller's contract is
    "verbatim or nothing"; use `validated_citation_quote` when light
    auto-repair is acceptable.

    Pure function. Returns the citation on accept (no mutation), None on
    drop. Callers log the None case.
    """
    if not citation.quote.strip():
        return None
    normalized_quote = _normalize_for_verbatim(citation.quote)
    normalized_text = _normalize_for_verbatim(node.verbatim_text)
    if not normalized_quote or not normalized_text:
        return None
    if normalized_quote in normalized_text:
        return citation
    return None
