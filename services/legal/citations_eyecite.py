"""eyecite-backed citation detection (Cachet deterministic engine).

Replaces the digit-blind ``_CITATION_SHAPE`` pre-filter in
``case_verification`` with eyecite, which catches reporters whose
abbreviation contains a digit (``F.3d``, ``F.Supp.2d``, ``Cal.4th``,
``N.Y.2d``) that the old regex silently missed.

Honesty tier T0 (pure deterministic, no AI): eyecite resolves
citations with an Aho-Corasick scan over the static ``reporters-db``
tables plus regex extraction. No learned weights, no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from eyecite import get_citations
from eyecite.models import FullCaseCitation, FullLawCitation


@dataclass(frozen=True)
class CitationRef:
    """One full citation located in a source string.

    ``start``/``end`` are character offsets into the text passed to
    :func:`find_citations`, so ``text[start:end] == matched_text``.
    ``plaintiff``/``defendant`` are the party names eyecite read from the
    draft text around the citation (None when the draft gives no caption).
    ``corrected`` is eyecite's normalized reporter form of the cite (e.g.
    the official "347 U. S. 483" spacing folds to "347 U.S. 483", and a
    pincite/year is dropped), so a corpus or API keyed on the canonical
    form resolves regardless of the draft's spacing. Falls back to
    ``matched_text`` if eyecite cannot produce a corrected form.
    """

    matched_text: str
    start: int
    end: int
    kind: str  # "case" | "law"
    volume: str | None
    reporter: str | None
    page: str | None
    parenthetical: str | None
    plaintiff: str | None = None
    defendant: str | None = None
    corrected: str | None = None
    # The year eyecite read from the cite's court-year parenthetical ("(1954)",
    # "(9th Cir. 1996)"), None when the draft gives none. Compared against the
    # resolved case's date_filed so a real number cited with a wrong year does
    # not read verified.
    year: int | None = None
    # eyecite's court id for the cite (courts-db ids, the same id-space
    # CourtListener uses: "scotus", "ca9"). From the parenthetical when given,
    # else inferred from the reporter; None when neither determines it.
    court: str | None = None


def find_citations(text: str) -> list[CitationRef]:
    """Return the full case- and law-citations in ``text``.

    Only ``FullCaseCitation``/``FullLawCitation`` are returned (the
    cites carrying a reporter + volume + page that CourtListener can
    resolve); short forms (``id.``/``supra``) and unknown tokens are
    skipped.
    """
    if not text or not text.strip():
        return []
    refs: list[CitationRef] = []
    for cite in get_citations(text):
        if isinstance(cite, FullCaseCitation):
            kind = "case"
        elif isinstance(cite, FullLawCitation):
            kind = "law"
        else:
            continue
        start, end = cite.span()
        groups = cite.groups or {}
        matched = cite.matched_text()
        try:
            corrected = cite.corrected_citation() or None
        except Exception:  # pragma: no cover - defensive: never fail a lookup on normalize
            corrected = None
        refs.append(
            CitationRef(
                matched_text=matched,
                start=start,
                end=end,
                kind=kind,
                volume=groups.get("volume"),
                reporter=groups.get("reporter"),
                page=groups.get("page"),
                parenthetical=getattr(cite.metadata, "parenthetical", None),
                plaintiff=getattr(cite.metadata, "plaintiff", None),
                defendant=getattr(cite.metadata, "defendant", None),
                corrected=corrected or matched,
                year=_coerce_year(getattr(cite.metadata, "year", None)),
                court=getattr(cite.metadata, "court", None) or None,
            )
        )
    return refs


def _coerce_year(value: object) -> int | None:
    """eyecite's metadata.year as an int, or None when absent/unparseable."""
    try:
        year = int(str(value))
    except (TypeError, ValueError):
        return None
    return year if 1000 <= year <= 9999 else None


def has_citation(text: str) -> bool:
    """True if ``text`` contains a full case- or law-citation."""
    return bool(find_citations(text))


_CAPTION_CONNECTIVES = {"the", "and", "for", "vs"}


def caption_tokens(text: str) -> set[str]:
    """Significant lowercase word tokens of a case caption (drops connectives)."""
    if not text:
        return set()
    raw = re.split(r"[^a-z0-9]+", text.lower())
    return {t for t in raw if len(t) >= 3 and t not in _CAPTION_CONNECTIVES}


def caption_token_info(text: str) -> list[tuple[str, bool]]:
    """``(token, is_abbrev)`` for the significant tokens of a caption.

    ``is_abbrev`` is True when the token is immediately followed by ``.`` or ``'``
    in the source (``Educ.``, ``Dep't``, ``Comm'n``), the signal that it is an
    abbreviation eligible for prefix/table matching. A plain surname carries no such
    mark and must match EXACTLY, so a fabricated party that merely prefixes a real
    token ("Boar" vs "board", "Educ" with no period vs "education") is not treated
    as an abbreviation and is correctly flagged.
    """
    if not text:
        return []
    low = text.lower()
    out: list[tuple[str, bool]] = []
    for m in re.finditer(r"[a-z0-9]+", low):
        tok = m.group(0)
        if len(tok) < 3 or tok in _CAPTION_CONNECTIVES:
            continue
        out.append((tok, low[m.end() : m.end() + 1] in (".", "'")))
    return out


# Legal abbreviations that are consonant skeletons, not prefixes, of their
# expansion (Bluebook T6). Matched in BOTH directions but only as EXACT lookups,
# never fuzzy, so a real abbreviated caption ("Mfg." for "Manufacturing") matches
# while a fabricated party that merely shares a subsequence ("bard" vs "board")
# does not.
_ABBREV = {
    "mfg": "manufacturing",
    "twp": "township",
    "bros": "brothers",
    "dept": "department",
    "mgmt": "management",
    "bldg": "building",
    "natl": "national",
    "intl": "international",
    "assn": "association",
    "dist": "district",
    "rr": "railroad",
    "svcs": "services",
    "comms": "communications",
}


def _marked_abbrev_prefix(short: str, long: str) -> bool:
    """A marked abbreviation token is a prefix of its expansion ONLY when it is a
    substantial truncation.

    "educ"->"education" (ratio 0.44) qualifies; "brow"->"brown" (0.80) or
    "boar"->"board" (0.80) does NOT -- a near-equal prefix is a coincidental
    collision (a fabricated party that merely added a period), not an abbreviation.
    Real legal abbreviations cluster at ratio <= 0.5 (dist./district = 0.5,
    corp./corporation = 0.36); 0.6 is a safe ceiling.
    """
    return len(short) >= 3 and long.startswith(short) and len(short) < 0.6 * len(long)


def _tokens_compatible(
    draft: str, draft_abbrev: bool, resolved: str, resolved_abbrev: bool
) -> bool:
    """True if a draft caption token plausibly denotes a resolved case-name token.

    Exact match always counts. Prefix and curated-abbreviation matching are GATED on
    the abbreviation mark (a trailing ``.`` or apostrophe in the source) AND, for
    prefixes, on a substantial-truncation ratio: only a marked token that is a real
    abbreviation matches by prefix ("educ."->"education") or table
    ("mfg."->"manufacturing"). A plain unmarked surname, or a near-equal marked
    prefix ("Brow." vs "Brown"), must match exactly, so a fabricated party is NOT
    compatible and the fabricated caption is flagged. Either side may carry the mark,
    since the reporter's name may itself be abbreviated ("Bhd. of Educ.").
    """
    if draft == resolved:
        return True
    if draft_abbrev and _marked_abbrev_prefix(draft, resolved):
        return True
    if resolved_abbrev and _marked_abbrev_prefix(resolved, draft):
        return True
    if draft_abbrev and _ABBREV.get(draft) == resolved:
        return True
    if resolved_abbrev and _ABBREV.get(resolved) == draft:
        return True
    return False


def _acronym_forms(case_name: str) -> set[str]:
    """Initialisms a draft token may legitimately use for the resolved name.

    Built from every contiguous run (length 2..6) of the resolved name's words,
    in two variants: all words, and significant words only (connectives like
    "of" dropped), because Bluebook initialisms sometimes keep the connective
    letter and sometimes drop it. Pure string work, no table to maintain: "NLRB"
    falls out of "National Labor Relations Board" without an entry.
    """
    lowered = case_name.lower()
    all_words = re.findall(r"[a-z0-9]+", lowered)
    significant = [w for w in all_words if w not in _CAPTION_CONNECTIVES and w != "v"]
    forms: set[str] = set()
    for words in (all_words, significant):
        for start in range(len(words)):
            for end in range(start + 2, min(start + 6, len(words)) + 1):
                forms.add("".join(w[0] for w in words[start:end]))
    return forms


# Dotted single-letter initials ("U.S.", "M.L.B.", "N. L. R. B."): the only
# short-token caption shape eligible for the initialism carve-out in
# caption_match_state.
_DOTTED_INITIALS = re.compile(r"(?:[A-Za-z]\.[\s-]*)+")


def _letters_of(text: str) -> str:
    """The side's letters, lowercased and joined ("M.L.B." -> "mlb")."""
    return "".join(re.findall(r"[A-Za-z]", text)).lower()


_CAPS_RUN = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")


def _caps_tokens(text: str) -> set[str]:
    """Lowercase forms of the tokens written in ALL CAPS in the source text.

    Only these earn initialism credit in :func:`caption_match_state`. An
    initialism is written in caps ("NLRB", "SEC"); a mixed-case surname that
    coincidentally spells one ("Fat" against "First American Title") is a party
    name and must match exactly, never by acronym. The dotted form ("N.L.R.B.")
    needs no credit: it tokenizes to single letters, which leaves its side
    vacuous already.
    """
    return {m.group(0).lower() for m in _CAPS_RUN.finditer(text or "")}


def caption_match_state(ref: CitationRef, case_name: str) -> str:
    """How the draft's caption relates to the resolved case: ``match`` /
    ``unconfirmed`` / ``mismatch``.

    Per-side rule: EVERY populated caption side (plaintiff, defendant) must land
    at least one token compatible with the resolved name. The old any-token rule
    let "Smith v. Board" pass on Brown's number off the single generic token
    "board"; under this rule that caption is ``unconfirmed``: one side names a
    real party, the other names nobody in the resolved caption. Unconfirmed is
    the refusal state, never the accusation: the odd side may be a short form
    the tool cannot prove, so the caller downgrades to could-not-check rather
    than flagging. ``mismatch`` (the hard flag) is unchanged from the old rule:
    no draft token anywhere is compatible with the resolved name.

    Compatibility per token pair is :func:`_tokens_compatible` (exact for plain
    surnames, prefix/table only for marked abbreviations), plus initialism
    forms of the resolved name ("NLRB" for "National Labor Relations Board"),
    so the stricter per-side rule does not false-flag initialism captions.
    Initialism credit is restricted to tokens written in ALL CAPS in the draft
    (:func:`_caps_tokens`): a mixed-case surname that coincidentally spells an
    initialism ("Fat" against "First American Title") is a party name and gets
    no credit.

    A side whose letters all tokenize away (sub-3-char tokens: dotted initials
    "M.L.B.", two-letter surnames "Ng") is UNVERIFIABLE, not vacuous, unless it
    is dotted single-letter initials that spell an initialism of the resolved
    name ("U.S." for "United States ..."): an unverifiable side caps the result
    at ``unconfirmed`` even when the other side matches, because "Ng v. Board"
    on Brown's number must never out-rank "Smith v. Board" (refusal, never the
    accusation, and never a bless). A caption with no letters at all is a
    ``match``: a bare citation is never punished for what it does not say.
    """
    raw_sides = [ref.plaintiff or "", ref.defendant or ""]
    sides = [(caption_token_info(raw), _caps_tokens(raw)) for raw in raw_sides]
    populated = [(tokens, caps) for tokens, caps in sides if tokens]
    resolved = caption_token_info(case_name)
    if not resolved:
        # The resolved name itself yields no significant tokens (a real
        # initials-caption case like "M. L. B. v. S. L. J."): nothing to
        # compare against, so the draft's caption is never punished.
        return "match"
    acronyms = _acronym_forms(case_name)
    # Letter-bearing sides that tokenized to nothing. Dotted single-letter
    # initials whose letters spell an initialism of the resolved name ("U.S."
    # -> "us" for "United States v. Carolene Products Co.") stay vacuous; any
    # other letter-bearing short-token side ("Ng", "M.L.B." against Brown) is
    # unverifiable and caps the result at the refusal below.
    unverifiable = [
        raw
        for raw, (tokens, _caps) in zip(raw_sides, sides)
        if not tokens
        and re.search(r"[A-Za-z]", raw)
        and not (_DOTTED_INITIALS.fullmatch(raw.strip()) and _letters_of(raw) in acronyms)
    ]
    if not populated:
        if unverifiable:
            return "unconfirmed"
        return "match"

    def _side_matches(side: list[tuple[str, bool]], caps: set[str]) -> bool:
        return any(
            _tokens_compatible(d, d_ab, r, r_ab) for d, d_ab in side for r, r_ab in resolved
        ) or any(token in acronyms and token in caps for token, _abbrev in side)

    results = [_side_matches(side, caps) for side, caps in populated]
    if all(results):
        return "unconfirmed" if unverifiable else "match"
    if any(results):
        return "unconfirmed"
    return "mismatch"


def caption_matches(ref: CitationRef, case_name: str) -> bool:
    """True unless the draft's caption is a hard mismatch for the resolved case.

    Back-compat predicate over :func:`caption_match_state`: an abbreviated real
    caption ("Bd. of Educ." for "Board of Education") is never falsely flagged,
    while a fabricated caption on a real reporter number ("Fake v. Nobody", or
    the subtler "Boar v. Nook" / "Brownstein v. Zelman" on Brown's number)
    shares no compatible token and IS flagged. The intermediate ``unconfirmed``
    state (one side matches, one does not) also returns True here; callers that
    can render a refusal should use :func:`caption_match_state` directly and
    downgrade unconfirmed captions to could-not-check.
    """
    return caption_match_state(ref, case_name) != "mismatch"
