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

from dataclasses import dataclass

from eyecite import get_citations
from eyecite.models import FullCaseCitation, FullLawCitation


@dataclass(frozen=True)
class CitationRef:
    """One full citation located in a source string.

    ``start``/``end`` are character offsets into the text passed to
    :func:`find_citations`, so ``text[start:end] == matched_text``.
    """

    matched_text: str
    start: int
    end: int
    kind: str  # "case" | "law"
    volume: str | None
    reporter: str | None
    page: str | None
    parenthetical: str | None


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
        refs.append(
            CitationRef(
                matched_text=cite.matched_text(),
                start=start,
                end=end,
                kind=kind,
                volume=groups.get("volume"),
                reporter=groups.get("reporter"),
                page=groups.get("page"),
                parenthetical=getattr(cite.metadata, "parenthetical", None),
            )
        )
    return refs


def has_citation(text: str) -> bool:
    """True if ``text`` contains a full case- or law-citation."""
    return bool(find_citations(text))
