from __future__ import annotations

import unittest

from app_logging import redact_context


class LoggingRedactionTests(unittest.TestCase):
    def test_redacts_token_key_and_url_fields_recursively(self) -> None:
        payload = redact_context(
            {
                "api_key": "sk-live-secret",
                "nested": {
                    "refresh_token": "refresh-secret",
                    "feed_url": "https://calendar.example.com/private/basic.ics?token=abc",
                },
                "items": [{"password": "pw"}],
                "filename": "private-study-plan.pdf",
                "safe": "value",
            }
        )

        self.assertEqual("[redacted]", payload["api_key"])
        self.assertEqual("[redacted]", payload["nested"]["refresh_token"])
        self.assertEqual("[redacted-url]", payload["nested"]["feed_url"])
        self.assertEqual("[redacted]", payload["items"][0]["password"])
        self.assertEqual("[redacted]", payload["filename"])
        self.assertEqual("value", payload["safe"])

    def test_redacts_url_like_values_without_losing_host_context(self) -> None:
        payload = redact_context(
            {
                "message": "Fetched https://example.com/a/b?secret=1 and continued.",
            }
        )

        self.assertEqual("Fetched https://example.com/*** and continued.", payload["message"])


if __name__ == "__main__":
    unittest.main()
