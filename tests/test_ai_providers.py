"""Tests for `ai/providers.py`. Provider selection + null fallback semantics."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from ai.ollama import OllamaClient
from ai.providers import (
    AIProvider,
    NullProvider,
    get_default_provider,
    reset_default_provider,
    select_provider,
)
from ai.router import ClaudeCallResult, ClaudeRouter


class SelectProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default_provider()

    def tearDown(self) -> None:
        reset_default_provider()

    def test_explicit_off_returns_null_provider(self) -> None:
        with mock.patch.dict(os.environ, {"EINSTEIN_AI_PROVIDER": "off"}, clear=False):
            provider = select_provider()
        self.assertIsInstance(provider, NullProvider)
        self.assertFalse(provider.ai_enabled())

    def test_explicit_claude_returns_claude_router_regardless_of_key(self) -> None:
        with mock.patch.dict(os.environ, {"EINSTEIN_AI_PROVIDER": "claude"}, clear=False):
            if "ANTHROPIC_API_KEY" in os.environ:
                del os.environ["ANTHROPIC_API_KEY"]
            provider = select_provider()
        # User explicitly asked for Claude. Surface visibly on missing key at
        # call time rather than silently substituting Ollama.
        self.assertIsInstance(provider, ClaudeRouter)

    def test_explicit_ollama_returns_ollama_client(self) -> None:
        with mock.patch.dict(os.environ, {"EINSTEIN_AI_PROVIDER": "ollama"}, clear=False):
            provider = select_provider()
        self.assertIsInstance(provider, OllamaClient)

    def test_explicit_afm_returns_afm_client(self) -> None:
        from ai.afm_client import AFMClient

        with mock.patch.dict(os.environ, {"EINSTEIN_AI_PROVIDER": "afm"}, clear=False):
            provider = select_provider()
        self.assertIsInstance(provider, AFMClient)

    def test_auto_prefers_afm_over_ollama_when_macos26_no_claude_key(self) -> None:
        from ai.afm_client import AFMClient

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["EINSTEIN_AI_PROVIDER"] = "auto"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("ai.providers._afm_available", return_value=True),
        ):
            provider = select_provider()
        self.assertIsInstance(provider, AFMClient)

    def test_auto_falls_back_to_ollama_when_afm_unavailable(self) -> None:
        # PR-P2: auto-select picks Ollama only when the user has
        # explicitly set OLLAMA_BASE_URL. Pre-PR-P2 this happened
        # unconditionally via an `or True` foot-gun that made the
        # fallback chain pick Ollama on every machine, broken
        # daemon or not.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["EINSTEIN_AI_PROVIDER"] = "auto"
        env["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("ai.providers._afm_available", return_value=False),
        ):
            provider = select_provider()
        self.assertIsInstance(provider, OllamaClient)

    def test_auto_prefers_claude_when_key_present(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"EINSTEIN_AI_PROVIDER": "auto", "ANTHROPIC_API_KEY": "sk-test-abc"},
            clear=False,
        ):
            provider = select_provider()
        self.assertIsInstance(provider, ClaudeRouter)

    def test_auto_falls_back_to_null_when_no_provider_configured(self) -> None:
        # PR-P2: when Claude has no key, AFM is unavailable, AND
        # OLLAMA_BASE_URL is not set, the fallback chain ends at
        # NullProvider so the UI can render a clear "no AI configured"
        # state. Pre-PR-P2 the chain incorrectly picked Ollama in this
        # scenario via an `or True` short-circuit, which then surfaced
        # as confusing http_error on the first call.
        from ai.providers import NullProvider

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["EINSTEIN_AI_PROVIDER"] = "auto"
        env.pop("OLLAMA_BASE_URL", None)
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("ai.providers._afm_available", return_value=False),
        ):
            provider = select_provider()
        self.assertIsInstance(provider, NullProvider)

    def test_unknown_value_falls_back_to_auto(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"EINSTEIN_AI_PROVIDER": "totally-bogus", "ANTHROPIC_API_KEY": "sk-x"},
            clear=False,
        ):
            provider = select_provider()
        self.assertIsInstance(provider, ClaudeRouter)


class NullProviderContractTests(unittest.TestCase):
    def test_null_provider_request_text_returns_visible_failure(self) -> None:
        null = NullProvider()
        result = null.request_text(request_kind="test", system="", prompt="")
        self.assertIsInstance(result, ClaudeCallResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ai_disabled")
        self.assertIsNone(result.text)
        self.assertIsNone(result.json_payload)

    def test_null_provider_request_json_honours_fallback(self) -> None:
        null = NullProvider()
        result = null.request_json(
            request_kind="test",
            system="",
            prompt="",
            fallback={"ok": False},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.json_payload, {"ok": False})

    def test_null_provider_request_tool_call_visible(self) -> None:
        null = NullProvider()
        result = null.request_tool_call(
            request_kind="test",
            system="",
            prompt="",
            tool={"name": "x", "description": "", "input_schema": {}},
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ai_disabled")


class ProviderProtocolTests(unittest.TestCase):
    """Structural check: every backend satisfies AIProvider at runtime."""

    def test_claude_router_is_ai_provider(self) -> None:
        self.assertIsInstance(ClaudeRouter(), AIProvider)

    def test_ollama_client_is_ai_provider(self) -> None:
        self.assertIsInstance(OllamaClient(), AIProvider)

    def test_null_provider_is_ai_provider(self) -> None:
        self.assertIsInstance(NullProvider(), AIProvider)

    def test_afm_client_is_ai_provider(self) -> None:
        from ai.afm_client import AFMClient

        self.assertIsInstance(AFMClient(), AIProvider)


class DefaultProviderSingletonTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_default_provider()

    def tearDown(self) -> None:
        reset_default_provider()

    def test_default_provider_caches_until_reset(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"EINSTEIN_AI_PROVIDER": "ollama"},
            clear=False,
        ):
            first = get_default_provider()
            second = get_default_provider()
        self.assertIs(first, second)
        reset_default_provider()
        with mock.patch.dict(
            os.environ,
            {"EINSTEIN_AI_PROVIDER": "off"},
            clear=False,
        ):
            third = get_default_provider()
        self.assertIsNot(first, third)
        self.assertIsInstance(third, NullProvider)


class DefaultProviderSignatureInvalidationTests(unittest.TestCase):
    """PR-P3: ``get_default_provider`` now auto-invalidates when the
    env vars that drive ``select_provider`` change. Tests pin the new
    contract so a future refactor that re-introduces a lifetime cache
    (the pre-PR-P3 behavior the audit flagged) fails loudly."""

    def setUp(self) -> None:
        reset_default_provider()

    def tearDown(self) -> None:
        reset_default_provider()

    def test_env_change_invalidates_without_explicit_reset(self) -> None:
        # The audit's exact scenario: settings UI writes
        # CARREL_AI_PROVIDER, the next call must see the new provider
        # WITHOUT the caller having to remember to call
        # reset_default_provider.
        from ai.providers import NullProvider

        with mock.patch.dict(
            os.environ,
            {"CARREL_AI_PROVIDER": "off"},
            clear=False,
        ):
            first = get_default_provider()
            self.assertIsInstance(first, NullProvider)

        # No reset; just change the env. Next call must re-select.
        with mock.patch.dict(
            os.environ,
            {"CARREL_AI_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:11434"},
            clear=False,
        ):
            second = get_default_provider()
            self.assertIsInstance(second, OllamaClient)

        # Sanity: the cache returned a different object.
        self.assertIsNot(first, second)

    def test_same_env_returns_cached_instance(self) -> None:
        # The signature check is presence-based, so two calls with the
        # same env state still hit the cache. No spurious re-selects.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["EINSTEIN_AI_PROVIDER"] = "off"
        with mock.patch.dict(os.environ, env, clear=True):
            first = get_default_provider()
            second = get_default_provider()
            third = get_default_provider()
        self.assertIs(first, second)
        self.assertIs(second, third)

    def test_signature_does_not_leak_api_key_value(self) -> None:
        # The signature must reflect ANTHROPIC_API_KEY *presence*, not
        # the key itself. A leaked log/trace of the signature should
        # not expose the key.
        from ai.providers import _provider_selection_signature

        with mock.patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-supersecret-FAKE"},
            clear=True,
        ):
            sig = _provider_selection_signature()
        self.assertNotIn("supersecret", sig)
        self.assertNotIn("FAKE", sig)
        self.assertNotIn("sk-", sig)
        # But it does reflect presence — a non-empty marker is in.
        self.assertIn("claude", sig)

    def test_signature_changes_when_claude_key_appears(self) -> None:
        # Power user adds ANTHROPIC_API_KEY mid-session. The auto path
        # should now pick Claude over previously-selected NullProvider.
        from ai.providers import ClaudeRouter, NullProvider

        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["CARREL_AI_PROVIDER"] = "auto"
        env.pop("OLLAMA_BASE_URL", None)

        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("ai.providers._afm_available", return_value=False),
        ):
            first = get_default_provider()
            self.assertIsInstance(first, NullProvider)

        env["ANTHROPIC_API_KEY"] = "sk-real-key-now"
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("ai.providers._afm_available", return_value=False),
        ):
            second = get_default_provider()
            self.assertIsInstance(second, ClaudeRouter)

    def test_explicit_reset_still_works(self) -> None:
        # reset_default_provider continues to function for test
        # fixtures and settings-write paths that want explicit
        # invalidation even when no env var changed.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["CARREL_AI_PROVIDER"] = "off"
        with mock.patch.dict(os.environ, env, clear=True):
            first = get_default_provider()
            reset_default_provider()
            second = get_default_provider()
        # Same signature, but reset forced a new instance.
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
