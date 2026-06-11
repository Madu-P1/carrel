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
class QuoteCheckResult:
    """Verdict for one quoted span extracted from the draft.

    ``altered`` True means at least one verbatim run is absent from every source
    we could fully and confidently see: a real alteration or fabrication.
    ``unplaceable`` True means the tool could not honestly check this quote (no
    source available, the run fell past a truncation, or the only candidates
    were partial chunks the run might straddle); the caller maps this to
    could_not_check, NEVER to a flag. ``runs`` is the parsed verbatim runs.
    """

    quote: str
    altered: bool
    unplaceable: bool
    runs: tuple[str, ...]


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
    """
    runs = tuple(split_runs(quote))
    usable = _coerce_sources(sources)
    if not usable or not runs:
        return QuoteCheckResult(quote=quote, altered=False, unplaceable=True, runs=runs)

    # Normalize each source ONCE (perf [8]); keep the confident-source subset
    # (complete AND untruncated) separate, since only those can ground an
    # `altered` verdict. The presence of any partial/truncated source means an
    # absent run degrades to could_not_check instead of altered.
    norm_all = [normalize_for_verbatim(strip_footnote_calls(s.text)) for s in usable]
    norm_confident = [n for n, s in zip(norm_all, usable) if s.complete and not s.truncated and n]
    has_uncertain_source = any((s.truncated or not s.complete) for s in usable)

    def _phrase_present(phrase: str) -> bool:
        for variant in first_letter_variants(phrase):
            norm_variant = normalize_for_verbatim(variant)
            if not norm_variant:
                return True  # vacuous: nothing checkable in this phrase
            if any(norm_variant in n for n in norm_all):
                return True
        return False

    for run in runs:
        for phrase in quoted_subphrases(run):
            phrase = phrase.strip()
            if not phrase or not _HAS_ALNUM.search(phrase):
                continue
            if _phrase_present(phrase):
                continue  # found verbatim somewhere: this phrase is clean
            # Absent from every source. Only call it altered if we have a
            # confident (complete, untruncated) source it SHOULD have appeared
            # in and there is no uncertain source that could plausibly contain it.
            if norm_confident and not has_uncertain_source:
                return QuoteCheckResult(quote=quote, altered=True, unplaceable=False, runs=runs)
            return QuoteCheckResult(quote=quote, altered=False, unplaceable=True, runs=runs)

    return QuoteCheckResult(quote=quote, altered=False, unplaceable=False, runs=runs)
