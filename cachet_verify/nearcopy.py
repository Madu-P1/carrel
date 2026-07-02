"""Near-copy flip detection — negation and proper-noun swaps, deterministically.

Shared verbatim between the Codex kernel (``cachet_verify/nearcopy.py``) and
the companion (``cachet_companion/verify/nearcopy.py``); keep the two copies
byte-identical, like the conformance corpus.

The gap this closes (live smoke, 2026-07-02): a paraphrased polarity flip
("inherently equal" for the source's "inherently unequal") and a proper-noun
swap ("State of New York" for the source's "State of Delaware") both carried
no parametric anchor, so the engines refused. Both are catchable without
semantics: in a sentence that is token-for-token identical to a source
sentence EXCEPT for one contiguous run, a negation-morphology difference or a
proper-noun substitution is a provable contradiction — the skeleton IS the
proof, exactly as it is for the parametric near-copy comparison.

The honesty disciplines, stricter than the parametric ones because there is
no numeric anchor to lean on:

- **Single-run gate.** Everything outside ONE contiguous token run must match
  exactly (case-insensitively). Two differing runs = not a near-copy = refuse.
- **Only two accusation shapes.** (1) Negation morphology: an inserted or
  removed "not"/"never"/"no", or an un-/non- prefix flip on the same stem
  (stem >= 4 chars, known non-negating pairs excluded). (2) A proper-noun
  swap where EVERY differing token on BOTH sides is proper-noun-shaped and
  the run is not sentence-initial. A plain word substitution — a synonym, a
  verb change — NEVER accuses (the G4 discipline: fine/penalty must refuse).
- **Rhetorical "not" never accuses.** "not only/just/merely" is emphasis, not
  negation; its insertion or removal refuses.
- **Abbreviation-shaped pairs never accuse.** "Del." vs "Delaware" is a
  formatting variant, not a swap.
- **The elsewhere guard.** A swapped-in proper noun that ALSO appears
  elsewhere in the source demotes to could_not_check — the claim may be
  referencing that other clause (mirrors the parametric value-absence rule).
- **Stated + contradicted = refuse.** If any source sentence states the claim
  verbatim while another near-copy contradicts it, the sources disagree, and
  the engine never picks a winner (the kernel's same-fact-disagreement veto).
- **Context floor.** An accusation needs at least 4 shared context tokens and
  a 5-token claim; a verbatim confirmation needs a 4-token claim. Below that
  there is not enough skeleton to call anything a near-copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
# Strip non-word characters from token EDGES only (quotes, commas, periods,
# brackets); interior characters (hyphens, apostrophes, dots in "U.S.") stay.
_EDGE_STRIP = re.compile(r"^\W+|\W+$", re.UNICODE)
# Proper-noun-shaped: leading uppercase letter, then letters / hyphen /
# apostrophe / interior dots ("New", "York", "McKinsey", "U.S", "IBM").
_PROPER = re.compile(r"[A-Z][A-Za-z'’.\-]*$")

_NEGATION_TOKENS = frozenset({"not", "never", "no"})
# "not only met the deadline" is emphasis, not negation of "met the deadline".
_RHETORICAL_AFTER_NOT = frozenset({"only", "just", "merely"})
# un-/non- pairs where the prefix does NOT negate (or is too treacherous to
# rule on): refuse rather than accuse.
_NON_NEGATING_PAIRS = frozenset(
    {
        ("unloosen", "loosen"),
        ("unravel", "ravel"),
        ("unthaw", "thaw"),
        ("unless", "less"),
    }
)
# Fixed-pair negations that are neither insertions nor prefix flips.
_FIXED_NEGATION_PAIRS = frozenset({("cannot", "can"), ("without", "with")})

_MIN_CLAIM_TOKENS_ACCUSE = 5
_MIN_CONTEXT_TOKENS_ACCUSE = 4
_MIN_CLAIM_TOKENS_CONFIRM = 4


@dataclass(frozen=True)
class NearCopyVerdict:
    state: str  # verified | altered | could_not_check
    detail: str
    subject: str


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.split():
        core = _EDGE_STRIP.sub("", raw)
        if core:
            out.append(core)
    return out


def _single_run_diff(a: list[str], b: list[str]) -> tuple[int, int, int] | None:
    """Longest-common-prefix/suffix diff. Returns (p, a_end, b_end) so the
    differing runs are a[p:a_end] and b[p:b_end], or None when the sequences
    are identical (no run at all)."""
    p = 0
    while p < len(a) and p < len(b) and a[p] == b[p]:
        p += 1
    s = 0
    while s < len(a) - p and s < len(b) - p and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1
    if p == len(a) == len(b):
        return None
    return p, len(a) - s, len(b) - s


def _negation_flip(
    claim_run: list[str],
    src_run: list[str],
    claim_folded: list[str],
    src_folded: list[str],
    p: int,
) -> str | None:
    """A detail string when the single-run diff is a negation flip; None
    otherwise. Never accuses on rhetorical or known non-negating shapes."""
    # Insertion/removal of a lone negation token.
    for run, other_folded, inserted_in_claim in (
        (claim_run, src_folded, True),
        (src_run, claim_folded, False),
    ):
        opposite = src_run if inserted_in_claim else claim_run
        if len(run) == 1 and not opposite and run[0].casefold() in _NEGATION_TOKENS:
            word = run[0].casefold()
            # The token AFTER the negation, in the side that carries it: when
            # it is rhetorical ("not only"), refuse.
            carrier = claim_folded if inserted_in_claim else src_folded
            if word == "not" and p + 1 < len(carrier) and carrier[p + 1] in _RHETORICAL_AFTER_NOT:
                return None
            if inserted_in_claim:
                return (
                    f"The claim inserts a negation ('{word}') absent from the "
                    "loaded source, in an otherwise near-verbatim sentence."
                )
            return (
                f"The claim omits the loaded source's negation ('{word}') "
                "in an otherwise near-verbatim sentence."
            )
    # One-token substitution: prefix negation or a fixed negation pair. An
    # a/an article pair may ride along ("an exclusive" vs "a non-exclusive"):
    # English article agreement changes with the prefix, so the flip
    # surfaces as a two-token run whose first tokens are both articles.
    sub_claim, sub_src = claim_run, src_run
    if (
        len(claim_run) == 2
        and len(src_run) == 2
        and {claim_run[0].casefold(), src_run[0].casefold()} <= {"a", "an"}
    ):
        sub_claim, sub_src = claim_run[1:], src_run[1:]
    if len(sub_claim) == 1 and len(sub_src) == 1:
        x, y = sub_claim[0].casefold(), sub_src[0].casefold()
        for a, b in ((x, y), (y, x)):
            if (a, b) in _NON_NEGATING_PAIRS:
                return None
            if (a, b) in _FIXED_NEGATION_PAIRS:
                return (
                    f"The claim states '{x}' where the loaded source states "
                    f"'{y}'; the polarity is inverted in an otherwise "
                    "near-verbatim sentence."
                )
            dehyphenated = a.replace("-", "")
            for prefix in ("un", "non"):
                if (
                    dehyphenated == prefix + b
                    and len(b) >= 4
                    and (dehyphenated, b) not in _NON_NEGATING_PAIRS
                ):
                    return (
                        f"The claim states '{x}' where the loaded source "
                        f"states '{y}'; the polarity is inverted in an "
                        "otherwise near-verbatim sentence."
                    )
    return None


def _proper_noun_swap(
    claim_run: list[str], src_run: list[str], p: int, source_text: str
) -> NearCopyVerdict | None:
    """An altered verdict when the single-run diff is a proper-noun
    substitution, a could_not_check when the swapped-in noun also lives
    elsewhere in the source, None when the shape does not qualify."""
    if not claim_run or not src_run:
        return None
    if p == 0:
        # Sentence-initial capitalization is not a proper-noun signal.
        return None
    if not all(_PROPER.fullmatch(t) for t in claim_run + src_run):
        return None
    if len(claim_run) == 1 and len(src_run) == 1:
        a = claim_run[0].replace(".", "").casefold()
        b = src_run[0].replace(".", "").casefold()
        if a.startswith(b) or b.startswith(a):
            # Abbreviation / truncation variant ("Del." vs "Delaware"):
            # a formatting difference, never a swap.
            return None
    claim_surface = " ".join(claim_run)
    src_surface = " ".join(src_run)
    pattern = re.compile(r"(?<!\w)" + re.escape(claim_surface) + r"(?!\w)", re.IGNORECASE)
    if pattern.search(source_text):
        return NearCopyVerdict(
            "could_not_check",
            f"The claim names {claim_surface} where this source sentence "
            f"names {src_surface}, but {claim_surface} also appears "
            "elsewhere in the source, so the claim may reference that "
            "other statement.",
            claim_surface,
        )
    return NearCopyVerdict(
        "altered",
        f"The claim names {claim_surface}; the loaded source names "
        f"{src_surface}, in an otherwise near-verbatim sentence.",
        claim_surface,
    )


def verify_near_copy_flip(claim: str, source: str) -> NearCopyVerdict | None:
    """Verify an (anchor-free) claim against a source by near-copy token
    comparison. Returns None when no source sentence is a near-copy of the
    claim (nothing to rule on); otherwise verified (verbatim restatement),
    altered (negation flip / proper-noun swap), or could_not_check (the
    sources both state and contradict the claim, or a swap demoted by the
    elsewhere guard)."""
    if not claim or not source:
        return None
    claim_tokens = _tokens(claim)
    if len(claim_tokens) < _MIN_CLAIM_TOKENS_CONFIRM:
        return None
    claim_folded = [t.casefold() for t in claim_tokens]

    restated = False
    contradiction: NearCopyVerdict | None = None
    demoted: NearCopyVerdict | None = None

    for sentence in filter(None, (s.strip() for s in _SENTENCE_SPLIT.split(source))):
        src_tokens = _tokens(sentence)
        if not src_tokens:
            continue
        src_folded = [t.casefold() for t in src_tokens]
        diff = _single_run_diff(claim_folded, src_folded)
        if diff is None:
            restated = True
            continue
        if contradiction is not None:
            continue
        p, a_end, b_end = diff
        context = p + (len(claim_folded) - a_end)
        if len(claim_tokens) < _MIN_CLAIM_TOKENS_ACCUSE or context < _MIN_CONTEXT_TOKENS_ACCUSE:
            continue
        claim_run = claim_tokens[p:a_end]
        src_run = src_tokens[p:b_end]
        negation_detail = _negation_flip(claim_run, src_run, claim_folded, src_folded, p)
        if negation_detail is not None:
            contradiction = NearCopyVerdict(
                "altered",
                negation_detail,
                " ".join(claim_run) or " ".join(src_run),
            )
            continue
        swap = _proper_noun_swap(claim_run, src_run, p, source)
        if swap is not None:
            if swap.state == "altered":
                contradiction = swap
            elif demoted is None:
                demoted = swap

    if restated and contradiction is not None:
        return NearCopyVerdict(
            "could_not_check",
            "the sources both state and contradict this claim; refusing to pick a winner",
            claim,
        )
    if contradiction is not None:
        return contradiction
    if restated:
        return NearCopyVerdict("verified", "a source states this claim verbatim", claim)
    return demoted
