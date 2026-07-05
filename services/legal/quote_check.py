"""Draft-quote-verbatim check (Cachet PR4).

The other Cachet checks verify the model's OWN extracted quotes against the
corpus. This module checks the quotes a LAWYER typed in their draft against the
cited source text, and flags ``quote_altered`` when a quoted run does not appear
verbatim in the source. It is the deterministic cry-wolf surface: a false
positive on a verification tool destroys trust, so every legitimate Bluebook
editing convention must pass clean, and anything the tool cannot fully see must
degrade to ``could_not_check``, never to a flag.

Pipeline:

  draft text
    -> extract_draft_quotes  (find the spans inside quotation marks)
       -> split_runs         (split each quote at the AUTHOR'S declared edits:
                              [brackets], ellipsis; those are not matched, and
                              each run is edge-trimmed of author punctuation)
          -> verbatim_run_present  (each run must be an exact normalized
                                    substring of the source pool; reuses the
                                    engine's normalizer + dash-fold +
                                    footnote-strip from services.retrieval)

What it attests: the words shown in quotation marks appear in the cited source
as written. What it does NOT attest: whether an omission (an ellipsis) changes
the meaning. Grounding, not truth.

Pure and deterministic. No I/O, no model calls, no confidence scores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from services.retrieval.validators import normalize_for_verbatim, strip_footnote_calls

# A quoted span in the draft. We match the OUTERMOST double-quote pair so an
# internal quotation (a cited opinion quoting a statute or prior case, extremely
# common in legal writing) does NOT fragment the span at the inner marks. Curly
# spans (U+201C .. U+201D) take everything up to the closing curly quote; the
# straight-quote arm is greedy to the LAST straight quote on the same logical
# span. Greediness here is deliberate and safe: over-capturing an outer span and
# then splitting it on edit marks is correct, whereas under-capturing (stopping
# at an inner quote) was the PR4 v1 cry-wolf bug. A span with no closing mate is
# never matched (extraction is conservative: skip what we cannot parse).
# DOTALL so a block quote that wraps across line breaks is still captured (the
# `.` then spans newlines); the negative lookahead stops the greedy straight-quote
# arm at a PARAGRAPH break (a blank line) so it never swallows the whole document
# between the first and last quote mark. The curly arm is a negated class, so it
# already crossed newlines and is unaffected. Greedy-to-last within a paragraph is
# preserved (the deliberate PR4 design: over-capture then split on edit marks).
_QUOTED_SPAN = re.compile(r"“([^”]*)”|\"((?:(?!\n[ \t]*\n).)*)\"", re.DOTALL)

# Author's declared edits inside a quote, which are NOT matched against source:
#   - any bracketed interpolation: [T]he caps, [the defendant] insertion,
#     [sic], [emphasis added], [citation omitted] -- one rule, no special-casing
#   - ellipsis: any run of 3+ dots (ASCII "...", spaced ". . .", an over-run
#     5-dot ". . . . ."), or Unicode U+2026. 3-or-more so no stray "." residue.
_EDIT_MARK = re.compile(r"\[[^\]]*\]|(?:\.\s*){3,}|…")

# Leading/trailing characters that are the author's punctuation, not part of the
# quoted words: the terminal period a lawyer puts INSIDE the closing quote
# (American convention) when the source continues mid-sentence, commas, quote
# marks, brackets/residue left by an edit split, and surrounding whitespace.
# Stripped from each run's EDGES before matching so a verbatim quote that merely
# ends in author punctuation is not falsely flagged. Interior punctuation is
# untouched (a substituted interior word is still caught).
_RUN_EDGE = re.compile(r"^[\s.,;:!?'\"“”‘’()\[\]]+|[\s.,;:!?'\"“”‘’()\[\]]+$")

# A run that, after edge-trimming, still contains a letter or digit is a real
# verbatim run worth checking. One that does not (pure punctuation residue) is
# vacuous and never flagged.
_HAS_ALNUM = re.compile(r"[A-Za-z0-9]")


@dataclass(frozen=True)
class SourceText:
    """One candidate source the draft quote may be checked against.

    `truncated` is True when the text was cut off (e.g. fetch_opinion_text hit
    its char cap), so a run absent from this source MIGHT live past the cut and
    must degrade to could_not_check rather than flag. `complete` is True when we
    are confident this text is a whole contiguous passage (a full opinion, or a
    whole loaded document); False for a single retrieval chunk, whose run could
    legitimately straddle into an adjacent chunk we did not join. We only assert
    `altered` against complete, untruncated sources.
    """

    text: str
    truncated: bool = False
    complete: bool = True


@dataclass(frozen=True)
class QuoteSegment:
    """One render slice of an altered quote, for the autopsy panel.

    ``kind`` is ``"verbatim"`` (a phrase found in a genuine source, shown in
    ink), ``"altered"`` (a phrase absent from every confident source: the
    fabricated words to strike through in oxblood), or ``"neutral"`` (the
    author's edit marks and connecting prose, never matched). The segments of a
    result concatenate back to the exact original quote, so the renderer can
    never drop or reorder a character. Carries only the lawyer's OWN words plus
    the per-phrase verdict the engine already reached: no source text crosses
    this boundary, so the zero-egress posture is unchanged.
    """

    text: str
    kind: str


@dataclass(frozen=True)
class QuoteCheckResult:
    """Verdict for one quoted span extracted from the draft.

    ``altered`` True means at least one verbatim run is absent from every source
    we could fully and confidently see: a real alteration or fabrication.
    ``unplaceable`` True means the tool could not honestly check this quote (no
    source available, the run fell past a truncation, or the only candidates
    were partial chunks the run might straddle); the caller maps this to
    could_not_check, NEVER to a flag. ``runs`` is the parsed verbatim runs.
    ``segments`` is the autopsy tiling of the quote (populated only for an
    ``altered`` quote; empty otherwise, where the quote renders plainly).
    """

    quote: str
    altered: bool
    unplaceable: bool
    runs: tuple[str, ...]
    segments: tuple[QuoteSegment, ...] = ()


def extract_draft_quotes(draft: str) -> list[str]:
    """Return the text inside each double-quoted span in ``draft``.

    Returns the INNER text (without the outer quote marks). Unbalanced or
    unclosed quotes yield no span (conservative: never flag what we could not
    parse). Empty quoted spans are dropped.
    """
    out: list[str] = []
    for match in _QUOTED_SPAN.finditer(draft or ""):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        inner = (inner or "").strip()
        if inner:
            out.append(inner)
    return out


def extract_draft_quote_spans(draft: str) -> list[tuple[str, int, int]]:
    """Like `extract_draft_quotes`, but also return each span's draft offsets.

    Returns (inner_text, start, end) where start/end are character offsets of
    the INNER text (inside the quote marks) in the original `draft`. Used by the
    PR5 claim-span alignment (services.legal.align) as one deterministic anchor
    source: a quoted span the lawyer typed is a high-confidence draft locator.
    Empty/whitespace-only spans are dropped. Offsets are into the raw draft, so
    the caller can map a placed claim back to the exact draft range.
    """
    out: list[tuple[str, int, int]] = []
    for match in _QUOTED_SPAN.finditer(draft or ""):
        group_index = 1 if match.group(1) is not None else 2
        inner = match.group(group_index) or ""
        if not inner.strip():
            continue
        # Offsets of the inner capture group, not the whole match (excludes the
        # quote marks themselves) so the span maps to the quoted words only.
        out.append((inner, match.start(group_index), match.end(group_index)))
    return out


def quoted_subphrases(run: str) -> list[str]:
    """The distinct quoted phrases inside a run, in case the span regex merged them.

    The quote-span extractor captures greedily from the first quote mark to the
    last, so a paragraph with two quoted phrases ('"A" failed because "B"') yields
    a single run with the inner marks retained ('A" failed because "B'). Splitting
    on quote marks recovers the phrases at the even positions; the odd positions
    are the author's own connecting prose, which was never quoted and must not be
    checked. A run with no inner marks yields itself unchanged. Shared by the
    sentence-level check (deterministic_envelope) and the brief-level panel so the
    two surfaces accept the same quotes.
    """
    parts = re.split(r'["“”]', run)
    phrases = [p for idx, p in enumerate(parts) if idx % 2 == 0 and p.strip()]
    return phrases or [run]


def first_letter_variants(run: str) -> tuple[str, ...]:
    """The run, plus the run with its first alphabetic character's case toggled.

    A lawyer who embeds a quote mid-sentence routinely lowercases the source's
    leading capital ("separate educational facilities..." from a sentence that
    opened "Separate ...") without the bracket convention ("[s]eparate"). That is
    a universally accepted edit, not an alteration, so the altered-quote check
    must accept either case at the leading letter. Interior case stays strict, so
    a substituted interior word is still caught. Shared by the sentence-level
    check and the brief-level panel.
    """
    for i, ch in enumerate(run):
        if ch.isalpha():
            swapped = ch.lower() if ch.isupper() else ch.upper()
            if swapped == ch:
                break
            return (run, run[:i] + swapped + run[i + 1 :])
    return (run,)


def split_runs(quote: str) -> list[str]:
    """Split a quoted span into the verbatim runs BETWEEN the author's edits.

    The bracketed interpolations and ellipses are the author's declared edits,
    not part of the source; only the runs between them must match verbatim. Each
    run is then edge-trimmed of the author's own surrounding punctuation (a
    terminal period inside the closing quote, stray residue from an edit split)
    so a verbatim quote that differs only at its edges is not falsely flagged.
    Runs that reduce to punctuation (no letter or digit) are dropped.
    """
    runs: list[str] = []
    for raw in _EDIT_MARK.split(quote or ""):
        trimmed = _RUN_EDGE.sub("", raw)
        if trimmed and _HAS_ALNUM.search(trimmed):
            runs.append(trimmed)
    return runs


def _coerce_sources(sources: list) -> list[SourceText]:
    """Accept either raw strings (back-compat: complete + untruncated) or
    SourceText. Empty/whitespace-only sources are dropped."""
    out: list[SourceText] = []
    for s in sources or []:
        if isinstance(s, SourceText):
            if s.text and s.text.strip():
                out.append(s)
        elif s and str(s).strip():
            out.append(SourceText(text=str(s)))
    return out


@dataclass(frozen=True)
class NormalizedSourcePool:
    """A source pool normalized ONCE for reuse across every draft quote.

    The brief-level panel checks many quoted spans against the SAME pool, so the
    normalization (NFKC + footnote strip + dash-fold) is hoisted here and computed
    one time per request rather than re-run per quote (E1). The normalized strings
    are deduped (a membership test is unaffected by duplicates, so dropping them is
    behavior-preserving and saves a substring scan per phrase). `has_sources`
    preserves the original `not usable` guard (a pool with sources but whose text
    normalizes to empty is still "has sources").
    """

    norm_all: tuple[str, ...]
    norm_confident: tuple[str, ...]
    has_uncertain_source: bool
    has_sources: bool
    # Case-folded confident-source texts, computed ONCE per pool for the
    # word-level autopsy (`_word_level_spans`) so the per-token presence test is
    # case-insensitive (matching the disposition gate's accepted leading-letter
    # edit) without rebuilding the fold per fabricated phrase.
    confident_text_cf: tuple[str, ...] = ()


def prepare_source_pool(sources: list) -> NormalizedSourcePool:
    """Coerce + normalize a source pool once, for reuse across many draft quotes.

    `sources` may be raw strings (treated as complete + untruncated) or `SourceText`
    records carrying truncation/completeness. The confident subset (complete AND
    untruncated, non-empty after normalization) is kept separate, since only those
    can ground an `altered` verdict; the presence of any partial/truncated source
    means an absent run degrades to could_not_check instead of altered.
    """
    usable = _coerce_sources(sources)
    norm_all_list = [normalize_for_verbatim(strip_footnote_calls(s.text)) for s in usable]
    norm_confident_list = [
        n for n, s in zip(norm_all_list, usable) if s.complete and not s.truncated and n
    ]
    # dict.fromkeys dedupes while preserving first-seen order (deterministic).
    norm_confident = tuple(dict.fromkeys(norm_confident_list))
    return NormalizedSourcePool(
        norm_all=tuple(dict.fromkeys(norm_all_list)),
        norm_confident=norm_confident,
        has_uncertain_source=any((s.truncated or not s.complete) for s in usable),
        has_sources=bool(usable),
        confident_text_cf=tuple(n.casefold() for n in norm_confident),
    )


def _word_level_spans(core: str, pool: NormalizedSourcePool) -> list[tuple[str, str]]:
    """Decompose a fabricated phrase into word-level (text, kind) spans.

    The phrase is absent from every confident source AS A WHOLE, but most of its
    words usually ARE genuine (a real quote with a few words spliced in or
    swapped). Strike only the words the source does not contain at all; the rest
    stay ``verbatim`` ink. The spans concatenate back to ``core`` exactly.

    Cry-wolf-safe by construction: a token is struck ONLY when its case-folded
    normalized form is a substring of NO confident source text. Case-folded
    SUBSTRING membership mirrors the leniency of the disposition gate (substring
    match plus the accepted leading-letter case edit), so a word the lawyer
    legitimately capitalized to embed mid-sentence ("Due" for source "due"), an
    interior case difference, or the "he" left by a "[T]he" bracket-cap is found
    in the source and never struck. The autopsy can therefore never strike a word
    the source contains in any form. The cost is the safe direction: a
    substitution that happens to be a source substring ("constitutional" inside
    "unconstitutional") is not pinpointed and falls back to the whole-phrase
    strike below. Two honest fallbacks both strike the whole phrase: no confident
    source to check against, or a phrase whose every word is present yet absent as
    written (a reordering/splice) — an altered verdict must always show at least
    one struck span, never a silently clean autopsy.
    """
    tokens = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", core)]
    if not tokens or not pool.confident_text_cf:
        return [(core, "altered")]

    # Case-folded confident-source texts, precomputed once per pool. A token that
    # normalizes to empty is pure punctuation: neutral, never struck.
    sources_cf = pool.confident_text_cf
    kinds: list[str] = []
    for t, _s, _e in tokens:
        norm = _RUN_EDGE.sub("", normalize_for_verbatim(t)).casefold()
        if not norm:
            kinds.append("neutral")  # punctuation token
        elif any(norm in text for text in sources_cf):
            kinds.append("verbatim")
        else:
            kinds.append("altered")
    if "altered" not in kinds:
        # Every word is present yet the phrase is absent as written (a reordering
        # or splice): strike the whole phrase, honestly.
        return [(core, "altered")]

    # Tile `core` exactly. A gap between two tokens is struck only when BOTH
    # neighbours are struck, so consecutive fabricated words read as one
    # continuous strike rather than a choppy word-by-word one.
    parts: list[tuple[str, str]] = []
    prev_end = 0
    prev_kind: str | None = None
    for (_t, s, e), kind in zip(tokens, kinds):
        if s > prev_end:
            gap_kind = "altered" if (prev_kind == "altered" and kind == "altered") else "neutral"
            parts.append((core[prev_end:s], gap_kind))
        parts.append((core[s:e], kind))
        prev_end = e
        prev_kind = kind
    if prev_end < len(core):
        parts.append((core[prev_end:], "neutral"))

    merged: list[tuple[str, str]] = []
    for text, kind in parts:
        if merged and merged[-1][1] == kind:
            merged[-1] = (merged[-1][0] + text, kind)
        else:
            merged.append((text, kind))
    return merged


def _build_quote_segments(
    quote: str, decisions: list[tuple[str, bool]], pool: NormalizedSourcePool
) -> tuple[QuoteSegment, ...]:
    """Tile the ORIGINAL quote into ordered render segments for the autopsy panel.

    Only called for an ``altered`` quote. Each checked phrase is located in the
    original text by a forward scan; a ``verbatim`` phrase renders as ink, a
    fabricated phrase is decomposed to WORD level (`_word_level_spans`) so only
    the invented words are struck, not the whole sentence. Everything between the
    checked phrases (the author's edit marks, connecting prose) is ``neutral``.
    The forward cursor keeps the tiling monotonic, and any gap or trailing
    remainder is emitted as ``neutral``, so the segments always concatenate back
    to the exact original quote (locked by a test). A phrase the scan cannot
    locate (it should always be a substring) is simply skipped: its characters
    fall into a neutral gap, so the concatenation invariant still holds and the
    worst case is an under-struck phrase, never a corrupted quote.
    """
    segments: list[QuoteSegment] = []
    cursor = 0
    for phrase, present in decisions:
        core = phrase.strip()
        if not core:
            continue
        idx = quote.find(core, cursor)
        if idx == -1:
            continue
        if idx > cursor:
            segments.append(QuoteSegment(text=quote[cursor:idx], kind="neutral"))
        if present:
            segments.append(QuoteSegment(text=core, kind="verbatim"))
        else:
            for sub_text, kind in _word_level_spans(core, pool):
                segments.append(QuoteSegment(text=sub_text, kind=kind))
        cursor = idx + len(core)
    if cursor < len(quote):
        segments.append(QuoteSegment(text=quote[cursor:], kind="neutral"))
    return tuple(segments)


def check_quote_against_pool(quote: str, pool: NormalizedSourcePool) -> QuoteCheckResult:
    """Check one quoted span against a pre-normalized source pool.

    The matching contract is identical to `check_quote_against_sources`; this split
    only hoists the source normalization out of the per-quote loop. Each run is first
    split into its distinct quoted phrases (the greedy span regex merges two quotes in
    one paragraph into a single run; the connecting prose between them is the author's
    own and is never matched), and each phrase may flex the case of its leading letter
    (the mid-sentence embedding convention). A phrase is satisfied if it is
    verbatim-present in ANY source. The quote is ``altered`` only if some phrase is
    present in NO source AND no truncated-or-partial source could plausibly contain it;
    in the latter case it degrades to ``unplaceable``.

    Disposition is unchanged from the v1 early-return: evaluating EVERY phrase
    (rather than returning on the first absent one) is what lets us tile the
    quote into genuine/fabricated ``segments`` for the autopsy panel, and it is
    provably equivalent because the confident-source guard
    (``norm_confident and not has_uncertain_source``) is a pool-level constant,
    independent of WHICH phrase first failed. The `tests.test_quote_check`
    parity suite and the frozen held-out cases lock that equivalence.
    """
    runs = tuple(split_runs(quote))
    if not pool.has_sources or not runs:
        return QuoteCheckResult(quote=quote, altered=False, unplaceable=True, runs=runs)

    def _phrase_present(phrase: str) -> bool:
        for variant in first_letter_variants(phrase):
            norm_variant = normalize_for_verbatim(variant)
            if not norm_variant:
                return True  # vacuous: nothing checkable in this phrase
            if any(norm_variant in n for n in pool.norm_all):
                return True
        return False

    # One pass over every checked phrase, recording presence in document order.
    # `decisions` holds the ORIGINAL phrase text (for locating it back in the
    # quote) paired with whether it is verbatim-present in the pool.
    decisions: list[tuple[str, bool]] = []
    for run in runs:
        for phrase in quoted_subphrases(run):
            stripped = phrase.strip()
            if not stripped or not _HAS_ALNUM.search(stripped):
                continue  # vacuous phrase: not a checked unit, no segment
            decisions.append((phrase, _phrase_present(stripped)))

    any_absent = any(not present for _, present in decisions)
    confident = bool(pool.norm_confident) and not pool.has_uncertain_source
    if not any_absent:
        altered, unplaceable = False, False
    elif confident:
        altered, unplaceable = True, False
    else:
        altered, unplaceable = False, True

    segments = _build_quote_segments(quote, decisions, pool) if altered else ()
    return QuoteCheckResult(
        quote=quote,
        altered=altered,
        unplaceable=unplaceable,
        runs=runs,
        segments=segments,
    )


# --- Adverse-frame demotion (Q1) --------------------------------------------
#
# Verbatim PRESENCE is not faithful QUOTATION. A lawyer can quote words that
# appear in the cited source only inside a frame that REJECTS or merely
# ATTRIBUTES the quoted proposition -- "Appellant argued that '<quote>'; the
# court rejected that contention." The engine's verbatim check greens on
# presence and cannot see that the source denies the proposition, so it must
# DEMOTE such a quote from `verified` to could_not_check.
#
# This is refuse-leaning and creates NO new green path: it only downgrades a
# would-be verified quote. Over-refusal is the failure mode to avoid, because a
# clean-source verbatim quote is one of ADR-0013's provably-safe green anchors.
# Two guards keep it conservative:
#   1. It fires only when EVERY located occurrence of the quoted span in a
#      confident source is adverse-framed; a single clean occurrence keeps the
#      quote verified.
#   2. If the span cannot be located contiguously in any confident source (a
#      spliced / ellipsis-bridged quote), it does NOT demote -- it cannot read
#      the frame, so it declines to refuse rather than guess (a documented
#      residual, matching the truncation-variant residual).
# All detection runs on the already-normalized confident-source pool: no source
# text crosses any new boundary, so the zero-egress posture is unchanged.

# The authority DISAPPROVING a proposition (rejected / reversed / found wanting).
_REJECTION = re.compile(
    r"\b(?:reject\w*|declin\w*|refus\w*|disagree\w*|unpersuasive|unavailing|"
    r"meritless|without\s+merit|no\s+merit|not\s+persuaded|err\w*|erroneous|"
    r"overrul\w*|revers\w*|vacat\w*|abrogat\w*|repudiat\w*|disapprov\w*|"
    r"untenable|dismiss\w*)\b",
    re.I,
)

# The quoted clause is ATTRIBUTED to an advocate -- an argument, not the court's
# own statement: "<argue|contend|the contention> that '<quote>'". Anchored to
# the END of the governing prefix so the attribution word must directly
# introduce the quote's own "that"-clause (not a sibling clause elsewhere).
_ATTRIB_INTRO = re.compile(
    r"\b(?:argu\w*|contend\w*|contention|assert\w*|assertion|alleg\w*|allegation|"
    r"claim\w*|urg\w*|maintain\w*|posit\w*|insist\w*|submit\w*|submission|"
    r"suggest\w*|theor\w*|hypothe\w*|proposition|premise|notion|position|view)"
    r"\s+that[\s\"'“”(]*$",
    re.I,
)

# The quoted clause is the OBJECT of an authority-proposition noun that a
# rejection in the SAME clause disapproves: "overrule the ... holding that
# '<quote>'", "erred in holding that '<quote>'".
_AUTH_PROP_INTRO = re.compile(
    r"\b(?:holding|ruling|finding|conclusion|proposition|premise|doctrine|"
    r"notion|view|theory|rule)\s+that[\s\"'“”(]*$",
    re.I,
)

# The authority verb governing the quote is NEGATED or declined: "did not hold
# that '<quote>'", "declined to find that '<quote>'". The negation IS the
# rejection, so no separate rejection marker is required.
_NEG_AUTHORITY = re.compile(
    r"(?:\b(?:did|do|does|would|could|can|will|is|was|were|are|has|have|had|shall)"
    r"\b\s+)?\b(?:not|never|n't)\b\s+(?:\w+\s+){0,2}?"
    r"(?:hold|held|rule|ruled|find|found|conclude\w*|decide\w*|agree\w*|accept\w*|"
    r"say|said|state\w*|reason\w*)\s+that[\s\"'“”(]*$"
    r"|\b(?:declin\w*|refus\w*|fail\w*)\s+to\s+"
    r"(?:hold|rule|find|conclude|agree|accept|recognize)\w*\s+that[\s\"'“”(]*$",
    re.I,
)

# A non-binding voice (a dissent / concurrence) advancing the proposition.
_DISSENT = re.compile(r"\b(?:dissent\w*|concurr\w*)\b", re.I)

# The court ADOPTING a proposition (its own conclusion, however introduced): an
# adopted argument is not adverse, even when the same sentence rejects something
# ELSE. Vetoes the attribution path so "accepted the contention that '<quote>',
# and rejected the laches defense" (a court-adopted quote) stays verified, and so
# does a quote whose argument was rejected below but affirmed on appeal.
_ADOPTION = re.compile(
    r"\b(?:accept\w*|agree\w*|adopt\w*|credit\w*|embrac\w*|endors\w*|approve\w*|"
    r"uph(?:o|e)ld\w*|affirm\w*|sustain\w*)\b",
    re.I,
)

# A noun naming the ADVOCACY the quote is the content of. The attribution path
# demotes only when a rejection lands on advocacy language (this is what the
# rejection is ABOUT): "rejected that CONTENTION", "this ARGUMENT is
# unpersuasive", "the CLAIM that '<quote>' is without merit". Bare "harmless-
# error" / "dismissed for want of jurisdiction" carry no advocacy noun, so they
# no longer over-refuse a faithful attributed quote.
_ARG_NOUN = re.compile(
    r"\b(?:argument|arguments|contention|contentions|claim|claims|assertion|"
    r"assertions|allegation|allegations|theory|theories|position|positions|view|"
    r"views|notion|notions|proposition|propositions|premise|premises|"
    r"submission|submissions)\b",
    re.I,
)

# Coordinating / subordinating breaks: the governing prefix is what remains
# AFTER the last of these before the quote, so a rejection of a SIBLING clause
# ("rejected the fraud claim but held that '<quote>'") never taints the quote's
# own clause.
_CLAUSE_BREAK = re.compile(
    r";|,|\bbut\b|\byet\b|\bhowever\b|\balthough\b|\bwhereas\b|\bwhile\b", re.I
)

# A sentence terminator on normalized (whitespace-collapsed) source text.
_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*(?=\s|$)")

# Abbreviations whose trailing period is NOT a sentence boundary. Without this,
# "did not, per Corp. Inc., hold that '<quote>'" splits at "Corp."/"Inc." and the
# negation is severed from the quote's sentence, so a genuinely negated-authority
# quote silently escapes demotion. Matched case-insensitively on the word before
# the period.
_ABBREVIATIONS = frozenset(
    "corp inc ltd co llc llp plc no nos vs v id ibid mr mrs ms dr st st jr sr "
    "art arts sec secs cf eg ie etc al ex rev ed dept assn bros u.s".split()
)

# Bound on the source text inspected on EACH side of an occurrence when reading
# its frame. The frame signals (attribution / negation / rejection of the
# advocacy, the following sentence) are all LOCAL to the quote; a real sentence
# is far shorter than this. Capping the window makes the per-occurrence cost
# O(1) in the source size, so a pathological single-"sentence" paste with
# thousands of anchor repeats can no longer drive quadratic work (CWE-1333 /
# CWE-407): the whole scan stays linear in the source length.
_FRAME_WINDOW = 800

# Defense-in-depth occurrence budget (CWE-770): a genuine cited source never
# repeats the SAME quoted span thousands of times. Past this many occurrences the
# input is pathological (a DoS-shaped paste), so the detector stops assessing and
# declines to demote -- the same over-refusal-safe direction it takes for an
# unreadable frame. This caps the total per-request frame work regardless of
# source size, independent of the adapter's sentence-pair ceiling (which counts
# sentences, not repeats, so a single-"sentence" repeat-pad slips under it).
_MAX_OCCURRENCES = 2_000


def _governing_prefix(pre_quote: str) -> str:
    """The clause that directly introduces the quote: the tail of the pre-quote
    text after the last clause-break token. Keeps a sibling clause's rejection
    from being read as governing THIS quote (the over-refusal guard for
    'rejected X but held that "<quote>"')."""
    last = 0
    for m in _CLAUSE_BREAK.finditer(pre_quote):
        last = m.end()
    return pre_quote[last:]


def _is_sentence_end(text: str, term_start: int) -> bool:
    """True when the terminator at ``term_start`` in ``text`` really ends a
    sentence (not an abbreviation's period like 'Corp.' or 'v.')."""
    if text[term_start] != ".":
        return True  # ! and ? are never abbreviation marks
    before = text[:term_start]
    word = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
    return not (word and word.group(1).lower().strip(".") in _ABBREVIATIONS)


def _sentence_and_next(source: str, start: int, end: int) -> tuple[str, str, str]:
    """Return (pre_quote, sentence, next_sentence) for an occurrence [start,end).

    ``sentence`` is the whole sentence containing the occurrence (semicolons and
    commas are kept INSIDE it, so a rejection after a semicolon still counts);
    ``pre_quote`` is the sentence text before the occurrence; ``next_sentence``
    is the following sentence (an attributed argument is often rejected in the
    NEXT sentence: 'X argued that "..." We reject that contention.').

    Only a BOUNDED window (``_FRAME_WINDOW`` chars each side) is inspected, so the
    cost is independent of the source length -- the frame is always local to the
    quote. Sentence boundaries are abbreviation-aware so a mid-sentence 'Corp.'
    does not sever the frame."""
    lo = max(0, start - _FRAME_WINDOW)
    hi = min(len(source), end + _FRAME_WINDOW)

    # Sentence start: just after the last real terminator in the left window.
    sent_start = lo
    for m in _SENTENCE_END.finditer(source, lo, start):
        if _is_sentence_end(source, m.start()):
            sent_start = m.end()

    # Sentence end + next-sentence end: the first two real terminators at/after
    # the occurrence, within the right window.
    sent_end = hi
    next_end = hi
    seen_current = False
    for m in _SENTENCE_END.finditer(source, end, hi):
        if not _is_sentence_end(source, m.start()):
            continue
        if not seen_current:
            sent_end = m.end()
            seen_current = True
        else:
            next_end = m.end()
            break

    pre_quote = source[sent_start:start]
    sentence = source[sent_start:sent_end].strip()
    next_sentence = source[sent_end:next_end].strip() if seen_current else ""
    return pre_quote, sentence, next_sentence


def _occurrence_is_adverse(pre_quote: str, sentence: str, next_sentence: str) -> bool:
    """True when this occurrence of the quote sits in a rejecting / attributing
    frame. See the module note for the family of frames and the over-refusal
    guards."""
    gov = _governing_prefix(pre_quote)
    # A negated / declined authority verb governing the quote: the negation is
    # itself the rejection ("did not hold that '<quote>'").
    if _NEG_AUTHORITY.search(gov):
        return True
    # An attributed argument whose ADVOCACY is rejected. The rejection must land
    # on advocacy language (an argument/contention/claim...) in the same or the
    # next sentence, and the court must not have ADOPTED it (an adopted argument,
    # or one rejected-below-but-affirmed, is the court's own conclusion). This
    # binds the rejection to the quoted proposition rather than to any incidental
    # rejection word elsewhere in the sentence.
    zone = f"{sentence} {next_sentence}"
    if (
        _ATTRIB_INTRO.search(gov)
        and not _ADOPTION.search(zone)
        and _REJECTION.search(zone)
        and _ARG_NOUN.search(zone)
    ):
        return True
    # The quote is the OBJECT of an authority-proposition noun disapproved in the
    # SAME clause ("overrule the holding that '<quote>'", "erred in holding that").
    if _AUTH_PROP_INTRO.search(gov) and _REJECTION.search(gov):
        return True
    # A non-binding voice advancing the proposition against a disagreeing court.
    if _DISSENT.search(gov) and _REJECTION.search(sentence):
        return True
    return False


def quote_adverse_framed(quote: str, pool: NormalizedSourcePool) -> bool:
    """True when a would-be `verified` quote must DEMOTE to could_not_check.

    The quote is located in the confident-source pool by its longest contiguous
    anchor (the whole span, else its longest edit-split run), leading-letter
    case flexed exactly as the presence check flexes it. It is adverse only when
    that anchor is located AND every one of its occurrences is adverse-framed;
    one clean occurrence, or an unlocatable (spliced) span, keeps it verified.
    Pure; reads only the pre-normalized confident pool.

    Cost is linear in the confident-source length: locating an anchor is one
    ``finditer`` pass, and each occurrence's frame is read from a bounded window
    (``_sentence_and_next``), so a large or repeat-padded source cannot drive
    superlinear work. The scan short-circuits on the first clean occurrence."""
    confident = pool.norm_confident
    if not confident:
        return False

    anchors: list[str] = []
    for variant in first_letter_variants(quote or ""):
        norm = normalize_for_verbatim(variant)
        if norm:
            anchors.append(norm)
    for run in split_runs(quote or ""):
        for variant in first_letter_variants(run):
            norm = normalize_for_verbatim(variant)
            if norm:
                anchors.append(norm)
    # Longest first: assess the most substantive contiguous anchor that appears,
    # so a short incidental sub-run occurring elsewhere never drives the verdict.
    for anchor in sorted(dict.fromkeys(anchors), key=len, reverse=True):
        located = False
        examined = 0
        for source in confident:
            for m in re.finditer(re.escape(anchor), source, re.I):
                examined += 1
                if examined > _MAX_OCCURRENCES:
                    return False  # pathological repeat-pad: decline to assess
                located = True
                pre_quote, sentence, next_sentence = _sentence_and_next(source, m.start(), m.end())
                if not _occurrence_is_adverse(pre_quote, sentence, next_sentence):
                    return False  # a clean occurrence exists: the quote stands
        if located:
            return True  # located, and every occurrence was adverse-framed
    return False  # nothing located contiguously: cannot read the frame, do not refuse


def check_quote_against_sources(quote: str, sources: list) -> QuoteCheckResult:
    """Check one quoted span against a pool of candidate sources.

    `sources` may be raw strings (treated as complete + untruncated) or
    `SourceText` records carrying truncation/completeness. Each run is first
    split into its distinct quoted phrases (the greedy span regex merges two
    quotes in one paragraph into a single run; the connecting prose between them
    is the author's own and is never matched), and each phrase may flex the case
    of its leading letter (the mid-sentence embedding convention). A phrase is
    satisfied if it is verbatim-present in ANY source (a brief may quote across
    several cited chunks/opinions). The quote is ``altered`` only if some phrase
    is present in NO source AND no truncated-or-partial source could plausibly
    contain it; in the latter case it degrades to ``unplaceable``. A quote the
    tool could not fully see is never called altered. These acceptances mirror
    the sentence-level check in deterministic_envelope exactly, so the panel and
    the claim card can never disagree about the same quoted words.

    Single-shot convenience wrapper: prepares the pool then checks one quote. The
    brief-level panel uses `prepare_source_pool` once and `check_quote_against_pool`
    per quote to avoid re-normalizing the shared pool for every span.
    """
    return check_quote_against_pool(quote, prepare_source_pool(sources))
