"""HTTP fetch for calendar feeds.

Three concerns this layer owns:

1. Conditional GET — send If-None-Match / If-Modified-Since when we
   have them, return a 304-not-modified shortcut so we don't re-parse
   bodies that haven't changed. Calendar providers honor these well.

2. Redirect discipline — at most one redirect, and the redirect target
   must pass the same SSRF gate as the original URL. This is the
   user-friendly compromise (Google/Apple/Outlook all redirect once
   for signed CDN delivery) without opening the rebinding-at-redirect
   attack surface.

3. Error redaction — any error that escapes this layer must already
   have URLs masked. Logs at this layer use mask_url for every URL
   reference so callers don't have to remember.

Synchronous httpx — Carrel's existing pattern is sync FastAPI routes
that call sync services. We don't need an async client for this; one
fetch per sync, sub-second normal case, 10s cap on the bad case. Keeps
the call tree simple.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app_logging import get_logger
from services.calendar.validators import (
    ALLOWED_CONTENT_TYPE_PREFIXES,
    HTTP_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    mask_url,
    validate_content_type,
    validate_feed_url,
)


LOGGER = get_logger("calendar.feed_client")

MAX_REDIRECTS = 1


@dataclass
class FetchResult:
    """Outcome of a single fetch attempt against a feed URL.

    `body` is None when status is 304 (server says nothing changed) so
    the caller can short-circuit parsing. `final_url` reflects post-
    redirect URL when applicable; sync_runs records that for
    debugging without exposing the original token-bearing URL.
    """

    status: int  # HTTP status of the final response
    body: Optional[bytes]  # None on 304, else the response body
    etag: Optional[str]
    last_modified: Optional[str]
    final_url: str  # already masked for safe logging


class FeedFetchError(Exception):
    """Raised when a fetch fails in a way the caller should record.

    `reason` is a stable analytics code; `detail` is human-readable and
    safe to surface to the user (URLs already masked).
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def fetch_feed(
    url: str,
    *,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> FetchResult:
    """Fetch a calendar feed with conditional GET + 1 validated redirect.

    Validation happens twice: once before the initial request (caller
    may have skipped this if the URL came from our own DB), and once on
    the redirect target if a 3xx comes back. The second check matters
    because a malicious or compromised feed could redirect to an
    internal address — DNS rebinding mitigation requires re-validating
    the post-redirect host.

    Raises FeedFetchError on:
      - URL fails validation
      - >1 redirect, or redirect target fails validation
      - Network error / timeout
      - Response > 5 MB
      - Content-Type clearly wrong (text/html, etc.)

    Returns FetchResult on:
      - 200 (body + etag/last-modified)
      - 304 (body=None, caller short-circuits)
      - Other 2xx (body)
      - 4xx/5xx are returned as FetchResult so the caller can record
        the HTTP status; we don't raise on those (tests and ops want
        to distinguish "feed went 404" from "we never reached it")
    """

    pre_check = validate_feed_url(url)
    if not pre_check.ok:
        raise FeedFetchError(
            reason=pre_check.reason,
            detail=pre_check.detail,
        )

    headers: dict[str, str] = {
        "User-Agent": "Carrel/1.0 (calendar feed sync)",
        "Accept": "text/calendar, text/plain;q=0.9, */*;q=0.5",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    masked_initial = mask_url(url)

    # Manual redirect handling. httpx's follow_redirects=True would do
    # this for us but wouldn't re-validate the redirect target. We need
    # the validation hook in the middle, so we drive the loop.
    target = url
    redirects_followed = 0
    response: Optional[httpx.Response] = None

    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            while True:
                response = client.get(target, headers=headers)

                # 3xx → maybe follow once, after re-validation
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location")
                    if not location:
                        # 3xx without Location = malformed; treat as fatal
                        raise FeedFetchError(
                            reason="redirect_no_location",
                            detail="Feed returned a redirect without a target URL.",
                        )

                    if redirects_followed >= MAX_REDIRECTS:
                        raise FeedFetchError(
                            reason="too_many_redirects",
                            detail=(
                                "This URL redirects more than we allow. "
                                "Paste the canonical URL from your "
                                "calendar provider's settings."
                            ),
                        )

                    # Resolve relative redirects against the previous URL
                    next_url = str(httpx.URL(target).join(location))
                    next_check = validate_feed_url(next_url)
                    if not next_check.ok:
                        # Redirect target fails the SSRF gate. This is
                        # exactly the rebinding attack we're guarding
                        # against — we DO NOT follow.
                        LOGGER.warning(
                            "Calendar feed redirect rejected: %s -> %s (%s)",
                            masked_initial,
                            mask_url(next_url),
                            next_check.reason,
                        )
                        raise FeedFetchError(
                            reason="redirect_rejected",
                            detail=(
                                "Feed redirected to a non-public address. "
                                "This may be a configuration mistake."
                            ),
                        )

                    redirects_followed += 1
                    target = next_url
                    continue

                # Non-3xx → done with the redirect loop
                break

    except httpx.TimeoutException as exc:
        raise FeedFetchError(
            reason="timeout",
            detail="Feed did not respond within 10 seconds.",
        ) from exc
    except httpx.RequestError as exc:
        raise FeedFetchError(
            reason="network_error",
            detail=f"Network error: {exc.__class__.__name__}",
        ) from exc

    assert response is not None  # loop guarantees this

    # 304 → caller short-circuits, no body to read
    if response.status_code == 304:
        return FetchResult(
            status=304,
            body=None,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            final_url=mask_url(target),
        )

    # Non-2xx, non-3xx: surface the status. The caller (sync_service)
    # decides whether to record this as a fail and back off.
    if not (200 <= response.status_code < 300):
        return FetchResult(
            status=response.status_code,
            body=None,
            etag=None,
            last_modified=None,
            final_url=mask_url(target),
        )

    # 2xx — content checks, then return the body
    content_type = response.headers.get("Content-Type", "")
    if not validate_content_type(content_type):
        raise FeedFetchError(
            reason="bad_content_type",
            detail=(
                f"Feed returned content-type '{content_type or '(none)'}'. "
                f"Expected one of: {', '.join(ALLOWED_CONTENT_TYPE_PREFIXES)}. "
                f"This often means the URL needs a different export format "
                f"or auth has expired."
            ),
        )

    body = response.content
    if len(body) > MAX_RESPONSE_BYTES:
        raise FeedFetchError(
            reason="response_too_large",
            detail=(
                f"Feed body is {len(body):,} bytes; cap is {MAX_RESPONSE_BYTES:,}. "
                f"Restrict the export window in your calendar settings."
            ),
        )

    return FetchResult(
        status=response.status_code,
        body=body,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        final_url=mask_url(target),
    )
