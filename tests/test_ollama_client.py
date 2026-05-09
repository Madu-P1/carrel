"""Tests for `ai/ollama.py`. Matches the style of tests/test_ai_router.py."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest import mock

import httpx

from ai.ollama import OllamaClient
from ai.router import ClaudeCallResult


def _mock_transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434")


def _ok_payload(message_content: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "model": "llama3.1:8b",
        "created_at": "2026-04-21T13:00:00Z",
        "message": {"role": "assistant", "content": message_content},
        "done": True,
        "done_reason": "stop",
        "total_duration": 123_000_000,  # 123 ms in nanoseconds
        "prompt_eval_count": 42,
        "eval_count": 17,
    }
    payload.update(extra)
    return payload


class OllamaRequestTextTests(unittest.TestCase):
    def test_request_text_happy_path(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json=_ok_payload("Mitosis produces two daughter cells."))

        client = OllamaClient(
            base_url="http://127.0.0.1:11434",
            balanced_model="llama3.1:8b",
            http_client=_mock_transport(handler),
        )
        result = client.request_text(
            request_kind="test.text",
            system="You are a tutor.",
            prompt="What is mitosis?",
        )

        self.assertIsInstance(result, ClaudeCallResult)
        self.assertTrue(result.ok)
        self.assertEqual(result.model, "llama3.1:8b")
        self.assertEqual(result.text, "Mitosis produces two daughter cells.")
        self.assertIsNone(result.json_payload)
        self.assertEqual(result.input_tokens, 42)
        self.assertEqual(result.output_tokens, 17)
        self.assertAlmostEqual(result.latency_ms, 123.0, places=1)
        self.assertEqual(result.stop_reason, "stop")
        self.assertFalse(result.cache_hit)
        self.assertTrue(captured["url"].endswith("/api/chat"))
        self.assertEqual(captured["body"]["model"], "llama3.1:8b")
        self.assertFalse(captured["body"]["stream"])
        self.assertEqual(captured["body"]["options"]["num_predict"], 1600)
        # System prompt gets its own message (role=system) per Ollama convention.
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")
        self.assertEqual(captured["body"]["messages"][1]["role"], "user")
        self.assertNotIn("format", captured["body"])

    def test_request_text_surfaces_http_error_as_ok_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="llama down")

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_text(
            request_kind="test.error",
            system="",
            prompt="anything",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "http_500")
        self.assertIn("llama down", result.error_message or "")
        self.assertIsNone(result.text)

    def test_request_text_surfaces_timeout_visibly(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("boom", request=request)

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_text(
            request_kind="test.timeout",
            system="",
            prompt="anything",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "timeout")
        self.assertIn("boom", result.error_message or "")


class OllamaRequestJsonTests(unittest.TestCase):
    def test_request_json_parses_format_json_response(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json=_ok_payload('{"answer": "mitosis", "confidence": 0.9}'))

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_json(
            request_kind="test.json",
            system="return JSON",
            prompt="label this",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"answer": "mitosis", "confidence": 0.9})
        self.assertEqual(captured["body"]["format"], "json")

    def test_request_json_falls_back_to_rescue_parse_when_model_wraps_prose(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=_ok_payload('Here is the JSON:\n{"x": 1}'),
            )

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_json(
            request_kind="test.rescue",
            system="return JSON",
            prompt="label",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"x": 1})

    def test_request_json_uses_fallback_on_http_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_json(
            request_kind="test.json.fallback",
            system="",
            prompt="",
            fallback={"ok": False, "reason": "no model"},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.json_payload, {"ok": False, "reason": "no model"})


class OllamaRequestToolCallTests(unittest.TestCase):
    TOOL = {
        "name": "submit_grounded_answer",
        "description": "Return a grounded answer payload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "claims": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["summary", "claims"],
        },
    }

    def test_request_tool_call_passes_schema_as_format(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(
                200,
                json=_ok_payload('{"summary": "ok", "claims": []}'),
            )

        client = OllamaClient(http_client=_mock_transport(handler))
        result = client.request_tool_call(
            request_kind="tutor.grounded_answer",
            system="You are Einstein.",
            prompt="Explain mitosis.",
            tool=self.TOOL,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.json_payload, {"summary": "ok", "claims": []})
        # The schema must flow through as `format` so Ollama constrains output.
        self.assertEqual(captured["body"]["format"], self.TOOL["input_schema"])
        # Tool description should be prepended to the system prompt so the
        # model understands its job even without Claude-style tool_use.
        system_msg = next(m for m in captured["body"]["messages"] if m["role"] == "system")
        self.assertIn("submit_grounded_answer", system_msg["content"])
        self.assertIn("grounded answer", system_msg["content"].lower())

    def test_request_tool_call_rejects_invalid_schema(self) -> None:
        client = OllamaClient(
            http_client=_mock_transport(lambda r: httpx.Response(200, json=_ok_payload("")))
        )
        result = client.request_tool_call(
            request_kind="tutor.grounded_answer",
            system="",
            prompt="",
            tool={"name": "x", "description": "", "input_schema": "not a dict"},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_tool_schema")


class OllamaConfigTests(unittest.TestCase):
    def test_env_vars_drive_defaults(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "OLLAMA_BASE_URL": "http://ollama.internal:11434/",
                "OLLAMA_MODEL_FAST": "llama3.2:1b",
                "OLLAMA_MODEL_BALANCED": "qwen2.5:7b",
                "OLLAMA_MODEL_DEEP": "llama3.1:70b-instruct-q4",
                "OLLAMA_TIMEOUT_SECONDS": "120",
                "OLLAMA_KEEP_ALIVE": "10m",
            },
            clear=False,
        ):
            client = OllamaClient()

        # Trailing slash on base URL is normalised.
        self.assertEqual(client.base_url, "http://ollama.internal:11434")
        self.assertEqual(client.fast_model, "llama3.2:1b")
        self.assertEqual(client.balanced_model, "qwen2.5:7b")
        self.assertEqual(client.deep_model, "llama3.1:70b-instruct-q4")
        self.assertEqual(client.timeout_seconds, 120.0)
        self.assertEqual(client.keep_alive, "10m")
        self.assertEqual(client.model_for_task("fast"), "llama3.2:1b")
        self.assertEqual(client.model_for_task("deep"), "llama3.1:70b-instruct-q4")
        self.assertEqual(client.model_for_task("balanced"), "qwen2.5:7b")


if __name__ == "__main__":
    unittest.main()
