import os
import unittest
from types import SimpleNamespace
from unittest import mock

from ai.router import ClaudeRouter


class ClaudeRouterToolCallTests(unittest.TestCase):
    def test_request_tool_call_returns_tool_input_payload(self) -> None:
        fake_response = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="submit_grounded_answer",
                    input={
                        "summary": "Grounded summary.",
                        "claims": [],
                        "unsupported_spans": [],
                    },
                )
            ],
            usage=SimpleNamespace(
                input_tokens=123,
                output_tokens=45,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=12,
                service_tier="auto",
            ),
            stop_reason="tool_use",
            id="req_test_123",
        )

        client = SimpleNamespace(
            messages=SimpleNamespace(create=mock.Mock(return_value=fake_response))
        )
        fake_anthropic = SimpleNamespace(Anthropic=mock.Mock(return_value=client))

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with mock.patch("ai.router.anthropic", fake_anthropic):
                router = ClaudeRouter()
                result = router.request_tool_call(
                    request_kind="unit_test.tool_call",
                    system="You are a test helper.",
                    prompt="Answer with the tool.",
                    tool={
                        "name": "submit_grounded_answer",
                        "description": "Return a structured answer.",
                        "input_schema": {"type": "object"},
                    },
                )

        self.assertTrue(result.ok)
        self.assertEqual(
            {
                "summary": "Grounded summary.",
                "claims": [],
                "unsupported_spans": [],
            },
            result.json_payload,
        )
        self.assertTrue(result.cache_hit)
        create_kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(
            {"type": "tool", "name": "submit_grounded_answer"}, create_kwargs["tool_choice"]
        )
        self.assertEqual("submit_grounded_answer", create_kwargs["tools"][0]["name"])


if __name__ == "__main__":
    unittest.main()
