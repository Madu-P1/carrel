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
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

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
    court + filing year + the opinion URIs (`sub_opinions`) that
    the holding-match step follows up on. Anything richer (judges,
    citation graph, full opinion text) stays in the raw payload
    accessible via `raw` for callers that need it.
    """

    case_name: str
    absolute_url: str | None
    court: str | None
    date_filed: str | None
    # Carrel V2 half-2: opinion URIs the holding-match step follows up
    # to fetch the actual decision text. CourtListener cluster payloads
    # carry a `sub_opinions` array of opinion-resource URLs; each is a
    # GET that returns the opinion record (html_with_citations,
    # plain_text, etc.). See `fetch_opinion_text` below.
    sub_opinions: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OpinionTextResult:
    """Result envelope for a fetch_opinion_text call.

    `ok=True` means the opinion URI returned a parseable record with
    extractable text. `ok=False` means the fetch itself failed (no
    token, HTTP error, no text fields populated). The holding-match
    step surfaces `error_code` to the operator instead of degrading
    to "holding verified" on a fetch failure (CLAUDE.md "no silent
    AI fallbacks").
    """

    ok: bool
    text: str
    source_field: str | None
    error_code: str | None
    error_message: str | None


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


def _trusted_host() -> str:
    """The host the auth token is valid for. Defaults to the public
    CourtListener host; can be overridden via COURTLISTENER_BASE_URL
    for self-hosted or test deployments.
    """
    parsed = urlparse(_base_url())
    return (parsed.netloc or "").lower()


def _is_trusted_url(url: str) -> bool:
    """Strict host-allowlist check.

    Returns True iff `url` is an http(s) URL whose host matches
    `_trusted_host()` exactly (case-insensitive). Rejects bare
    paths, non-http(s) schemes, missing hosts, and any host that
    only superficially looks like the trusted one (so
    `https://www.courtlistener.com.attacker.com` is rejected).

    Used as a defense-in-depth gate before:
      - rendering an `absolute_url` as a clickable link in the UX,
      - GETting an opinion URI with the auth token in the header.

    Closes the credential-leak vector where a spoofed citation-lookup
    response could exfiltrate the Bearer token to an attacker host.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    return (parsed.netloc or "").lower() == _trusted_host()


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
    # Defense-in-depth: drop absolute_url that doesn't point at the
    # trusted host. A spoofed response (compromised CourtListener,
    # MITM with stripped TLS, or a malicious fixture in a test) could
    # otherwise render a UX link to an attacker domain.
    if absolute_url and not _is_trusted_url(absolute_url):
        log_event(
            LOGGER,
            logging.WARNING,
            "courtlistener_untrusted_absolute_url_dropped",
            url_preview=absolute_url[:120],
        )
        absolute_url = None
    court_raw = payload.get("court") or payload.get("court_id")
    court = str(court_raw).strip() if court_raw else None
    date_filed_raw = payload.get("date_filed") or payload.get("dateFiled")
    date_filed = str(date_filed_raw).strip() if date_filed_raw else None
    sub_opinions_raw = payload.get("sub_opinions") or payload.get("subOpinions") or []
    # Same defense-in-depth on the sub_opinions URIs. fetch_opinion_text
    # also validates per-call, but filtering at coercion keeps untrusted
    # URIs from ever reaching the caller's iteration.
    sub_opinions_candidates = (
        str(uri).strip() for uri in sub_opinions_raw if isinstance(uri, str) and uri.strip()
    )
    sub_opinions: tuple[str, ...] = ()
    kept: list[str] = []
    for uri in sub_opinions_candidates:
        if _is_trusted_url(uri):
            kept.append(uri)
        else:
            log_event(
                LOGGER,
                logging.WARNING,
                "courtlistener_untrusted_sub_opinion_dropped",
                url_preview=uri[:120],
            )
    sub_opinions = tuple(kept)
    return CitationCluster(
        case_name=case_name,
        absolute_url=absolute_url,
        court=court,
        date_filed=date_filed,
        sub_opinions=sub_opinions,
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
    network I/O so the no-token case is cheap (no socket open). The token
    guard applies only to the live path: an injected `client` (the offline
    local-caselaw MockTransport, or a test stub) owns its transport and
    needs no egress credential, so requiring one there would reject the
    offline corpus that needs no auth.
    """
    token = _api_token()
    if client is None and not token:
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


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|nbsp|#\d+|#x[0-9a-fA-F]+);")
_HTML_ENTITY_MAP = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": " ",
}
_WHITESPACE_RUN = re.compile(r"\s+")
# CourtListener opinion text-field preference order. Per the public
# docs: "prefer the html_with_citations field instead of plain_text;
# it contains the raw text of the decision, and is the most reliable
# field for most purposes." Walk in order, take the first non-empty.
_OPINION_TEXT_FIELDS = (
    "html_with_citations",
    "html_columbia",
    "html_lawbox",
    "html_anon_2020",
    "html",
    "xml_harvard",
    "plain_text",
)


def _decode_entity(match: "re.Match[str]") -> str:
    raw = match.group(0)
    if raw in _HTML_ENTITY_MAP:
        return _HTML_ENTITY_MAP[raw]
    body = raw[1:-1]
    try:
        if body.startswith("#x") or body.startswith("#X"):
            return chr(int(body[2:], 16))
        if body.startswith("#"):
            return chr(int(body[1:]))
    except (ValueError, OverflowError):
        return raw
    return raw


def _html_to_text(html: str) -> str:
    """Cheap HTML-to-text. Avoids the BeautifulSoup dependency for one
    file's worth of stripping — opinion HTML is well-structured enough
    that a tag-strip + entity-decode is faithful."""
    if not html:
        return ""
    no_tags = _HTML_TAG_RE.sub(" ", html)
    decoded = _HTML_ENTITY_RE.sub(_decode_entity, no_tags)
    collapsed = _WHITESPACE_RUN.sub(" ", decoded).strip()
    return collapsed


def fetch_opinion_text(
    opinion_uri: str,
    *,
    client: httpx.Client | None = None,
    max_chars: int = 8_000,
) -> OpinionTextResult:
    """GET an opinion resource URI and return its text content.

    The CourtListener citation-lookup response's cluster carries a
    `sub_opinions` array of opinion-resource URIs; this function
    fetches one of them and extracts the most reliable text field
    (html_with_citations preferred; falls back through the documented
    source-specific variants). HTML is stripped to plain text.

    `max_chars` truncates the returned text from the front. V1
    holding-match runs near the start of the opinion (the holding
    is typically in the first 5-15K characters). A future half can
    add semantic narrowing for opinions where the holding lives
    deeper.

    Honest fallback per CLAUDE.md "no silent AI fallbacks": every
    failure mode returns `ok=False` with an explicit error_code so
    the holding-match step surfaces "Holding check unavailable"
    instead of silently treating the cite as verified.
    """
    # Egress credential gate: live path only. An injected client (offline
    # MockTransport / test stub) owns its transport and needs no token.
    token = _api_token()
    if client is None and not token:
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_no_api_token",
            error_message=("COURTLISTENER_API_TOKEN is not set; cannot fetch opinion text."),
        )
    uri = (opinion_uri or "").strip()
    if not uri:
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_no_opinion_uri",
            error_message="Empty opinion URI.",
        )
    # Defense-in-depth: never send the auth token to an untrusted host.
    # A spoofed citation-lookup response could otherwise return a
    # sub_opinions URI like "https://attacker.com/opinions/1/" and
    # exfiltrate the Bearer token via the request header. _coerce_cluster
    # already filters sub_opinions at coercion, but this gate guarantees
    # the invariant at the call site too — both layers must agree before
    # the socket opens.
    if not _is_trusted_url(uri):
        log_event(
            LOGGER,
            logging.WARNING,
            "courtlistener_opinion_fetch_untrusted_host",
            url_preview=uri[:120],
        )
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_untrusted_host",
            error_message=(
                f"Opinion URI host is not trusted: refusing to send auth token to {uri[:120]}."
            ),
        )

    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=_timeout_seconds())
    try:
        response = http.get(uri, headers=headers)
    except httpx.HTTPError as exc:
        log_event(
            LOGGER,
            logging.WARNING,
            "courtlistener_opinion_fetch_failed",
            error_code="courtlistener_http_error",
            error_class=exc.__class__.__name__,
        )
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_http_error",
            error_message=f"Opinion fetch failed: {exc.__class__.__name__}",
        )
    finally:
        if owns_client:
            http.close()

    if response.status_code == 429:
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_rate_limited",
            error_message="CourtListener rate limit hit on opinion fetch.",
        )
    if response.status_code in (401, 403):
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_auth_rejected",
            error_message=(
                f"CourtListener rejected the token on opinion fetch ({response.status_code})."
            ),
        )
    if response.status_code >= 400:
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_http_status",
            error_message=f"Opinion endpoint returned HTTP {response.status_code}.",
        )

    try:
        payload = response.json()
    except ValueError:
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_invalid_json",
            error_message="Opinion response was not valid JSON.",
        )
    if not isinstance(payload, dict):
        return OpinionTextResult(
            ok=False,
            text="",
            source_field=None,
            error_code="courtlistener_invalid_shape",
            error_message="Opinion response was not a JSON object.",
        )

    for field_name in _OPINION_TEXT_FIELDS:
        raw = payload.get(field_name)
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = _html_to_text(raw) if field_name != "plain_text" else raw.strip()
        if not text:
            continue
        if max_chars and len(text) > max_chars:
            text = text[:max_chars].rstrip() + " …"
        return OpinionTextResult(
            ok=True,
            text=text,
            source_field=field_name,
            error_code=None,
            error_message=None,
        )

    return OpinionTextResult(
        ok=False,
        text="",
        source_field=None,
        error_code="courtlistener_no_text_field",
        error_message="Opinion record has no populated text field.",
    )
