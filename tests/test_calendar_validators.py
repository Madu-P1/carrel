"""Tests for services/calendar/validators.py.

Two surfaces with explicit security postures:
  - validate_feed_url: SSRF gate (scheme + private-IP + non-public hosts)
  - mask_url: stable redaction for logs / API responses / errors
"""

from __future__ import annotations

import unittest
from unittest import mock

from services.calendar.validators import (
    mask_url,
    validate_content_type,
    validate_feed_url,
)


class MaskUrlTests(unittest.TestCase):
    def test_masks_path_keeps_scheme_and_host(self) -> None:
        masked = mask_url(
            "https://calendar.google.com/calendar/ical/abc123/basic.ics"
        )
        self.assertEqual(masked, "https://calendar.google.com/***")

    def test_masks_query_string_too(self) -> None:
        masked = mask_url(
            "https://learn.escp.eu/cal?token=secret&user=42"
        )
        self.assertEqual(masked, "https://learn.escp.eu/***")

    def test_idempotent_on_already_masked(self) -> None:
        first = mask_url("https://learn.escp.eu/cal?token=secret")
        again = mask_url(first)
        self.assertEqual(first, again)

    def test_safe_on_non_url_input(self) -> None:
        # Must not raise; mask_url is wrapped around random log inputs.
        self.assertEqual(mask_url(""), "")
        self.assertEqual(mask_url("not a url"), "not a url")
        self.assertEqual(mask_url(None), "")


class ValidateFeedUrlTests(unittest.TestCase):
    def test_accepts_public_https(self) -> None:
        with mock.patch(
            "services.calendar.validators.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("142.250.190.78", 0))],
        ):
            result = validate_feed_url("https://calendar.google.com/cal/abc.ics")
        self.assertTrue(result.ok, result.detail)

    def test_rejects_non_http_scheme(self) -> None:
        result = validate_feed_url("file:///etc/passwd")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "bad_scheme")

    def test_rejects_javascript_scheme(self) -> None:
        result = validate_feed_url("javascript:alert(1)")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "bad_scheme")

    def test_rejects_localhost(self) -> None:
        result = validate_feed_url("http://localhost:8080/calendar")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "localhost")

    def test_rejects_loopback_ip(self) -> None:
        with mock.patch(
            "services.calendar.validators.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("127.0.0.1", 0))],
        ):
            result = validate_feed_url("http://internal.example/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "private_ip")

    def test_rejects_rfc1918(self) -> None:
        for ip in ("10.0.0.1", "192.168.1.5", "172.16.99.1"):
            with self.subTest(ip=ip):
                with mock.patch(
                    "services.calendar.validators.socket.getaddrinfo",
                    return_value=[(0, 0, 0, "", (ip, 0))],
                ):
                    result = validate_feed_url("https://internal.corp/cal")
                self.assertFalse(result.ok)
                self.assertEqual(result.reason, "private_ip")

    def test_rejects_link_local(self) -> None:
        with mock.patch(
            "services.calendar.validators.socket.getaddrinfo",
            return_value=[(0, 0, 0, "", ("169.254.169.254", 0))],
        ):
            result = validate_feed_url("http://aws-meta/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "private_ip")

    def test_rejects_dot_local(self) -> None:
        result = validate_feed_url("http://imac.local/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "private_tld")

    def test_rejects_dot_internal(self) -> None:
        result = validate_feed_url("https://router.internal/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "private_tld")

    def test_rejects_empty(self) -> None:
        result = validate_feed_url("")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "empty_url")

    def test_dns_failure_surfaces(self) -> None:
        import socket as _socket
        with mock.patch(
            "services.calendar.validators.socket.getaddrinfo",
            side_effect=_socket.gaierror("nodename nor servname"),
        ):
            result = validate_feed_url("https://no-such-host.invalid/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "dns_failed")

    def test_rejects_when_any_resolved_address_is_private(self) -> None:
        # DNS rebinding mitigation: if ONE address is private, fail
        # the whole URL — never follow public DNS into a private network.
        with mock.patch(
            "services.calendar.validators.socket.getaddrinfo",
            return_value=[
                (0, 0, 0, "", ("142.250.190.78", 0)),  # public
                (0, 0, 0, "", ("10.0.0.5", 0)),         # private
            ],
        ):
            result = validate_feed_url("https://hostile.example/cal")
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "private_ip")


class ContentTypeTests(unittest.TestCase):
    def test_accepts_ical(self) -> None:
        self.assertTrue(validate_content_type("text/calendar"))
        self.assertTrue(validate_content_type("text/calendar; charset=utf-8"))

    def test_accepts_plain(self) -> None:
        self.assertTrue(validate_content_type("text/plain"))

    def test_accepts_octet_stream(self) -> None:
        self.assertTrue(validate_content_type("application/octet-stream"))

    def test_accepts_missing(self) -> None:
        # Some servers omit content-type; we let the parser decide.
        self.assertTrue(validate_content_type(None))
        self.assertTrue(validate_content_type(""))

    def test_rejects_html(self) -> None:
        # text/html means we hit a login page or error page, not iCal.
        self.assertFalse(validate_content_type("text/html"))


if __name__ == "__main__":
    unittest.main()
