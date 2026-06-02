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

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import httpx

from ai.providers import AIProvider, get_default_provider
from ai.router import ClaudeCallResult
from app_logging import get_logger, log_event

from .courtlistener import (
    CitationCluster,
    CitationHit,
    CourtListenerResult,
    OpinionTextResult,
    fetch_opinion_text,
    lookup_citations_in_text,
)

LOGGER = get_logger("einstein.legal.case_verification")

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

    Carrel V2 half-2 holding-match fields surface a per-cite
    verdict on whether the cited opinion actually supports the
    claim text. Populated only when `exists` is True (status 200)
    and the opinion-text fetch + Claude verifier succeeded.
    `holding_match` is the headline: True = supports, False =
    contradicts/unrelated, None = not run or could not decide.
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
    holding_match: bool | None = None
    holding_concern: str | None = None
    holding_excerpt: str | None = None
    holding_error: str | None = None


@dataclass(frozen=True)
class HoldingMatchVerdict:
    """Result of running the Claude verifier on (claim, opinion text).

    `ok=True` and `supports=True/False` is a decided verdict.
    `ok=True` + `supports=None` means the model ran but explicitly
    refused to decide (e.g. claim is too vague to compare). `ok=False`
    means the verifier itself failed (no provider configured, model
    error, malformed tool response).
    """

    ok: bool
    supports: bool | None
    concern: str | None
    excerpt: str | None
    error_code: str | None
    error_message: str | None


_HOLDING_MATCH_SYSTEM_PROMPT = """\
You are an independent verifier. The user is auditing a draft text
that cites a court opinion. You will receive (1) the claim the user
made and (2) text from the cited opinion. Your only job is to
decide whether the opinion text supports the claim.

Decide carefully. A claim is supported only when the opinion text
actually says what the claim asserts about the case. Mere topical
relevance is not support. If the opinion text is too short to
decide or the relevant passage is not present in the excerpt
provided, return supports=null and explain in `concern`.

You must respond by calling the submit_holding_match tool.
""".strip()


_HOLDING_MATCH_TOOL: dict[str, Any] = {
    "name": "submit_holding_match",
    "description": (
        "Submit a structured verdict on whether the cited opinion text supports the user's claim."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "supports": {
                "type": ["boolean", "null"],
                "description": (
                    "True iff the opinion text directly supports the claim. "
                    "False iff the opinion text contradicts the claim or is "
                    "clearly unrelated. Null iff the excerpt is insufficient "
                    "to decide."
                ),
            },
            "concern": {
                "type": "string",
                "description": (
                    "Short reasoning (1-3 sentences) explaining the verdict. "
                    "When supports=false or null, name the specific gap."
                ),
            },
            "excerpt": {
                "type": "string",
                "description": (
                    "The most relevant verbatim passage from the opinion "
                    "text that the verdict rests on. Up to 240 characters. "
                    "Empty string when the verdict is null with no anchor."
                ),
            },
        },
        "required": ["supports", "concern", "excerpt"],
    },
}


def _holding_match_user_prompt(
    claim_text: str,
    case_name: str | None,
    citation: str,
    opinion_text: str,
) -> str:
    case_label = case_name or "the cited case"
    return (
        f"<claim>{claim_text.strip()}</claim>\n"
        f"<cited_case>{case_label} ({citation})</cited_case>\n"
        f"<opinion_text>\n{opinion_text.strip()}\n</opinion_text>"
    )


def check_holding_match(
    claim_text: str,
    case_name: str | None,
    citation: str,
    opinion_text: str,
    *,
    provider: AIProvider | None = None,
) -> HoldingMatchVerdict:
    """Run the Claude verifier on (claim_text, opinion_text).

    Returns `ok=False` only when the call itself failed (no
    provider, model error). A successful call with `supports=None`
    means the model ran and explicitly refused to decide — surfaced
    as "ambiguous" by the UX, not as "supports". Per CLAUDE.md "no
    silent AI fallbacks": every failure mode emits an error_code so
    the UX can show "Holding check unavailable" rather than
    silently treating the cite as verified.
    """
    cleaned_claim = (claim_text or "").strip()
    cleaned_opinion = (opinion_text or "").strip()
    if not cleaned_claim:
        return HoldingMatchVerdict(
            ok=False,
            supports=None,
            concern=None,
            excerpt=None,
            error_code="holding_match_no_claim",
            error_message="Claim text is empty.",
        )
    if not cleaned_opinion:
        return HoldingMatchVerdict(
            ok=False,
            supports=None,
            concern=None,
            excerpt=None,
            error_code="holding_match_no_opinion_text",
            error_message="Opinion text is empty.",
        )

    active_provider = provider or get_default_provider()
    if not hasattr(active_provider, "request_tool_call"):
        return HoldingMatchVerdict(
            ok=False,
            supports=None,
            concern=None,
            excerpt=None,
            error_code="holding_match_no_tool_call_provider",
            error_message=("Active AI provider does not support structured tool calls."),
        )

    user_prompt = _holding_match_user_prompt(cleaned_claim, case_name, citation, cleaned_opinion)
    try:
        result: ClaudeCallResult = active_provider.request_tool_call(
            request_kind="legal.holding_match",
            system=_HOLDING_MATCH_SYSTEM_PROMPT,
            prompt=user_prompt,
            tool=_HOLDING_MATCH_TOOL,
            max_tokens=600,
            task="balanced",
        )
    except Exception as exc:
        log_event(
            LOGGER,
            logging.WARNING,
            "holding_match_call_raised",
            error_class=exc.__class__.__name__,
        )
        return HoldingMatchVerdict(
            ok=False,
            supports=None,
            concern=None,
            excerpt=None,
            error_code="holding_match_call_raised",
            error_message=f"Verifier call raised: {exc.__class__.__name__}",
        )

    if not result.ok or not isinstance(result.json_payload, dict):
        return HoldingMatchVerdict(
            ok=False,
            supports=None,
            concern=None,
            excerpt=None,
            error_code=result.error_code or "holding_match_no_payload",
            error_message=(result.error_message or "Verifier returned no structured payload."),
        )

    payload = result.json_payload
    supports_raw = payload.get("supports")
    if isinstance(supports_raw, bool):
        supports: bool | None = supports_raw
    elif supports_raw is None:
        supports = None
    else:
        supports = None
    concern = str(payload.get("concern") or "").strip() or None
    excerpt = str(payload.get("excerpt") or "").strip() or None
    return HoldingMatchVerdict(
        ok=True,
        supports=supports,
        concern=concern,
        excerpt=excerpt,
        error_code=None,
        error_message=None,
    )


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


def _verdict_from_hit(
    hit: CitationHit,
    *,
    claim_text: str,
    http_client: httpx.Client | None,
    ai_provider: AIProvider | None,
    enable_holding_match: bool,
) -> CaseVerdict:
    """Build the per-cite verdict and, when the cite exists, run the
    holding-match follow-up (fetch opinion text + Claude verifier).

    Holding-match is only attempted when:
      - `enable_holding_match` is True (caller can pin it off for
        cheap "did this case exist?" runs);
      - `hit.exists` is True (status=200, single match);
      - the cluster has at least one `sub_opinions` URI to fetch.

    Failure modes (no token, fetch error, no provider, model error)
    populate `holding_error` so the UX renders "Holding check
    unavailable" rather than silently treating the cite as
    verified-and-supported.
    """
    cluster = _first_cluster(hit.clusters)
    normalized = hit.normalized_citations[0] if hit.normalized_citations else None
    base_kwargs = {
        "citation": hit.citation,
        "normalized_citation": normalized,
        "status": hit.status,
        "exists": hit.exists,
        "case_name": cluster.case_name if cluster else None,
        "absolute_url": cluster.absolute_url if cluster else None,
        "court": cluster.court if cluster else None,
        "date_filed": cluster.date_filed if cluster else None,
        "error_message": hit.error_message or None,
    }

    if not enable_holding_match or not hit.exists or cluster is None:
        return CaseVerdict(**base_kwargs)
    if not cluster.sub_opinions:
        return CaseVerdict(
            **base_kwargs,
            holding_error="no_sub_opinions",
        )

    opinion_uri = cluster.sub_opinions[0]
    opinion = fetch_opinion_text(opinion_uri, client=http_client)
    if not opinion.ok:
        return CaseVerdict(
            **base_kwargs,
            holding_error=opinion.error_code,
        )

    verdict = check_holding_match(
        claim_text=claim_text,
        case_name=cluster.case_name or None,
        citation=hit.citation,
        opinion_text=opinion.text,
        provider=ai_provider,
    )
    if not verdict.ok:
        return CaseVerdict(
            **base_kwargs,
            holding_error=verdict.error_code,
        )
    return CaseVerdict(
        **base_kwargs,
        holding_match=verdict.supports,
        holding_concern=verdict.concern,
        holding_excerpt=verdict.excerpt,
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


def verify_claims_for_cases_steps(
    claim_texts: Sequence[str],
    *,
    client: httpx.Client | None = None,
    ai_provider: AIProvider | None = None,
    enable_holding_match: bool = True,
) -> Iterator[ClaimCaseVerdict]:
    """Streaming variant of `verify_claims_for_cases`.

    Yields each per-claim `ClaimCaseVerdict` the moment its CourtListener
    lookup (and, when enabled, the per-cite holding-match follow-up)
    completes. This is the genuinely slow, sequential work the Verify
    surface streams so the operator watches the labor happen rather than
    staring at a spinner. `verify_claims_for_cases` drains this into the
    eager list it has always returned, so non-streaming callers are
    byte-for-byte unaffected.
    """
    for index, raw_text in enumerate(claim_texts):
        text = (raw_text or "").strip()
        if not _looks_like_legal_text(text):
            yield ClaimCaseVerdict(
                claim_index=index,
                ok=True,
                verdicts=(),
                error_code=None,
                error_message=None,
            )
            continue
        lookup = lookup_citations_in_text(text, client=client)
        if not lookup.ok:
            yield _failure_verdict(index, lookup)
            continue
        verdicts = tuple(
            _verdict_from_hit(
                hit,
                claim_text=text,
                http_client=client,
                ai_provider=ai_provider,
                enable_holding_match=enable_holding_match,
            )
            for hit in lookup.hits
        )
        yield ClaimCaseVerdict(
            claim_index=index,
            ok=True,
            verdicts=verdicts,
            error_code=None,
            error_message=None,
        )


def verify_claims_for_cases(
    claim_texts: Sequence[str],
    *,
    client: httpx.Client | None = None,
    ai_provider: AIProvider | None = None,
    enable_holding_match: bool = True,
) -> list[ClaimCaseVerdict]:
    """Run CourtListener verification on every claim that plausibly
    contains a case citation; emit a per-claim verdict batch.

    When `enable_holding_match` is True (default) and a cite returns
    status=200 (single match), the verifier also follows up with
    `fetch_opinion_text` + `check_holding_match` so each verdict
    carries `holding_match` / `holding_concern` / `holding_excerpt`
    (or `holding_error` when the follow-up fails). Pin
    `enable_holding_match=False` to run a cheaper "did this case
    exist?" pass without the LLM call.

    Claims with no citation-shape substring are emitted as
    `ok=True, verdicts=()` — they were scanned, nothing legal to
    verify. That is the dominant case for the existing study-tool
    flow and stays cheap (zero network).

    Optional `client` is forwarded to the CourtListener client so a
    single httpx connection is reused across the per-claim loop
    AND the per-cite opinion fetches. `ai_provider` defaults to
    `get_default_provider()` lazily inside the holding-match step.
    """
    return list(
        verify_claims_for_cases_steps(
            claim_texts,
            client=client,
            ai_provider=ai_provider,
            enable_holding_match=enable_holding_match,
        )
    )
