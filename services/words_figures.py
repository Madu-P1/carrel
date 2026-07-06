"""Words-vs-figures conflict detector for the Cachet deterministic engine.

Legal drafting states one number two ways, bound by adjacency: a spelled-out
cardinal immediately restated as a parenthetical numeral ("thirty (30) days",
"Five Thousand Dollars ($5,000)"). When the two surfaces disagree, the
document contradicts itself inside a single span, and the disagreement is a
literal fact a reader can confirm at a glance. This module detects that
disagreement and stops. It never applies the resolution doctrine (UCC 3-114:
words control over figures); it names both values and refuses to pick a
winner. Design and verdict shapes follow
docs/proposals/2026-07-06-held-claim-type-proposal.md.

Campaign invariants, enforced by construction:

* SILENT on consistent input. A pair whose word value equals its figure value
  produces NO finding. There is no supported/verified/green output state
  anywhere in this module -- `WordsFiguresFinding.__post_init__` rejects any
  verdict outside {"contradicted", "could_not_verify"} -- so a false green is
  impossible structurally, not by tuning.
* SILENT unless the pair unambiguously denominates the SAME fact. A spelled
  cardinal immediately before a bare-integer parenthetical is not enough on
  its own: "Section thirty (40)", "Article five (40)", "Schedule twelve (5)"
  are structural cross-references, not a quantity restated twice, and firing
  on them would be a false accusation. `_DENOMINATION_CUE_EXCLUDE` refuses
  (silently, no finding at all) any site whose word run is immediately
  preceded by a cross-reference cue word (Section/Article/Clause/Paragraph/
  Schedule/Exhibit/Appendix/Part/Annex/Rule/Chapter/Item/Recital/
  Attachment/Addendum). Over-restriction here only costs a silent site, never
  a wrong accusation -- the same structural argument that kept the SI-2
  defined-term-unused check loud through three adversary rounds.
* Every contradiction and every refusal names its own figures verbatim
  (the spelled words, the parenthetical text, and the parsed integers),
  never a content-free message.
* A conflicted pair the SOURCE carries verbatim is the source's defect, not
  the drafter's: it yields `could_not_verify` locating the conflict in the
  source. Callers may pass an explicit `verbatim_run_present` flag; otherwise
  the check runs the engine's own
  `cachet_verify.engine.validators.verbatim_run_present` against `source`.
* Ambiguity refuses, never guesses: a spelled number outside the bounded
  grammar, a parenthetical that is not a bare unambiguously grouped integer,
  or a dollars/no-dollars unit mismatch each yield `could_not_verify` naming
  the exact unparsed token.

Word-to-number parsing is an explicit closed-vocabulary table plus a finite
automaton (`_WORD_UNITS` / `_WORD_TENS` / `_WORD_SCALES` and
`_word_run_value`); there is no fuzzy matching. Anything the grammar does not
accept is refused by name. Pure stdlib plus one existing pure-string engine
helper; no network, no LLM, no I/O anywhere in the call path.

    from services.words_figures import check_words_figures

    findings = check_words_figures(claim_text, source_text)
    for finding in findings:
        print(finding.verdict, finding.detail)   # names both figures, always
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from cachet_verify.engine.validators import (
    verbatim_run_present as _engine_verbatim_run_present,
)

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "PairSite",
    "WordsFiguresFinding",
    "check_words_figures",
    "find_pair_sites",
]

# The ONLY verdicts this detector can emit. There is deliberately no
# supported/verified member: on a consistent pair the detector emits nothing.
CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

# --- The auditable word-to-number table (closed vocabulary; no fuzz) --------

_WORD_UNITS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

_WORD_TENS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_WORD_SCALES: dict[str, int] = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}

_HUNDRED = "hundred"
_DOLLAR_UNITS = frozenset({"dollar", "dollars", "usd"})

# Words that mark a number-word run for DETECTION but are outside the parsing
# grammar ("one and a half million" must be located so it can be refused by
# name rather than silently skipped -- the proposal's example 3).
_DETECT_ONLY = frozenset({"and", "a", "half", "quarter", "quarters", "halves"})

_CARDINAL_WORDS = (
    frozenset(_WORD_UNITS) | frozenset(_WORD_TENS) | {_HUNDRED} | frozenset(_WORD_SCALES)
)
_DETECT_WORDS = _CARDINAL_WORDS | _DOLLAR_UNITS | _DETECT_ONLY

# Cross-reference cue words that mark a SECTION/ARTICLE/SCHEDULE NUMBER, not a
# quantity. "Section thirty (40) of the Lease" is a mis-set structural
# reference (or a typo), never a restated fact; the pair check must refuse to
# denominate it as a conflict. Checked as the single token immediately before
# the word run (case-insensitive); over-restriction here only costs a silent
# site, never a wrong accusation.
_DENOMINATION_CUE_EXCLUDE = frozenset(
    {
        "section",
        "sections",
        "article",
        "articles",
        "clause",
        "clauses",
        "paragraph",
        "paragraphs",
        "subsection",
        "subsections",
        "schedule",
        "schedules",
        "exhibit",
        "exhibits",
        "appendix",
        "appendices",
        "part",
        "parts",
        "annex",
        "annexes",
        "rule",
        "rules",
        "chapter",
        "chapters",
        "item",
        "items",
        "recital",
        "recitals",
        "attachment",
        "attachments",
        "addendum",
        "addenda",
        "footnote",
        "footnotes",
    }
)
_PRECEDING_TOKEN_RE = re.compile(r"([A-Za-z]+)\s*$")

# --- Site location -----------------------------------------------------------

# A candidate site is a run of 1..8 vocabulary words (space- or hyphen-joined)
# immediately followed by a short parenthetical. Longest-alternative-first so
# the regex never truncates a word ("seventeen" before "seven"). All
# quantifiers are bounded (CWE-1333 hardening; see the kernel ReDoS fix).
_WORD_ALT = "|".join(sorted(_DETECT_WORDS, key=len, reverse=True))
_SITE_RE = re.compile(
    rf"\b(?P<words>(?:(?:{_WORD_ALT})[ -]){{0,7}}(?:{_WORD_ALT}))\s{{0,2}}"
    r"\((?P<paren>[^()\n]{1,40})\)",
    re.IGNORECASE,
)

# A bare integer parenthetical: optional $, then plain digits or digits with
# STRICT thousands grouping. "5,000" parses; "3,0" does not (ambiguous
# grouping is refused by name, mirroring `parse_grouped_number`'s stance).
_BARE_INT_RE = re.compile(r"^(?P<dollar>\$)?\s{0,2}(?P<digits>\d{1,3}(?:,\d{3}){1,6}|\d{1,15})$")

# A single numeric-looking token that is NOT a bare integer (decimal, percent,
# ordinal suffix, malformed grouping). Adjacent to a number-word run this is a
# refusal that names the token; anything else in a parenthetical ("as defined
# in Section 3", "2 of 14") is not a site at all and stays silent.
_NUMERIC_TOKEN_RE = re.compile(r"^\$?\d[\d,.]{0,20}%?(?:st|nd|rd|th)?$", re.IGNORECASE)

_MAX_TEXT_FOR_PAIRS = 2_000_000  # DoS bound, structural_integrity precedent


@dataclass(frozen=True)
class PairSite:
    """One located words+parenthetical pair, both sides parsed (or refused)."""

    span: str  # the full matched surface, e.g. "thirty (40)"
    start: int
    end: int
    word_text: str  # the spelled-out run, verbatim from the input
    paren_text: str  # the parenthetical content, verbatim, without parens
    word_value: int | None  # None = run outside the bounded grammar
    figure_value: int | None  # None = parenthetical refused (not a bare int)
    word_is_dollars: bool
    figure_is_dollars: bool


@dataclass(frozen=True)
class WordsFiguresFinding:
    """One verdict this detector adds. Never a green one.

    `__post_init__` makes the zero-green invariant structural: constructing a
    finding with any verdict outside `ALLOWED_VERDICTS` raises, so no code
    path in (or importing) this module can mint a supported/verified state
    from it.
    """

    verdict: str  # "contradicted" | "could_not_verify", nothing else
    kind: str  # words_figures_conflict | words_figures_unparsed |
    #            words_figures_source_defect | words_figures_unit_mismatch
    detail: str  # names the pair's own figures verbatim, by construction
    span: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                "words_figures detector can only emit "
                f"{sorted(ALLOWED_VERDICTS)}; got {self.verdict!r}. "
                "It has no green output state by design."
            )


def _sub_thousand(tokens: Sequence[str]) -> int | None:
    """Value of a 1..999 word sequence, or None when outside the grammar.

    Accepted shapes, nothing else: UNIT | TENS | TENS UNIT(1-9) |
    UNIT HUNDRED [TENS | UNIT | TENS UNIT(1-9)]. "and" joiners are outside
    the grammar on purpose: over-restriction only costs a refusal, never a
    wrong value.
    """
    total = 0
    rest = list(tokens)
    if len(rest) >= 2 and rest[0] in _WORD_UNITS and rest[1] == _HUNDRED:
        total = _WORD_UNITS[rest[0]] * 100
        rest = rest[2:]
        if not rest:
            return total
    if not rest:
        return None
    if len(rest) == 1:
        token = rest[0]
        if token in _WORD_TENS:
            return total + _WORD_TENS[token]
        if token in _WORD_UNITS:
            return total + _WORD_UNITS[token]
        return None
    if (
        len(rest) == 2
        and rest[0] in _WORD_TENS
        and rest[1] in _WORD_UNITS
        and _WORD_UNITS[rest[1]] <= 9
    ):
        return total + _WORD_TENS[rest[0]] + _WORD_UNITS[rest[1]]
    return None


def _word_run_value(word_text: str) -> tuple[int | None, bool]:
    """Parse a spelled-out run into (value, is_dollars); value None = refused.

    The automaton over the closed table: [sub-thousand] [SCALE] [DOLLARS].
    Every accepted parse yields exactly one integer; everything else returns
    None so the caller refuses by name instead of guessing.
    """
    tokens = [t for t in re.split(r"[ -]+", word_text.strip().lower()) if t]
    dollars = False
    if tokens and tokens[-1] in _DOLLAR_UNITS:
        dollars = True
        tokens = tokens[:-1]
    if not tokens:
        return None, dollars
    scale = 1
    if tokens[-1] in _WORD_SCALES:
        scale = _WORD_SCALES[tokens[-1]]
        tokens = tokens[:-1]
        if not tokens:
            return None, dollars
    value = _sub_thousand(tokens)
    if value is None:
        return None, dollars
    return value * scale, dollars


def _paren_value(paren_text: str) -> tuple[int | None, bool, bool]:
    """Classify a parenthetical: (value, has_dollar, is_numeric_token).

    value is an int only for a bare, unambiguously grouped integer. A single
    numeric-looking token that is not one (decimal, ordinal, "3,0") returns
    (None, ..., True) so it can be refused by name. Anything else returns
    (None, False, False): not a site.
    """
    text = paren_text.strip()
    match = _BARE_INT_RE.match(text)
    if match:
        return int(match.group("digits").replace(",", "")), bool(match.group("dollar")), True
    if _NUMERIC_TOKEN_RE.match(text):
        return None, text.startswith("$"), True
    return None, False, False


def _preceded_by_denomination_cue(text: str, start: int) -> bool:
    """True iff the token immediately before ``start`` is a cross-reference
    cue word (Section/Article/Schedule/...). Such a site denominates a
    structural identifier, not a quantity restated twice, so the caller must
    stay silent rather than risk a false accusation."""
    match = _PRECEDING_TOKEN_RE.search(text[:start])
    if not match:
        return False
    return match.group(1).lower() in _DENOMINATION_CUE_EXCLUDE


def find_pair_sites(text: str) -> list[PairSite]:
    """Locate every words+parenthetical pair site in `text`, in order.

    A site requires a run containing at least one cardinal word, immediately
    followed by a parenthetical holding a single numeric token. A `$` in the
    parenthetical without a dollars word on the word side is NOT a site (the
    proposal's step-1 rule): the parenthetical may denominate something else,
    and silence is the only safe output. A word run immediately preceded by a
    structural cross-reference cue ("Section", "Article", "Schedule", ...) is
    also not a site: it denominates an identifier, not a restated fact.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT_FOR_PAIRS:
        raise ValueError(f"text exceeds the {_MAX_TEXT_FOR_PAIRS}-char words_figures bound")
    sites: list[PairSite] = []
    for match in _SITE_RE.finditer(text):
        word_text = match.group("words")
        paren_text = match.group("paren").strip()
        tokens = {t for t in re.split(r"[ -]+", word_text.lower()) if t}
        if not tokens & _CARDINAL_WORDS:
            continue  # "dollars (500)" alone is not a number statement
        if _preceded_by_denomination_cue(text, match.start()):
            continue  # "Section thirty (40)": structural reference, not a fact
        figure_value, figure_is_dollars, is_numeric = _paren_value(paren_text)
        if not is_numeric:
            continue  # "(as defined in Section 3)", "(2 of 14)": not a site
        word_value, word_is_dollars = _word_run_value(word_text)
        if figure_is_dollars and not word_is_dollars:
            continue  # "$" allowed only when the words end in a dollars unit
        sites.append(
            PairSite(
                span=match.group(0),
                start=match.start(),
                end=match.end(),
                word_text=word_text,
                paren_text=paren_text,
                word_value=word_value,
                figure_value=figure_value,
                word_is_dollars=word_is_dollars,
                figure_is_dollars=figure_is_dollars,
            )
        )
    return sites


def _refusal_detail(site: PairSite) -> str:
    """A refusal that names the exact unparsed token and the other figure."""
    if site.word_value is None:
        return (
            f"Cannot compute the value of the spelled-out number '{site.word_text}' "
            "with certainty (outside the bounded number-word grammar); the "
            f"parenthetical states '{site.paren_text}'. Review the pair manually."
        )
    return (
        f"Cannot parse the parenthetical figure '{site.paren_text}' with certainty "
        "(not a bare, unambiguously grouped integer); the words state "
        f"'{site.word_text}' (={site.word_value:,}). Review the pair manually."
    )


def check_words_figures(
    claim: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[WordsFiguresFinding]:
    """Check every words+figures pair in `claim`; return only non-green findings.

    Returns `[]` for a claim whose every pair is consistent (or that has no
    pair sites at all): silence is the consistent-input output, and this
    function has no way to say "supported". Per conflicted site:

    * pair NOT verbatim in `source`: `contradicted` -- the claim introduced
      the conflict; the detail names both figures and never says which
      controls.
    * pair verbatim in `source` (per `verbatim_run_present` when explicitly
      passed, else the engine's own normalized-substring check against
      `source`): `could_not_verify` locating the conflict in the source -- a
      faithful copy of a defective source is never blamed on the drafter.
    * either side unparseable, or a dollars word run against a bare non-$
      numeral whose values differ: `could_not_verify` naming the exact token.

    Deterministic: same inputs, same output list, always.
    """
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    findings: list[WordsFiguresFinding] = []
    for site in find_pair_sites(claim):
        if site.word_value is None or site.figure_value is None:
            findings.append(
                WordsFiguresFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="words_figures_unparsed",
                    detail=_refusal_detail(site),
                    span=site.span,
                    start=site.start,
                    end=site.end,
                )
            )
            continue
        if site.word_value == site.figure_value:
            continue  # consistent pair: SILENT, the pipeline is untouched
        if site.word_is_dollars and not site.figure_is_dollars:
            findings.append(
                WordsFiguresFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="words_figures_unit_mismatch",
                    detail=(
                        f"The words '{site.word_text}' state a dollar amount "
                        f"(={site.word_value:,}) but the parenthetical '{site.paren_text}' "
                        f"(={site.figure_value:,}) carries no '$', and the two values "
                        f"differ ({site.word_value:,} vs {site.figure_value:,}). Unit "
                        "mismatch between words and figures; review the pair manually."
                    ),
                    span=site.span,
                    start=site.start,
                    end=site.end,
                )
            )
            continue
        pair_in_source = verbatim_run_present
        if pair_in_source is None:
            pair_in_source = bool(source) and _engine_verbatim_run_present(site.span, source)
        if pair_in_source:
            findings.append(
                WordsFiguresFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="words_figures_source_defect",
                    detail=(
                        f"The words '{site.word_text}' (={site.word_value:,}) and the "
                        f"figure '{site.paren_text}' (={site.figure_value:,}) disagree, "
                        f"and the source carries the same conflicted pair '{site.span}' "
                        "verbatim. The conflict originates in the source, not the "
                        "draft; review which value was intended."
                    ),
                    span=site.span,
                    start=site.start,
                    end=site.end,
                )
            )
            continue
        findings.append(
            WordsFiguresFinding(
                verdict=CONTRADICTED,
                kind="words_figures_conflict",
                detail=(
                    f"The words state '{site.word_text}' (={site.word_value:,}) but the "
                    f"figure reads '{site.paren_text}' (={site.figure_value:,}). The pair "
                    "disagrees inside one span; this document states one obligation two "
                    "ways. The engine does not decide which value controls."
                ),
                span=site.span,
                start=site.start,
                end=site.end,
            )
        )
    return findings
