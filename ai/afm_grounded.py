"""Server-side helpers for the AFM grounded-answer flow.

Why this module exists:
The "don't ask AFM for quotes" insight. AFM (3B parameters, no runtime
guided generation beyond `@Generable`) can identify *which* chunk
supports a claim, but verbatim quote extraction is unreliable in small
models. Instead, AFM emits only chunk indices, and Python extracts the
most relevant verbatim span from each cited chunk using lexical
overlap against the answer text. This is:

* More accurate -- chunk text is ground truth; LLM-generated quotes
  can drift one word and break Carrel's verbatim-citation guard.
* Faster -- fewer tokens for AFM to emit means lower latency.
* Schema-trivial -- the model only emits ints, which is well within
  what `@Generable`-constrained decoding can reliably produce on AFM.

This file is provider-agnostic: it operates on plain chunk strings and
an answer string, and emits the verbatim span. `services/tutor.py`
calls it via `AFMClient.request_grounded_answer`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sentence splitting -- minimal, no NLTK dependency. Splits on
# .?! followed by whitespace, while preserving common abbreviations.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\'])")
_TOKEN_RE = re.compile(r"\w+")

# Stopwords ignored by the Jaccard scorer. Including these inflates
# the overlap score for tangentially-related chunks (e.g. the answer
# "Variance is the average of squared differences" trivially shares
# {"the", "of"} with any chapter-title chunk). Filtering them yields
# scores that better reflect substantive semantic overlap.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being",
    "but", "by", "do", "does", "for", "from", "has", "have", "if",
    "in", "into", "is", "it", "its", "of", "on", "or", "so", "such",
    "than", "that", "the", "their", "them", "these", "this", "those",
    "to", "was", "were", "which", "will", "with", "you", "your",
})


@dataclass(frozen=True)
class ExtractedSpan:
    """A verbatim span from a chunk plus its lexical-overlap score.

    `text` is guaranteed to be a substring of the source chunk.
    `score` is in [0.0, 1.0], higher = better overlap with the answer.
    `is_full_chunk` is True when no sentence-level subspan beat the
    full chunk; the caller may want to truncate.
    """

    text: str
    score: float
    is_full_chunk: bool


def _tokens(text: str) -> list[str]:
    """Lowercased content tokens. Stopwords are filtered out so the
    Jaccard scorer reflects substantive overlap, not function-word
    coincidence."""
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if t.lower() not in _STOPWORDS
    ]


def _jaccard(a: list[str], b: list[str]) -> float:
    """Token-level Jaccard similarity. Cheap, robust, no embeddings."""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _split_sentences(text: str) -> list[str]:
    """Splits a chunk into sentences using a minimal heuristic. The
    function preserves exact substrings: every returned sentence is a
    verbatim slice of the input, so callers can re-emit it as a
    citation quote without re-quoting issues."""
    text = text.strip()
    if not text:
        return []
    candidates = _SENTENCE_SPLIT_RE.split(text)
    # Keep candidates that are non-trivial. Very short fragments
    # (< 20 chars) usually carry no signal and make poor citations.
    return [c.strip() for c in candidates if len(c.strip()) >= 20]


def extract_best_span(
    chunk_text: str,
    answer_text: str,
    *,
    min_score: float = 0.10,
    max_chars: int = 320,
) -> ExtractedSpan:
    """Pick the span from `chunk_text` that best supports `answer_text`.

    Strategy:
      1. Split the chunk into sentences.
      2. Score each sentence by token-level Jaccard against the answer.
      3. Return the highest-scoring sentence if it clears `min_score`.
      4. Otherwise return the truncated full chunk so the citation
         still surfaces *something* the user can click through to.

    `max_chars` caps the returned span for citation-chip display; the
    truncation always happens at a word boundary.
    """
    answer_tokens = _tokens(answer_text)
    if not answer_tokens or not chunk_text.strip():
        return ExtractedSpan(
            text=_truncate_at_word(chunk_text, max_chars),
            score=0.0,
            is_full_chunk=True,
        )

    sentences = _split_sentences(chunk_text)
    if not sentences:
        return ExtractedSpan(
            text=_truncate_at_word(chunk_text, max_chars),
            score=0.0,
            is_full_chunk=True,
        )

    best_text = sentences[0]
    best_score = 0.0
    for sentence in sentences:
        score = _jaccard(answer_tokens, _tokens(sentence))
        if score > best_score:
            best_score = score
            best_text = sentence

    if best_score >= min_score:
        return ExtractedSpan(
            text=_truncate_at_word(best_text, max_chars),
            score=best_score,
            is_full_chunk=False,
        )

    # Fallback: no sentence scored well enough. Surface the truncated
    # full chunk so the citation chip still goes somewhere useful.
    return ExtractedSpan(
        text=_truncate_at_word(chunk_text, max_chars),
        score=best_score,
        is_full_chunk=True,
    )


def _truncate_at_word(text: str, max_chars: int) -> str:
    """Truncate `text` at a word boundary.

    Returns a verbatim substring of `text`. No ellipsis is appended:
    the citation invariant is that the returned span must be findable
    inside the source chunk byte-for-byte, and "…" breaks that. The
    frontend renders its own truncation indicator if it wants one.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Walk back to the last whitespace to avoid splitting words.
    space = cut.rfind(" ")
    if space >= max_chars // 2:
        cut = cut[:space]
    return cut.rstrip()


# ---------------------------------------------------------------------------
# Proper-noun hallucination guard
# ---------------------------------------------------------------------------
#
# Real failure caught in user testing on 2026-05-11:
#   Question: "what is variance"
#   Chunks:   (talked about BFI / Big Foot Inn)
#   AFM said: "The variance of Microsoft's returns is 0.045."
#
# AFM substituted "Microsoft" from training data even though BFI was
# clearly in the chunks. Detection: any capitalized multi-word phrase
# or solo capitalized word longer than 3 chars in the answer that does
# not appear (case-insensitive substring) anywhere in the chunks is
# almost certainly fabricated.
#
# Common-vocabulary words that are capitalized at sentence starts get
# false-positive flagged. We allow-list the obvious ones and rely on
# the substring check to catch the rest (real proper nouns like
# "Microsoft" will almost always also appear in mid-sentence, while
# common words mostly appear in many cases throughout the chunks).

# Frequent sentence-starters that are usually NOT proper nouns. Keep
# this list short; over-broad allow-listing erases the guard.
_COMMON_SENTENCE_STARTERS = frozenset({
    "the", "a", "an", "this", "that", "these", "those",
    "it", "they", "we", "you", "i",
    "in", "on", "at", "for", "to", "of", "by", "with", "from",
    "if", "when", "while", "during", "after", "before",
    "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "but", "so", "because",
    "every", "each", "all", "some", "many", "few",
    "any", "no", "not", "yes",
    "however", "therefore", "thus", "hence",
    "first", "second", "third", "next", "last", "finally",
})

# Capitalized word at least 4 chars long. Allows simple acronyms
# (BFI, CEO) only when they appear in chunk text -- this regex still
# matches them, the substring check then verifies.
_PROPER_NOUN_RE = re.compile(r"\b[A-Z][A-Za-z]{2,}\b")

# Numeric tokens: integers, decimals, percentages. AFM 3B also
# substitutes numeric values from training data: real case where the
# chunks said "0.045" and the answer claimed "0.05". Same refuse
# policy applies: a wrong number is a wrong answer, not a stylistic
# rounding choice.
#
# We skip very short pure integers (year-like 1-3 digit numbers
# appear in too many natural-language contexts to gate on); the guard
# is for the "specific value claimed as a fact" failure mode.
_NUMERIC_TOKEN_RE = re.compile(r"\b\d+(?:[.,]\d+)+%?\b|\b\d{4,}\b|\b\d+%\b")


@dataclass(frozen=True)
class FabricationCheck:
    """Result of the proper-noun fabrication check.

    `suspect_terms` is the set of capitalized words found in `answer`
    that do not appear (case-insensitively) in the concatenated chunk
    text. Empty when the answer is clean; non-empty when AFM appears
    to have introduced an entity from training data.
    """

    suspect_terms: tuple[str, ...]

    @property
    def is_clean(self) -> bool:
        return not self.suspect_terms


def _sentence_initial_offsets(text: str) -> set[int]:
    """Character offsets in `text` that begin a sentence.

    Sentence-initial capitalization is grammatical, not a signal of a
    proper noun. We exclude those positions from the fabrication
    check to avoid false positives on words like "Variance is...".
    """
    offsets: set[int] = {0}
    for match in re.finditer(r"[.!?]\s+", text):
        offsets.add(match.end())
    return offsets


def detect_fabricated_terms(
    answer: str,
    chunks: list[str],
) -> FabricationCheck:
    """Return capitalized terms in `answer` that don't appear in any chunk.

    Case-insensitive substring matching. We skip:
      * words on the common-sentence-starter allow-list
      * words that begin a sentence (grammatical capitalization)

    The remaining hits are mid-sentence capitalized terms missing from
    the chunks. That's the failure pattern we're trying to catch:
    "Microsoft" injected from training data into an answer about
    chunks that mention only "BFI".
    """
    if not answer or not chunks:
        return FabricationCheck(suspect_terms=())
    haystack_lower = " ".join(chunks).lower()
    haystack_raw = " ".join(chunks)
    sentence_starts = _sentence_initial_offsets(answer)
    seen: list[str] = []
    for match in _PROPER_NOUN_RE.finditer(answer):
        if match.start() in sentence_starts:
            continue
        term = match.group(0)
        if term.lower() in _COMMON_SENTENCE_STARTERS:
            continue
        if term.lower() in haystack_lower:
            continue
        if term not in seen:
            seen.append(term)
    # Numeric fabrication: any specific number in the answer must
    # appear verbatim somewhere in the chunks. We accept either dot
    # or comma as the decimal separator on the chunk side (PDFs
    # localize), but the answer's numeric token must match one of the
    # forms exactly.
    for match in _NUMERIC_TOKEN_RE.finditer(answer):
        token = match.group(0)
        if token in haystack_raw:
            continue
        # Try the comma/dot swap so "0.045" matches a chunk written
        # "0,045" and vice versa. PDFs from EU-localized sources mix
        # these freely.
        sentinel = "\x01"
        swapped = token.replace(".", sentinel).replace(",", ".").replace(sentinel, ",")
        if swapped in haystack_raw:
            continue
        if token not in seen:
            seen.append(token)
    return FabricationCheck(suspect_terms=tuple(seen))
