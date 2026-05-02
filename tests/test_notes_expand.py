"""Tests for /api/notes/expand.

Contract:
  - When the AI provider is available and returns a well-formed tool payload,
    the endpoint renders that payload into the feature's markdown shape with
    all four sections present (Summary, Key Ideas, Organized Notes, Review
    Prompts) — and NONE of the content is a literal restatement of the user's
    input.
  - When the AI provider returns ok=False (disabled, rate limited, any
    failure), the endpoint falls back to the deterministic builder. The
    response body still has the same markdown shape; the content will be
    thin, but the endpoint never 500s.
  - When the AI provider returns ok=True but malformed JSON (missing
    required fields, wrong types), the endpoint also falls back silently.
  - Empty content is rejected with HTTP 400.
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

import main
from ai.router import ClaudeCallResult


def _ok_tool_result(payload: dict) -> ClaudeCallResult:
    return ClaudeCallResult(
        ok=True,
        task="balanced",
        model="claude-sonnet-4-6",
        request_kind="notes.expand",
        text=None,
        json_payload=payload,
        error_code=None,
        error_message=None,
        latency_ms=123.0,
        input_tokens=200,
        output_tokens=600,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier=None,
        stop_reason="tool_use",
        request_id="req-1",
    )


def _failing_tool_result(code: str = "http_500") -> ClaudeCallResult:
    return ClaudeCallResult(
        ok=False,
        task="balanced",
        model="claude-sonnet-4-6",
        request_kind="notes.expand",
        text=None,
        json_payload=None,
        error_code=code,
        error_message="boom",
        latency_ms=12.0,
        input_tokens=None,
        output_tokens=None,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier=None,
        stop_reason=None,
        request_id=None,
    )


class FakeProvider:
    """Minimal stand-in for an AIProvider used only by /api/notes/expand.

    Enables a test to control ai_enabled() and the tool-call return value
    without touching the real Claude/Ollama selection logic.
    """

    def __init__(self, *, enabled: bool = True, result: ClaudeCallResult | None = None) -> None:
        self._enabled = enabled
        self._result = result

    def ai_enabled(self) -> bool:
        return self._enabled

    def model_for_task(self, task):  # pragma: no cover - not exercised here
        del task
        return "fake"

    def request_text(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("request_text should not be called from expand_note")

    def request_json(self, **kwargs):  # pragma: no cover - not exercised here
        raise AssertionError("request_json should not be called from expand_note")

    def request_tool_call(self, **kwargs) -> ClaudeCallResult:
        # Sanity-check the tool we're called with — if the shape drifts we
        # want the test to fail loudly, not silently.
        tool = kwargs.get("tool") or {}
        assert tool.get("name") == "submit_expanded_note"
        schema = tool.get("input_schema") or {}
        assert set(schema.get("required") or []) == {
            "summary",
            "key_ideas",
            "organized_notes",
            "review_prompts",
        }
        return self._result or _failing_tool_result("no_result")


class NotesExpandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)

    def test_empty_content_rejected(self) -> None:
        response = self.client.post("/api/notes/expand", json={"content": "   "})
        self.assertEqual(response.status_code, 400)

    def test_ai_payload_rendered_to_markdown(self) -> None:
        ai_payload = {
            "summary": (
                "A bond is a debt security: the issuer borrows money from the "
                "holder and agrees to repay the face value on a fixed date, "
                "plus periodic interest called the coupon. Governments, "
                "corporations, and municipalities all issue them."
            ),
            "key_ideas": [
                {
                    "name": "Face value",
                    "description": "The amount repaid at maturity, also called par.",
                },
                {
                    "name": "Coupon",
                    "description": "Periodic interest payments made before maturity.",
                },
                {
                    "name": "Yield",
                    "description": "The effective return, which moves inverse to the bond's price.",
                },
            ],
            "organized_notes": [
                "Bonds are debt instruments, not ownership stakes.",
                "Issuers include sovereign governments, corporations, and municipalities.",
                "Price moves inverse to prevailing interest rates.",
                "Credit ratings signal default risk.",
            ],
            "review_prompts": [
                "How does a bond's price change when market interest rates rise?",
                "Why might a corporation issue bonds instead of equity?",
                "What happens to a holder if the issuer defaults before maturity?",
            ],
        }
        fake = FakeProvider(enabled=True, result=_ok_tool_result(ai_payload))
        with mock.patch("routes.tutor.get_default_provider", return_value=fake):
            response = self.client.post(
                "/api/notes/expand",
                json={"content": "Bonds are issued by government bodies", "title": "Bonds"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("expanded_markdown", body)
        self.assertEqual("ai", body["mode"])
        self.assertIsNone(body["error_code"])
        md = body["expanded_markdown"]

        # Structure checks.
        self.assertIn("# Bonds", md)
        self.assertIn("## Summary", md)
        self.assertIn("## Key Ideas", md)
        self.assertIn("## Organized Notes", md)
        self.assertIn("## Review Prompts", md)

        # Content check: the user's literal input must not appear as a top-level
        # bullet. That was the original bug — the deterministic path echoed the
        # single sentence into every section.
        self.assertNotIn("- **Bonds**: Bonds are issued by government bodies", md)
        self.assertNotIn("1. Bonds are issued by government bodies", md)

        # Content is drawn from the AI payload.
        self.assertIn("Face value", md)
        self.assertIn("market interest rates rise", md)

    def test_ai_unavailable_falls_back_without_500(self) -> None:
        fake = FakeProvider(enabled=False)
        with mock.patch("routes.tutor.get_default_provider", return_value=fake):
            response = self.client.post(
                "/api/notes/expand",
                json={"content": "Bonds are issued by government bodies", "title": "Bonds"},
            )
        # The endpoint must still return something. Even if the content is
        # sparse (deterministic path), the shape is stable.
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual("deterministic", body["mode"])
        self.assertEqual("ai_disabled", body["error_code"])
        md = body["expanded_markdown"]
        self.assertIn("# Bonds", md)
        self.assertIn("## Summary", md)

    def test_ai_malformed_payload_falls_back(self) -> None:
        # AI returned ok=True but with an empty/bad payload. We refuse to
        # format junk; fall back cleanly.
        bad = _ok_tool_result({"summary": None, "key_ideas": "not-a-list"})
        fake = FakeProvider(enabled=True, result=bad)
        with mock.patch("routes.tutor.get_default_provider", return_value=fake):
            response = self.client.post(
                "/api/notes/expand",
                json={"content": "Bonds are debt instruments.", "title": "Bonds"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual("deterministic", body["mode"])
        self.assertEqual("malformed_payload", body["error_code"])
        md = body["expanded_markdown"]
        # The deterministic fallback is what we should see — it still has a
        # Summary section populated from the user's input.
        self.assertIn("## Summary", md)

    def test_small_model_outline_mode_gets_filtered(self) -> None:
        """Small models sometimes slip into outline mode — emitting topic
        headings like "Bond Yields" or "Real-World Examples" instead of
        complete sentences for organized_notes, and non-question headings
        like "Bond Schedules" for review_prompts. Those must be dropped so
        the user sees only real content.
        """
        ai_payload = {
            "summary": "Bonds are debt instruments sold by issuers to raise capital.",
            "key_ideas": [
                {"name": "Face value", "description": "Amount repaid at maturity."},
                # Identifier leak, dropped.
                {"name": "bond_types", "description": "concepts_related_to_bonds"},
            ],
            "organized_notes": [
                "Bonds pay fixed coupon interest until maturity.",  # real sentence, keep
                "Government Bonds",  # title-case heading, drop
                "Bond Valuation",  # heading, drop
                "use_cases_for_government_bonds",  # identifier leak, drop
                "Investor protection depends on issuer credit quality.",  # real sentence, keep
            ],
            "review_prompts": [
                "How does a bond's price change when interest rates rise?",  # real question, keep
                "Bond Schedules",  # non-question heading, drop
                "concepts_related_to_bonds",  # identifier leak, drop
                "What is X?",  # too short (3 words), drop
                "Why might a corporation issue bonds instead of equity?",  # real question, keep
            ],
        }
        fake = FakeProvider(enabled=True, result=_ok_tool_result(ai_payload))
        with mock.patch("routes.tutor.get_default_provider", return_value=fake):
            response = self.client.post(
                "/api/notes/expand",
                json={"content": "Bonds are issued by governments.", "title": "Bonds"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual("ai", body["mode"])
        self.assertIsNone(body["error_code"])
        md = body["expanded_markdown"]

        # Junk filtered out.
        for bad in [
            "concepts_related_to_bonds",
            "use_cases_for_government_bonds",
            "Government Bonds",
            "Bond Valuation",
            "Bond Schedules",
        ]:
            self.assertNotIn(bad, md, f"{bad!r} should have been filtered")

        # "What is X?" is too short (3 words).
        self.assertNotIn("- What is X?", md)

        # Real content survives.
        self.assertIn("Face value", md)
        self.assertIn("coupon interest until maturity", md)
        self.assertIn("Investor protection", md)
        self.assertIn("interest rates rise", md)
        self.assertIn("corporation issue bonds", md)

    def test_ai_error_falls_back(self) -> None:
        fake = FakeProvider(enabled=True, result=_failing_tool_result("http_429"))
        with mock.patch("routes.tutor.get_default_provider", return_value=fake):
            response = self.client.post(
                "/api/notes/expand",
                json={"content": "Bonds are debt instruments."},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual("deterministic", body["mode"])
        self.assertEqual("http_429", body["error_code"])
        md = body["expanded_markdown"]
        self.assertIn("## Summary", md)


if __name__ == "__main__":
    unittest.main()
