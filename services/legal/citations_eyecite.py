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
            )
        )
    return refs


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


def caption_matches(ref: CitationRef, case_name: str) -> bool:
    """True if the draft's party names plausibly name the resolved case.

    A draft caption matches if any significant draft token is
    :func:`_tokens_compatible` with any resolved token, so an abbreviated real
    caption ("Bd. of Educ." for "Board of Education") is never falsely flagged,
    while a fabricated caption on a real reporter number ("Fake v. Nobody", or the
    subtler "Boar v. Nook" / "Brownstein v. Zelman" on Brown's number) shares no
    compatible token and IS flagged. Compatibility is exact for plain surnames and
    only loosens (prefix/abbreviation table) for tokens explicitly marked as
    abbreviations, because for a filing-grade tool a fabricated caption reading as
    verified is the malpractice direction. Returns True when the draft carries no
    caption to compare, so a bare citation is never treated as a mismatch.
    """
    drafted = caption_token_info(ref.plaintiff or "") + caption_token_info(ref.defendant or "")
    resolved = caption_token_info(case_name)
    if not drafted or not resolved:
        return True
    return any(_tokens_compatible(d, d_ab, r, r_ab) for d, d_ab in drafted for r, r_ab in resolved)
