"""URL validation + redaction for calendar feeds.

Two concerns live here because they share input shape:

1. SSRF defense — before we ask httpx to fetch a URL, gate it against the
   classes of input that would let a hostile/typo'd URL hit our local
   network or non-HTTP schemes. Concrete bar:

       - schemes: http and https only
       - host: must resolve to a public IP
                no loopback (127.0.0.0/8, ::1)
                no RFC1918 (10/8, 172.16/12, 192.168/16)
                no link-local (169.254/16, fe80::/10)
                no IPv6 unique-local (fc00::/7)
                no 0.0.0.0
       - path: opaque to us; iCal feeds use any path

2. Log/return-value redaction — calendar feed URLs ARE secrets (Google
   Calendar's "secret address," Outlook's signed ICS, Blackboard's
   per-user feed). They're revocable, but they should not leak through
   the system. Every log line, error response, sync_runs.error field,
   and GET /api/calendar/feeds row uses the masked form.

The two concerns share file because callers want both: validate then
later redact for display. Putting them together keeps the security
boundary in one place.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


_ALLOWED_SCHEMES = ("http", "https")

# 5 MB cap. iCal feeds for a single user are typically 50-500 KB; even
# a 5-year-history Google Cal export tops out around 1-2 MB. 5 MB gives
# us headroom while still being a meaningful DoS limit.
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# 10 second cap on the network round trip. Calendar providers are fast
# under normal conditions; anything slower is a sync-failure signal,
# not something we want a user waiting on.
HTTP_TIMEOUT_SECONDS = 10.0

# Allowed iCal content types. Some servers send text/plain or
# application/octet-stream for .ics; we accept those too because the
# parser only cares about the body. Anything HTML-shaped means we
# probably hit an auth-required login page and should fail loud.
ALLOWED_CONTENT_TYPE_PREFIXES = (
    "text/calendar",
    "text/plain",
    "application/octet-stream",
    "application/calendar",
)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a feed URL pre-flight check.

    `ok=True` means the URL is well-formed AND the resolved host is in
    the public internet IP space. The actual HTTP request can still
    fail — that's feed_client's concern.
    """

    ok: bool
    reason: str = ""  # short stable code for analytics / tests
    detail: str = ""  # human-readable explanation


class FeedURLRejected(Exception):
    """Raised when a URL fails the SSRF + scheme gate.

    Carries a `reason` code so route handlers can return structured
    errors and clients can render specific recovery actions ("Use the
    canonical URL from your calendar settings" vs "Only http/https
    schemes are supported").
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def validate_feed_url(url: str) -> ValidationResult:
    """Run the full pre-flight check on a feed URL.

    Returns ValidationResult instead of raising so callers can decide
    whether to surface the failure to the user (POST /feeds) or log and
    move on (sync-time re-validation after redirect).

    The check sequence matters: scheme first (cheapest), shape second,
    DNS resolution last (expensive + side-effecting). Short-circuit on
    the first failure so a malformed URL never even hits DNS.
    """

    if not isinstance(url, str) or not url.strip():
        return ValidationResult(ok=False, reason="empty_url", detail="URL is empty.")

    parsed = urlparse(url.strip())

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return ValidationResult(
            ok=False,
            reason="bad_scheme",
            detail=(f"Only http and https URLs are accepted. Got '{parsed.scheme or '(none)'}'."),
        )

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ValidationResult(
            ok=False,
            reason="missing_host",
            detail="URL has no host part.",
        )

    if host == "localhost":
        return ValidationResult(
            ok=False,
            reason="localhost",
            detail="Localhost URLs are not allowed.",
        )

    # Suffix-style block for .local mDNS hostnames (Bonjour). Matches
    # Apple's "myimac.local" pattern. Also covers .internal which some
    # corp networks use as a private TLD.
    if host.endswith(".local") or host.endswith(".internal"):
        return ValidationResult(
            ok=False,
            reason="private_tld",
            detail="Private/mDNS hosts are not allowed.",
        )

    # Resolve to IP and reject any private range. We use getaddrinfo so
    # both IPv4 and IPv6 results are checked. If the host resolves to
    # multiple addresses, ALL of them must be public — otherwise an
    # attacker could DNS-pin a public lookup but TCP-connect to the
    # private one (rebinding attack at the resolution boundary).
    try:
        addrinfo = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return ValidationResult(
            ok=False,
            reason="dns_failed",
            detail=f"Could not resolve host: {exc}",
        )

    for family, _socktype, _proto, _canon, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        ):
            return ValidationResult(
                ok=False,
                reason="private_ip",
                detail=(
                    "URL resolves to a non-public IP. Calendar feeds must be publicly reachable."
                ),
            )

    return ValidationResult(ok=True)


def validate_content_type(content_type: Optional[str]) -> bool:
    """Sanity check on Content-Type from a successful fetch.

    Calendar servers should send text/calendar; some send text/plain or
    application/octet-stream for .ics files. text/html is the canary
    we care about — it means we hit a login page or a 4xx error page
    instead of an iCal body.
    """

    if not content_type:
        # No content-type at all is suspicious but not a hard fail —
        # some servers omit it. The parser will reject if the body
        # isn't valid iCal.
        return True

    ct = content_type.split(";", 1)[0].strip().lower()
    return any(ct.startswith(prefix) for prefix in ALLOWED_CONTENT_TYPE_PREFIXES)


# ---------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------

# Match the path of an iCal URL. Keeps scheme + host visible; everything
# after the third slash gets replaced with `***`. This preserves enough
# context for "which provider" debugging without leaking the auth token
# embedded in the path.
#
# Examples:
#   https://calendar.google.com/calendar/ical/abc123.../basic.ics
#     → https://calendar.google.com/***
#   https://learn.escp.eu/webapps/calendar/icalendar/?action=GET&token=...
#     → https://learn.escp.eu/***
_HOST_AND_PATH = re.compile(r"^([a-z]+://[^/]+)(/.*)?$", re.IGNORECASE)


def mask_url(url: str) -> str:
    """Return a masked form of a feed URL safe for logs/errors/exports.

    The contract: the masked form is stable under repeated calls (so
    log dedup works), reveals provider domain (for debugging), but
    never reveals path or query (which is where the auth token lives).

    For non-URL inputs (already masked, garbage, None) the function is
    a no-op string conversion. This makes it safe to wrap any value
    going into a log line without knowing whether it's a URL.
    """

    if not url:
        return ""
    if not isinstance(url, str):
        url = str(url)

    match = _HOST_AND_PATH.match(url)
    if not match:
        # Not URL-shaped (could be already-masked or unrelated text).
        # Return the input untouched; the caller is responsible for not
        # passing other secrets in.
        return url

    return f"{match.group(1)}/***"
