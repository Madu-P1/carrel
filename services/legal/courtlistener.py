"""CourtListener citation-lookup client (Carrel V2 Stage 1).

The litigation-pre-flight wedge needs to answer "does this cited case
actually exist?" before a brief is filed. CourtListener's free
v4 citation-lookup endpoint takes a block of text (up to 64K chars),
detects Bluebook-shape case citations inside it, and returns per-cite
verdicts: status 200 (found), 300 (ambiguous - multiple matches),
404 (valid format but no record), 400 (malformed reporter), 429
(rate limited).

This module is a thin client; it does NOT classify citations itself
(CourtListener does the detection) and does NOT cache lookups across
runs (V1 — per-call only). Both are deliberate scope cuts for the
first half of the V2 case-existence integration.

Per CLAUDE.md "no silent AI fallbacks": every call returns a typed
`CourtListenerResult` with explicit `ok`, `error_code`, and
`error_message` fields. The hook that consumes this in
`services.legal.case_verification` surfaces those values to the
operator instead of degrading silently to "case verified" on a
network error.

Env contract:
  COURTLISTENER_API_TOKEN — required. Absent → ok=False,
    error_code="courtlistener_no_api_token".
  COURTLISTENER_TIMEOUT_SECONDS — optional, default 8.0.
  COURTLISTENER_BASE_URL — optional, override for tests.

Rate limits (per the public docs):
  60 valid citations per minute (server-enforced; we report 429
    back rather than wrapping with a sleep).
  250 citations per request maximum (text length cap of 64K chars
    saturates well before this; we enforce the char cap client-side).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from app_logging import get_logger, log_event

LOGGER = get_logger("einstein.legal.courtlistener")

_DEFAULT_BASE_URL = "https://www.courtlistener.com"
_DEFAULT_TIMEOUT_SECONDS = 8.0
_MAX_TEXT_CHARS = 64_000


@dataclass(frozen=True)
class CitationCluster:
    """One matched case record returned alongside a citation hit.

    CourtListener returns the full case-law cluster shape in the
    `clusters` array of each response item. The subset surfaced here
    is what the verifier UX needs to render: case name + URL +
    court + filing year. Anything richer (full opinion text, judges,
    citation graph) stays in the raw payload accessible via
    `raw` for callers that need it.
    """

    case_name: str
    absolute_url: str | None
    court: str | None
    date_filed: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CitationHit:
    """One per-citation entry from a citation-lookup response.

    Mirrors the documented response item shape. `status` is the
    HTTP-equivalent code the server returns per citation (200 found,
    300 ambiguous, 404 not found, 400 malformed reporter, 429 rate
    limited). `clusters` is empty unless status is 200 or 300.
    """

    citation: str
    normalized_citations: tuple[str, ...]
    start_index: int
    end_index: int
    status: int
    error_message: str
    clusters: tuple[CitationCluster, ...]

    @property
    def exists(self) -> bool:
        """Convenience: True only when status==200 (single match found).

        Status 300 means multiple cases match — the verdict UX
        should surface that as "ambiguous", not as a confirmed
        existence, so this property returns False there. Callers
        that want "found at all" can check `status in {200, 300}`.
        """
        return self.status == 200


@dataclass(frozen=True)
class CourtListenerResult:
    """Result envelope for a citation-lookup call.

    `ok=True` means the request reached CourtListener and returned a
    parseable response — individual citations inside may still be
    404 / 300 / 400, which the consumer reads from `hits[*].status`.
    `ok=False` means the call itself failed: no token, network error,
    HTTP non-2xx, malformed response. `error_code` distinguishes
    those cases so observability and operator-facing copy can branch
    cleanly.
    """

    ok: bool
    hits: tuple[CitationHit, ...]
    error_code: str | None
    error_message: str | None


def _api_token() -> str:
    return (os.getenv("COURTLISTENER_API_TOKEN") or "").strip()


def _base_url() -> str:
    return (os.getenv("COURTLISTENER_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")


def _timeout_seconds() -> float:
    raw = os.getenv("COURTLISTENER_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


def _coerce_cluster(payload: Any) -> CitationCluster:
    if not isinstance(payload, dict):
        return CitationCluster(case_name="", absolute_url=None, court=None, date_filed=None)
    case_name = str(payload.get("case_name") or payload.get("caseName") or "").strip()
    absolute_url_raw = payload.get("absolute_url") or payload.get("absoluteUrl")
    absolute_url = str(absolute_url_raw).strip() if absolute_url_raw else None
    if absolute_url and absolute_url.startswith("/"):
        # CourtListener returns site-relative URLs in the cluster
        # payload; absolutize against the configured base so the
        # verifier UX can render a working link.
        absolute_url = _base_url() + absolute_url
    court_raw = payload.get("court") or payload.get("court_id")
    court = str(court_raw).strip() if court_raw else None
    date_filed_raw = payload.get("date_filed") or payload.get("dateFiled")
    date_filed = str(date_filed_raw).strip() if date_filed_raw else None
    return CitationCluster(
        case_name=case_name,
        absolute_url=absolute_url,
        court=court,
        date_filed=date_filed,
        raw=payload,
    )


def _coerce_hit(payload: Any) -> CitationHit | None:
    if not isinstance(payload, dict):
        return None
    try:
        status = int(payload.get("status", 0))
    except (TypeError, ValueError):
        status = 0
    citation = str(payload.get("citation") or "").strip()
    normalized_raw = payload.get("normalized_citations") or []
    normalized = tuple(
        str(item).strip() for item in normalized_raw if isinstance(item, str) and item.strip()
    )
    try:
        start_index = int(payload.get("start_index", 0))
    except (TypeError, ValueError):
        start_index = 0
    try:
        end_index = int(payload.get("end_index", 0))
    except (TypeError, ValueError):
        end_index = 0
    error_message = str(payload.get("error_message") or "")
    clusters_raw = payload.get("clusters") or []
    clusters = tuple(_coerce_cluster(item) for item in clusters_raw)
    return CitationHit(
        citation=citation,
        normalized_citations=normalized,
        start_index=start_index,
        end_index=end_index,
        status=status,
        error_message=error_message,
        clusters=clusters,
    )


def lookup_citations_in_text(
    text: str,
    *,
    client: httpx.Client | None = None,
) -> CourtListenerResult:
    """POST `text` to citation-lookup and return per-citation verdicts.

    `client` is an optional injected `httpx.Client` for testing — the
    test suite passes a mock-transport client. Production callers
    omit it and a one-shot client is created per call (V1 — no
    connection pool yet).

    The function pre-checks the token and text-length cap before any
    network I/O so the no-token case is cheap (no socket open).
    """
    token = _api_token()
    if not token:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_no_api_token",
            error_message=(
                "COURTLISTENER_API_TOKEN is not set. Get a free token at "
                "https://www.courtlistener.com/profile/api/ and set the env var."
            ),
        )
    cleaned = (text or "").strip()
    if not cleaned:
        return CourtListenerResult(
            ok=True,
            hits=(),
            error_code=None,
            error_message=None,
        )
    if len(cleaned) > _MAX_TEXT_CHARS:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_text_too_long",
            error_message=(
                f"Text length {len(cleaned)} exceeds CourtListener's "
                f"{_MAX_TEXT_CHARS}-char cap. Chunk the brief and call "
                "this function per chunk."
            ),
        )

    url = f"{_base_url()}/api/rest/v4/citation-lookup/"
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=_timeout_seconds())
    try:
        response = http.post(url, headers=headers, data={"text": cleaned})
    except httpx.HTTPError as exc:
        log_event(
            LOGGER,
            logging.WARNING,
            "courtlistener_lookup_failed",
            error_code="courtlistener_http_error",
            error_class=exc.__class__.__name__,
        )
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_http_error",
            error_message=f"CourtListener request failed: {exc.__class__.__name__}",
        )
    finally:
        if owns_client:
            http.close()

    if response.status_code == 429:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_rate_limited",
            error_message=(
                "CourtListener rate limit hit (60 valid citations/minute). Back off and retry."
            ),
        )
    if response.status_code == 401 or response.status_code == 403:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_auth_rejected",
            error_message=(
                f"CourtListener rejected the token ({response.status_code}). "
                "Verify COURTLISTENER_API_TOKEN is current and active."
            ),
        )
    if response.status_code >= 400:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_http_status",
            error_message=f"CourtListener returned HTTP {response.status_code}.",
        )

    try:
        payload = response.json()
    except ValueError:
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_invalid_json",
            error_message="CourtListener response was not valid JSON.",
        )

    if not isinstance(payload, list):
        return CourtListenerResult(
            ok=False,
            hits=(),
            error_code="courtlistener_invalid_shape",
            error_message="CourtListener response was not a JSON array of citation items.",
        )

    hits: list[CitationHit] = []
    for item in payload:
        coerced = _coerce_hit(item)
        if coerced is not None:
            hits.append(coerced)

    return CourtListenerResult(
        ok=True,
        hits=tuple(hits),
        error_code=None,
        error_message=None,
    )
