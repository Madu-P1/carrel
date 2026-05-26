"""Per-claim case-existence verification (Carrel V2 Stage 1).

The tutor produces a grounded answer made of claims, each backed by
zero or more in-corpus citations. The V2 verifier adds a second
verdict layer specifically for legal claims: when a claim's text
contains a Bluebook-shape case citation, check whether that case
exists on CourtListener and surface the result alongside the
in-corpus citation.

This module is the thin coordinator between the tutor and the
CourtListener client:

  tutor -> verify_claims_for_cases(claim_texts) -> list[ClaimCaseVerdict]

It cheaply skips the network when the claim text obviously contains
no citation-shaped substring (the API has a 60/min rate cap and
costs latency we never want to pay for non-legal corpora).

Per CLAUDE.md "no silent AI fallbacks": when CourtListener is
unconfigured or unreachable, the per-claim verdict carries an
explicit `ok=False` + error_code rather than degrading to "case
verified" or omitting the verdict. The verifier UX shows the
operator exactly what state the verification is in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import httpx

from .courtlistener import (
    CitationCluster,
    CitationHit,
    CourtListenerResult,
    lookup_citations_in_text,
)

# Conservative pre-filter for "does this string plausibly contain a
# case citation?". Bluebook case cites carry the shape
# "<volume> <Reporter> <page>" — e.g. "576 U.S. 644", "410 F.3d 138",
# "5 U.S. (1 Cranch) 137". The regex matches "<digits> <Token-cased
# token> <digits>" with whitespace between, which catches the
# overwhelming majority of US federal + state reporters without
# requiring a Bluebook-aware parser. False positives are cheap (one
# CourtListener call returns 404), false negatives skip a legitimate
# cite (worse — so we keep the regex broad).
_CITATION_SHAPE = re.compile(r"\b\d{1,4}\s+[A-Z][A-Za-z\.\s\(\)]{1,40}\s+\d{1,5}\b")


@dataclass(frozen=True)
class CaseVerdict:
    """One per-cite verdict the verifier surfaces back to the operator.

    `citation` is the literal substring that CourtListener detected
    in the claim text (post-normalization may differ — see
    `normalized_citation`). `exists` is the binary headline; the UX
    can drill into `status` for the nuanced cases (300 = ambiguous,
    404 = not found, 400 = malformed).
    """

    citation: str
    normalized_citation: str | None
    status: int
    exists: bool
    case_name: str | None
    absolute_url: str | None
    court: str | None
    date_filed: str | None
    error_message: str | None


@dataclass(frozen=True)
class ClaimCaseVerdict:
    """Verification verdict batch for one claim's text.

    `ok=True` and an empty `verdicts` list means the claim text was
    scanned, CourtListener was reachable, and no citation-shape
    substrings matched the API's parser. `ok=False` means the
    verification itself failed (no token, network error, rate
    limited) and the operator should be told so they don't read
    silence as "verified".
    """

    claim_index: int
    ok: bool
    verdicts: tuple[CaseVerdict, ...]
    error_code: str | None
    error_message: str | None


def _looks_like_legal_text(text: str) -> bool:
    """Cheap pre-filter to skip non-legal claim texts.

    Returns True if `_CITATION_SHAPE` finds anything — a single
    plausible citation triggers the full lookup. The shape is loose
    on purpose: any positive that turns out to be non-legal will
    come back as status=400/404 from CourtListener, which is
    correct behavior. The pre-filter exists only to keep tutor
    latency at zero on corpora with no legal content (the dominant
    case for the existing study-tool flow).
    """
    if not text or not text.strip():
        return False
    return _CITATION_SHAPE.search(text) is not None


def _first_cluster(clusters: Sequence[CitationCluster]) -> CitationCluster | None:
    return clusters[0] if clusters else None


def _verdict_from_hit(hit: CitationHit) -> CaseVerdict:
    cluster = _first_cluster(hit.clusters)
    normalized = hit.normalized_citations[0] if hit.normalized_citations else None
    return CaseVerdict(
        citation=hit.citation,
        normalized_citation=normalized,
        status=hit.status,
        exists=hit.exists,
        case_name=cluster.case_name if cluster else None,
        absolute_url=cluster.absolute_url if cluster else None,
        court=cluster.court if cluster else None,
        date_filed=cluster.date_filed if cluster else None,
        error_message=hit.error_message or None,
    )


def _failure_verdict(
    claim_index: int,
    result: CourtListenerResult,
) -> ClaimCaseVerdict:
    return ClaimCaseVerdict(
        claim_index=claim_index,
        ok=False,
        verdicts=(),
        error_code=result.error_code,
        error_message=result.error_message,
    )


def verify_claims_for_cases(
    claim_texts: Sequence[str],
    *,
    client: httpx.Client | None = None,
) -> list[ClaimCaseVerdict]:
    """Run CourtListener verification on every claim that plausibly
    contains a case citation; emit a per-claim verdict batch.

    Claims with no citation-shape substring are emitted as
    `ok=True, verdicts=()` — they were scanned, nothing legal to
    verify. That is the dominant case for the existing study-tool
    flow and stays cheap (zero network).

    Optional `client` is forwarded to the CourtListener client so a
    single httpx connection can be reused across the per-claim
    loop. Callers that omit it pay the one-shot per call cost — fine
    for the typical 1-5 cites in a tutor response.
    """
    results: list[ClaimCaseVerdict] = []
    for index, raw_text in enumerate(claim_texts):
        text = (raw_text or "").strip()
        if not _looks_like_legal_text(text):
            results.append(
                ClaimCaseVerdict(
                    claim_index=index,
                    ok=True,
                    verdicts=(),
                    error_code=None,
                    error_message=None,
                )
            )
            continue
        lookup = lookup_citations_in_text(text, client=client)
        if not lookup.ok:
            results.append(_failure_verdict(index, lookup))
            continue
        verdicts = tuple(_verdict_from_hit(hit) for hit in lookup.hits)
        results.append(
            ClaimCaseVerdict(
                claim_index=index,
                ok=True,
                verdicts=verdicts,
                error_code=None,
                error_message=None,
            )
        )
    return results
