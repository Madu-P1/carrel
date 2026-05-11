"""Provider selection for Carrel AI calls.

The app has three peer LLM providers:

* `ClaudeRouter` in `ai/router.py` — paid Pro path. Ships with tool_use,
  prompt caching, and the eval-gated grounded-answer pipeline.
* `AFMClient` in `ai/afm_client.py` — on-device free tier on macOS 26+
  Apple Silicon. Talks to the `EinsteinAFMBridge` Swift sidecar over
  stdin/stdout JSON. Same `ClaudeCallResult` shape, zero download.
* `OllamaClient` in `ai/ollama.py` — legacy local fallback for users
  on macOS 14/15 or Intel. Same call surface.

Everything downstream (tutor, concept extraction, etc.) should import
`get_default_provider()` from here instead of reaching into any provider
module directly. That keeps provider selection in one place and lets us
flip between backends via env flag without refactoring callers.

Env vars:

    CARREL_AI_PROVIDER      "auto" (default) | "claude" | "afm" | "ollama" | "off"
    EINSTEIN_AI_PROVIDER    legacy alias, still honoured. The 2026-04-29
                            rename keeps both names working until the
                            deferred-rename pass migrates the rest of the
                            system identifiers (DB filename, bundle ID).

      auto    Claude (when ANTHROPIC_API_KEY set) → AFM (macOS 26+
              Apple Silicon with the bridge built) → Ollama → off.
      claude  force ClaudeRouter. Surfaces ok=False when the API key is
              missing rather than silently falling back.
      afm     force AFMClient. Surfaces ok=False with a specific
              error_code when Apple Intelligence is disabled or the
              bridge binary is missing.
      ollama  force OllamaClient. Same visibility contract.
      off     return a NullProvider that always returns ok=False with
              error_code="ai_disabled". Tests, kiosk mode, privacy lockdown.

Plus the provider-specific env the modules read for themselves
(ANTHROPIC_*, AFM_*, OLLAMA_*). This module does not duplicate those.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any, Literal, Protocol, runtime_checkable

from ai.afm_client import AFMClient, get_default_afm_client
from ai.ollama import OllamaClient, get_default_ollama_client
from ai.router import ClaudeCallResult, ClaudeRouter, get_default_router

ProviderKind = Literal["claude", "ollama", "afm", "null"]


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

    def supports_grounded_answer(self) -> bool:
        """True when the provider implements `request_grounded_answer`.

        Optional capability: only AFM ships a true grounded-answer
        flow today. Claude and Ollama route grounded questions through
        the regular tool-call path, which yields a different json
        shape. Callers should check this before dispatching.
        """
        ...

    def request_grounded_answer(
        self,
        *,
        request_kind: str,
        system: str,
        question: str,
        chunks: Any,
        max_tokens: int = 600,
        task: Any = "balanced",
    ) -> ClaudeCallResult:
        """Grounded-answer flow: emit a tutor-schema payload with
        `claims` + per-claim `citations` derived from `chunks`.

        `chunks` is a sequence of `GroundedChunk`-shaped objects.
        Providers that don't implement this should return ok=False
        with `error_code="grounded_unsupported"` so callers fall back
        to the tool-call path.
        """
        ...


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

    def supports_grounded_answer(self) -> bool:
        return False

    def request_grounded_answer(
        self,
        *,
        request_kind: str,
        system: str,
        question: str,
        chunks: Any,
        max_tokens: int = 600,
        task: Any = "balanced",
    ) -> ClaudeCallResult:
        del system, question, chunks, max_tokens
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


def _afm_available() -> bool:
    """True on macOS 26+ Apple Silicon when the AFMBridge binary exists.

    Cheap check, no model load. Apple Intelligence enabled-state is
    surfaced at call time via the bridge as
    `error_code="apple_intelligence_not_enabled"` so the UI can deep-link
    the user into System Settings rather than the provider silently
    falling back here.
    """
    if sys.platform != "darwin":
        return False
    if platform.machine() != "arm64":
        return False
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return False
    if major < 26:
        return False
    from ai.native_bridge_paths import AFM_BRIDGE_CANDIDATES, find_binary

    return find_binary(AFM_BRIDGE_CANDIDATES) is not None


def select_provider(kind: str | None = None) -> AIProvider:
    """Resolve the active provider.

    `kind` overrides the env var when provided. Accepts:
    "claude" | "ollama" | "afm" | "auto" | "off". Unknown values fall
    back to "auto".

    Env var resolution: prefer `CARREL_AI_PROVIDER` (canonical post-
    rename), fall back to legacy `EINSTEIN_AI_PROVIDER` so existing
    `.env` files keep working without a forced edit. The legacy name
    will stay supported until the deferred-rename pass migrates the
    rest of the system identifiers (DB filename, bundle ID).

    Auto-resolution order:
      1. Claude (when ANTHROPIC_API_KEY is set) for paid Pro tier.
      2. Apple Foundation Models (macOS 26+ Apple Silicon with the
         EinsteinAFMBridge binary present) for the on-device free tier.
      3. Ollama, the legacy local fallback for macOS 14/15 or Intel.
      4. NullProvider when nothing is configured.
    """
    env_value = os.getenv("CARREL_AI_PROVIDER") or os.getenv("EINSTEIN_AI_PROVIDER", "auto")
    raw = (kind or env_value).strip().lower()
    if raw == "off":
        return NullProvider()
    if raw == "claude":
        return get_default_router()
    if raw == "ollama":
        return get_default_ollama_client()
    if raw == "afm":
        return get_default_afm_client()

    # auto: pick the best available without paying a network probe.
    if _claude_has_key():
        return get_default_router()
    if _afm_available():
        return get_default_afm_client()
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


# Re-export for clean import path: `from ai.providers import ClaudeRouter, OllamaClient, AFMClient`
__all__ = [
    "AFMClient",
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
