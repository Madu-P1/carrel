from __future__ import annotations

import unittest
from unittest import mock

import httpx

from services.calendar.feed_client import FeedFetchError, fetch_feed


class FakeClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, target: str, headers: dict[str, str]) -> httpx.Response:
        self.requests.append(target)
        return self.responses.pop(0)


class CalendarFeedClientTests(unittest.TestCase):
    def test_redirect_target_is_revalidated_before_following(self) -> None:
        client = FakeClient(
            [
                httpx.Response(
                    302,
                    headers={"Location": "http://127.0.0.1/private.ics"},
                    request=httpx.Request("GET", "https://calendar.example.com/feed.ics"),
                )
            ]
        )

        def validation(url: str):
            ok = not url.startswith("http://127.0.0.1")
            return type("Result", (), {"ok": ok, "reason": "private_ip", "detail": "blocked"})()

        with (
            mock.patch("services.calendar.feed_client.httpx.Client", return_value=client),
            mock.patch("services.calendar.feed_client.validate_feed_url", side_effect=validation),
        ):
            with self.assertRaises(FeedFetchError) as raised:
                fetch_feed("https://calendar.example.com/feed.ics")

        self.assertEqual("redirect_rejected", raised.exception.reason)
        self.assertEqual(["https://calendar.example.com/feed.ics"], client.requests)

    def test_successful_redirect_returns_only_masked_final_url(self) -> None:
        client = FakeClient(
            [
                httpx.Response(
                    302,
                    headers={"Location": "https://cdn.example.com/private/basic.ics?token=secret"},
                    request=httpx.Request("GET", "https://calendar.example.com/feed.ics"),
                ),
                httpx.Response(
                    200,
                    headers={"Content-Type": "text/calendar"},
                    content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
                    request=httpx.Request("GET", "https://cdn.example.com/private/basic.ics?token=secret"),
                ),
            ]
        )

        with (
            mock.patch("services.calendar.feed_client.httpx.Client", return_value=client),
            mock.patch(
                "services.calendar.feed_client.validate_feed_url",
                return_value=type("Result", (), {"ok": True, "reason": None, "detail": ""})(),
            ),
        ):
            result = fetch_feed("https://calendar.example.com/feed.ics")

        self.assertEqual(200, result.status)
        self.assertEqual("https://cdn.example.com/***", result.final_url)
        self.assertNotIn("token=secret", result.final_url)


if __name__ == "__main__":
    unittest.main()
