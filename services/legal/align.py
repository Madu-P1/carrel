"""Claim-to-draft span alignment (Cachet PR5a).

Places each verified claim against the lawyer's original draft text so the UI
(PR5b, the Margin layout) can pin a claim's disposition next to the sentence it
came from. Deterministic by design: we do NOT ask the model for a draft anchor
(that would touch the shared grounded-answer tool schema + prompt + the evals
gate, and a model can hallucinate a locator that does not exist). Instead we
search the real draft for each claim's best verbatim key.

The bright-line safety rule mirrors PR4's cry-wolf bar: a mis-pinned claim is a
trust failure exactly like a mis-flag, so a claim is PLACED only when its key
resolves to ONE unambiguous draft range; every ambiguity (no match, multiple
indistinguishable matches, fuzzy-but-uncertain) goes to the UNPLACED tray. The
tray is the honest destination, never a guess.

Search-key priority per claim (most reliable locator first):
  1. the claim's own verbatim draft-quote span, if the claim text contains one
     (a lawyer's literal quotation is a high-confidence locator)
  2. the claim's resolved citation quote text
  3. the claim text itself (a model paraphrase; weakest, often only fuzzy)

Pure: no I/O, no model calls, no confidence scores. Reuses the engine's own
normalizer (services.retrieval.validators) so placement and quote-checking share
one source of normalization truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.legal.quote_check import extract_draft_quote_spans
from services.retrieval.validators import (
    QUOTE_SIMILARITY_FLOOR,
    NormalizedText,
    fuzzy_quote_match,
    normalize_match_text,
)

# A normalized key shorter than this is too generic to place by content alone
# (e.g. "the statute"); if it is not uniquely resolvable it goes to the tray.
_MIN_KEY_CHARS = 12


@dataclass(frozen=True)
class ClaimPlacement:
    """Where one claim landed in the draft.

    `placed` True means `char_start`/`char_end` are a real, unambiguous range in
    the original draft. `placed` False means the claim is in the unplaced tray
    (char offsets are None). `method` records how it resolved, for observability
    and so the UI can render fuzzy placements distinctly if it wants.
    """

    claim_index: int
    placed: bool
    method: str  # "exact" | "fuzzy" | "unplaced"
    char_start: int | None = None
    char_end: int | None = None


def _claim_search_keys(claim: dict) -> list[str]:
    """Search keys for one serialized claim, best locator first.

    `claim` is a serialized claim dict (services.tutor._serialize_claims):
    {text, citations: [{quote, content, ...}], ...}. We take the claim's own
    quoted spans first, then citation quotes, then the claim text.
    """
    keys: list[str] = []
    text = str(claim.get("text") or "")
    for span_text, _s, _e in extract_draft_quote_spans(text):
        if span_text.strip():
            keys.append(span_text)
    for citation in claim.get("citations") or []:
        quote = str((citation or {}).get("quote") or "").strip()
        if quote:
            keys.append(quote)
    if text.strip():
        keys.append(text)
    # De-dup preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def _all_occurrences(haystack: str, needle: str) -> list[int]:
    """Every start index of `needle` in `haystack` (overlapping not needed for
    natural-language keys; non-overlapping scan is sufficient and cheaper)."""
    out: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + len(needle)


def _resolve_key(
    key: str,
    norm_draft: NormalizedText,
    draft_text: str,
    consumed: dict[str, int],
) -> tuple[int, int, str] | None:
    """Resolve one key to a normalized [start, end) range, or None if it cannot
    be placed unambiguously.

    `consumed` maps a normalized key to how many of its occurrences EARLIER
    claims with the SAME key already took, so a run of N claims sharing one
    repeated phrase consumes its N occurrences in draft order. The bright-line
    rule (never mis-pin): a key is placed only when, after removing the
    occurrences earlier same-key claims consumed, EXACTLY ONE candidate remains.
    Any other count (zero left, or two-or-more indistinguishable) goes to the
    tray. A lone claim whose key appears 2+ times is therefore unplaced, never
    pinned to a guessed occurrence.

    Returns (norm_start, norm_end, method) where method is "exact" or "fuzzy".
    """
    norm_key = normalize_match_text(key)
    if not norm_key.text:
        return None
    occurrences = _all_occurrences(norm_draft.text, norm_key.text)

    if occurrences:
        already = consumed.get(norm_key.text, 0)
        remaining = occurrences[already:]
        if len(remaining) == 1:
            start = remaining[0]
            consumed[norm_key.text] = already + 1
            return (start, start + len(norm_key.text), "exact")
        if len(remaining) >= 2:
            # Indistinguishable repeated matches: the honest destination is the
            # tray, not a guess. (A short generic key would also land here.)
            return None
        # remaining == 0: every occurrence was consumed by earlier same-key
        # claims; do not pin behind them.
        return None

    # Zero exact occurrences: try fuzzy, but only accept a confident, unique
    # longest-match. fuzzy_quote_match already enforces the 0.95 floor.
    match = fuzzy_quote_match(key, draft_text, norm_key, norm_draft)
    if match is None:
        return None
    # Re-locate the repaired span in the normalized draft to get its offset.
    norm_repaired = normalize_match_text(match.quote)
    if not norm_repaired.text:
        return None
    fuzzy_occurrences = _all_occurrences(norm_draft.text, norm_repaired.text)
    if len(fuzzy_occurrences) != 1:
        # Fuzzy match that is not uniquely locatable: do not guess.
        return None
    start = fuzzy_occurrences[0]
    # Guard: the repaired span must clear the same similarity bar vs the key, so
    # a fuzzy near-miss does not pin a materially different sentence.
    similarity = len(norm_repaired.text) / max(len(norm_key.text), 1)
    if similarity < QUOTE_SIMILARITY_FLOOR:
        return None
    return (start, start + len(norm_repaired.text), "fuzzy")


def align_claims_to_draft(
    draft_text: str,
    claims: list,
) -> tuple[list[ClaimPlacement], list[int]]:
    """Place each claim against the draft. Returns (placements, unplaced_indices).

    `claims` is the serialized claim list. `claim_index` is the UNFILTERED list
    position (so it matches the caller's `enumerate(claims)` when building verdict
    cards, even if the list contains a non-dict entry). Every claim gets exactly
    one ClaimPlacement; unplaced ones also appear in `unplaced_indices` for the
    tray. NEVER mis-pins: any ambiguity (no match, indistinguishable repeats,
    fuzzy-but-not-uniquely-locatable) -> unplaced.

    Repeated identical keys are consumed in draft order: a run of claims sharing
    one phrase takes its occurrences left to right; once they are exhausted,
    further same-key claims tray rather than pin behind an earlier one.
    """
    draft = str(draft_text or "")
    norm_draft = normalize_match_text(draft)
    placements: list[ClaimPlacement] = []
    unplaced: list[int] = []
    # normalized-key -> count of occurrences already taken by earlier claims.
    consumed: dict[str, int] = {}

    for index, claim in enumerate(claims):
        resolved: tuple[int, int, str] | None = None
        if norm_draft.text and isinstance(claim, dict):
            for key in _claim_search_keys(claim):
                resolved = _resolve_key(key, norm_draft, draft, consumed)
                if resolved is not None:
                    break

        if resolved is None:
            placements.append(ClaimPlacement(claim_index=index, placed=False, method="unplaced"))
            unplaced.append(index)
            continue

        norm_start, norm_end, method = resolved
        # Map the normalized [start, end) back to original draft offsets via the
        # index map (handles NFKC ligature expansion + collapsed whitespace).
        char_start = norm_draft.index_map[norm_start]
        # end maps from the last consumed normalized char + 1.
        char_end = norm_draft.index_map[norm_end - 1] + 1
        placements.append(
            ClaimPlacement(
                claim_index=index,
                placed=True,
                method=method,
                char_start=char_start,
                char_end=char_end,
            )
        )

    return placements, unplaced


def placement_to_dict(placement: ClaimPlacement) -> dict:
    """Serialize a ClaimPlacement to the wire shape attached per claim card."""
    return {
        "char_start": placement.char_start,
        "char_end": placement.char_end,
        "placed": placement.placed,
        "method": placement.method,
    }
