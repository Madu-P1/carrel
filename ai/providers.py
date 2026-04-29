"""Provider selection for Carrel AI calls.

The app has two peer LLM providers now:

* `ClaudeRouter` in `ai/router.py` — production path. Ships with tool_use,
  prompt caching, and the eval-gated grounded-answer pipeline.
* `OllamaClient` in `ai/ollama.py` — local-first path. Same call surface,
  same `ClaudeCallResult` shape, no API key required.

Everything downstream (tutor, concept extraction, etc.) should import
`get_default_provider()` from here instead of reaching into either module
directly. That keeps provider selection in one place and lets us flip
between Claude and Ollama via env flag without refactoring callers.

Env vars:

    CARREL_AI_PROVIDER      "auto" (default) | "claude" | "ollama" | "off"
    EINSTEIN_AI_PROVIDER    legacy alias, still honoured. The 2026-04-29
                            rename keeps both names working until the
                            deferred-rename pass migrates the rest of the
                            system identifiers (DB filename, bundle ID).

      auto    prefer Claude when ANTHROPIC_API_KEY is set, otherwise Ollama
              when OLLAMA_BASE_URL resolves to something non-empty.
      claude  force ClaudeRouter. Surfaces ok=False when the API key is
              missing rather than silently falling back.
      ollama  force OllamaClient. Same visibility contract.
      off     return a NullProvider that always returns ok=False with
              error_code="ai_disabled". Tests, kiosk mode, privacy lockdown.

Plus the provider-specific env the two modules already read for themselves
(ANTHROPIC_*, OLLAMA_*). This module does not duplicate those.
"""

from __future__ import annotations

import os
from typing import Any, Literal, Protocol, runtime_checkable

from ai.ollama import OllamaClient, get_default_ollama_client
from ai.router import ClaudeCallResult, ClaudeRouter, get_default_router

ProviderKind = Literal["claude", "ollama", "null"]


@runtime_checkable
class AIProvider(Protocol):
    """Minimal surface shared by every backend. Matches `ClaudeRouter` /
    `OllamaClient`. Anything the tutor or extraction pipeline calls must be
    here."""

    def ai_enabled(self) -> bool: ...

    def model_for_task(self, task: Any) -> str: ...

    def request_text(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult: ...

    def request_json(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        fallback: Any = None,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult: ...

    def request_tool_call(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        tool: dict[str, Any],
        max_tokens: int = 2400,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult: ...


class NullProvider:
    """Provider of last resort. Every call returns a visible `ok=False`
    `ClaudeCallResult` with `error_code="ai_disabled"`. Used when
    `CARREL_AI_PROVIDER=off` (or the legacy `EINSTEIN_AI_PROVIDER=off`)
    or when auto-selection finds no candidate.

    This is intentionally not silent. Downstream tutor code inspects
    `ok`/`error_code` and renders an "AI synthesis unavailable" fallback,
    same as any other provider failure — no deception about what the app
    is doing.
    """

    kind: ProviderKind = "null"

    def ai_enabled(self) -> bool:
        return False

    def model_for_task(self, task: Any) -> str:
        del task
        return "null"

    def request_text(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del system, prompt, max_tokens, cache_system_prompt
        return _null_result(task=task, request_kind=request_kind)

    def request_json(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        fallback: Any = None,
        max_tokens: int = 1600,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del system, prompt, max_tokens, cache_system_prompt
        result = _null_result(task=task, request_kind=request_kind)
        if fallback is not None:
            from dataclasses import replace

            return replace(result, json_payload=fallback)
        return result

    def request_tool_call(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        tool: dict[str, Any],
        max_tokens: int = 2400,
        task: Any = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del system, prompt, tool, max_tokens, cache_system_prompt
        return _null_result(task=task, request_kind=request_kind)


def _null_result(*, task: Any, request_kind: str) -> ClaudeCallResult:
    return ClaudeCallResult(
        ok=False,
        task=task,
        model="null",
        request_kind=request_kind,
        text=None,
        json_payload=None,
        error_code="ai_disabled",
        error_message="AI is disabled (CARREL_AI_PROVIDER=off) or no provider is configured.",
        latency_ms=0.0,
        input_tokens=None,
        output_tokens=None,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier=None,
        stop_reason=None,
        request_id=None,
    )


def _claude_has_key() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def _ollama_has_endpoint() -> bool:
    # Default base URL in the OllamaClient is localhost, so "configured" means
    # either the user set OLLAMA_BASE_URL explicitly or they're on the local
    # default. We can't verify reachability without paying a network round-trip,
    # so we treat presence of the default URL as "configured" and let call-time
    # errors surface via ok=False.
    return bool(os.getenv("OLLAMA_BASE_URL", "").strip()) or True


def select_provider(kind: str | None = None) -> AIProvider:
    """Resolve the active provider.

    `kind` overrides the env var when provided. Accepts:
    "claude" | "ollama" | "auto" | "off". Unknown values fall back to
    "auto".

    Env var resolution: prefer `CARREL_AI_PROVIDER` (canonical post-
    rename), fall back to legacy `EINSTEIN_AI_PROVIDER` so existing
    `.env` files keep working without a forced edit. The legacy name
    will stay supported until the deferred-rename pass migrates the
    rest of the system identifiers (DB filename, bundle ID).
    """
    env_value = os.getenv("CARREL_AI_PROVIDER") or os.getenv(
        "EINSTEIN_AI_PROVIDER", "auto"
    )
    raw = (kind or env_value).strip().lower()
    if raw == "off":
        return NullProvider()
    if raw == "claude":
        return get_default_router()
    if raw == "ollama":
        return get_default_ollama_client()

    # auto: pick the best available without paying a network probe.
    if _claude_has_key():
        return get_default_router()
    if _ollama_has_endpoint():
        return get_default_ollama_client()
    return NullProvider()


_DEFAULT_PROVIDER: AIProvider | None = None


def get_default_provider() -> AIProvider:
    """Module-level singleton matching `get_default_router()`'s pattern.

    Stays cached for the lifetime of the process; callers that need a
    different provider (e.g. the eval harness forcing Claude for scoring)
    should call `select_provider(kind=...)` directly instead.
    """
    global _DEFAULT_PROVIDER
    if _DEFAULT_PROVIDER is None:
        _DEFAULT_PROVIDER = select_provider()
    return _DEFAULT_PROVIDER


def reset_default_provider() -> None:
    """Drop the cached provider. Tests and env reconfigurations use this."""
    global _DEFAULT_PROVIDER
    _DEFAULT_PROVIDER = None


# Re-export for clean import path: `from ai.providers import ClaudeRouter, OllamaClient`
__all__ = [
    "AIProvider",
    "ClaudeCallResult",
    "ClaudeRouter",
    "NullProvider",
    "OllamaClient",
    "ProviderKind",
    "get_default_provider",
    "reset_default_provider",
    "select_provider",
]
