"""Ollama provider for Carrel.

Peer to `ai/router.py::ClaudeRouter`, same call surface, same result shape.
Anything in the app that currently calls a `ClaudeRouter` method can accept
an `OllamaClient` in its place via the `AIProvider` protocol in
`ai/providers.py`.

Design choices specific to Carrel:

* Returns `ClaudeCallResult` (not a new type) so tutor/concept-extraction code
  that already destructures that dataclass keeps working unchanged.
* `request_tool_call` uses Ollama's JSON-schema format mode to approximate
  Claude's `tool_use`: the tool's `input_schema` is passed as `format`,
  Ollama constrains output to that schema, we return the parsed dict as
  `json_payload`. No special tool_use block is needed.
* No streaming here yet. The tutor's current path is request/response and the
  eval harness measures full-answer latency. Streaming is additive and can
  land in a follow-up without rewriting this module.
* Config centralised in env vars — never hardcode base URL in business logic.

Env vars (see `.env.example`):
    OLLAMA_BASE_URL          default "http://127.0.0.1:11434"
    OLLAMA_MODEL_FAST        default "llama3.2:3b"
    OLLAMA_MODEL_BALANCED    default "llama3.1:8b"
    OLLAMA_MODEL_DEEP        default "llama3.1:70b"
    OLLAMA_TIMEOUT_SECONDS   default "60"
    OLLAMA_KEEP_ALIVE        default "5m" (Ollama's own keep-alive string)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Literal

import httpx

from ai.router import ClaudeCallResult, _extract_json_from_text
from app_logging import get_logger, log_event

ClaudeTask = Literal["fast", "balanced", "deep"]  # identical labels, different backend


DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_FAST_MODEL = "llama3.2:3b"
DEFAULT_BALANCED_MODEL = "llama3.1:8b"
DEFAULT_DEEP_MODEL = "llama3.1:70b"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_KEEP_ALIVE = "5m"


class OllamaClient:
    """Local LLM provider backed by Ollama's HTTP API.

    Same method signatures as `ClaudeRouter`; returns the same
    `ClaudeCallResult` shape so downstream code does not branch on provider.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        fast_model: str | None = None,
        balanced_model: str | None = None,
        deep_model: str | None = None,
        timeout_seconds: float | None = None,
        keep_alive: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._logger = get_logger("ai.ollama")
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.fast_model = fast_model or os.getenv("OLLAMA_MODEL_FAST") or DEFAULT_FAST_MODEL
        self.balanced_model = (
            balanced_model or os.getenv("OLLAMA_MODEL_BALANCED") or DEFAULT_BALANCED_MODEL
        )
        self.deep_model = deep_model or os.getenv("OLLAMA_MODEL_DEEP") or DEFAULT_DEEP_MODEL
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.keep_alive = keep_alive or os.getenv("OLLAMA_KEEP_ALIVE") or DEFAULT_KEEP_ALIVE
        self._http_client = http_client  # injected in tests

    # ---------- surface parity with ClaudeRouter ----------

    def ai_enabled(self) -> bool:
        """True if the Ollama endpoint appears configured.

        We do NOT ping on startup (would add latency to boot and drag the
        cold-launch budget). A real call will surface `ok=False` with a
        typed error if the endpoint is wrong or down; callers rely on that
        contract rather than a pre-check.
        """
        return bool(self.base_url)

    def model_for_task(self, task: ClaudeTask) -> str:
        if task == "fast":
            return self.fast_model
        if task == "deep":
            return self.deep_model
        return self.balanced_model

    def request_text(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: ClaudeTask = "balanced",
        cache_system_prompt: bool = True,  # accepted for protocol parity; no-op for Ollama
    ) -> ClaudeCallResult:
        del cache_system_prompt  # Ollama has no ephemeral prompt cache concept
        return self._chat(
            request_kind=request_kind,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            task=task,
            response_format=None,
        )

    def request_json(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        fallback: Any = None,
        max_tokens: int = 1600,
        task: ClaudeTask = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        del cache_system_prompt
        result = self._chat(
            request_kind=request_kind,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            task=task,
            response_format="json",
        )
        if result.ok and result.json_payload is None and result.text:
            # Model ignored format=json; try to rescue a JSON object from prose.
            rescued = _extract_json_from_text(result.text)
            if rescued is not None:
                return _replace_result(result, json_payload=rescued)
        if not result.ok and fallback is not None:
            return _replace_result(result, json_payload=fallback)
        return result

    def request_tool_call(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        tool: dict[str, Any],
        max_tokens: int = 2400,
        task: ClaudeTask = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        """Ollama equivalent of Claude tool_use.

        Ollama 0.5+ accepts a JSON Schema as `format`, which constrains output
        to match the schema. We pass the tool's `input_schema` directly. The
        tool `name` and `description` get prepended to the system prompt so
        the model knows what it's supposed to be producing.
        """
        del cache_system_prompt
        tool_name = str(tool.get("name") or "submit").strip() or "submit"
        tool_description = str(tool.get("description") or "").strip()
        input_schema = tool.get("input_schema")
        if not isinstance(input_schema, dict):
            return _error_result(
                task=task,
                model=self.model_for_task(task),
                request_kind=request_kind,
                error_code="invalid_tool_schema",
                error_message="tool['input_schema'] must be a dict matching JSON Schema.",
                latency_ms=0.0,
            )

        system_with_tool = system.strip()
        preamble = (
            f"You must respond by populating the `{tool_name}` payload.\n"
            f"{tool_description}\n"
            "Your entire response MUST be a single JSON object matching the required schema. "
            "Do not include explanations, markdown, or text outside the JSON object."
        )
        system_with_tool = (
            (preamble + "\n\n" + system_with_tool).strip() if system_with_tool else preamble
        )

        return self._chat(
            request_kind=request_kind,
            system=system_with_tool,
            prompt=prompt,
            max_tokens=max_tokens,
            task=task,
            response_format=input_schema,
        )

    def supports_grounded_answer(self) -> bool:
        """Ollama has no @Generable-equivalent. Callers route grounded
        questions through the regular tool-call path."""
        return False

    def request_grounded_answer(
        self,
        *,
        request_kind: str,
        system: str,
        question: str,
        chunks: Any,
        max_tokens: int = 600,
        task: ClaudeTask = "balanced",
    ) -> ClaudeCallResult:
        del system, question, chunks, max_tokens
        return _error_result(
            task=task,
            model=self.model_for_task(task),
            request_kind=request_kind,
            error_code="grounded_unsupported",
            error_message="OllamaClient has no dedicated grounded-answer endpoint; use request_tool_call.",
            latency_ms=0.0,
        )

    # ---------- internals ----------

    def _chat(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int,
        task: ClaudeTask,
        response_format: Any | None,
    ) -> ClaudeCallResult:
        model = self.model_for_task(task)
        request_id = f"ollama_{uuid.uuid4().hex[:12]}"
        start = time.perf_counter()

        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "messages": _build_messages(system, prompt),
            "options": {"num_predict": int(max_tokens)},
        }
        if response_format is not None:
            payload["format"] = response_format

        try:
            response_json = self._post_chat(payload)
        except httpx.TimeoutException as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return self._log_and_return(
                _error_result(
                    task=task,
                    model=model,
                    request_kind=request_kind,
                    error_code="timeout",
                    error_message=str(exc) or f"Ollama call exceeded {self.timeout_seconds}s",
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            )
        except httpx.HTTPStatusError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return self._log_and_return(
                _error_result(
                    task=task,
                    model=model,
                    request_kind=request_kind,
                    error_code=f"http_{exc.response.status_code}",
                    error_message=_truncate(exc.response.text, 400) or str(exc),
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            )
        except httpx.HTTPError as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return self._log_and_return(
                _error_result(
                    task=task,
                    model=model,
                    request_kind=request_kind,
                    error_code="http_error",
                    error_message=str(exc),
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            )
        except Exception as exc:  # defensive; surface visibly rather than crash
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return self._log_and_return(
                _error_result(
                    task=task,
                    model=model,
                    request_kind=request_kind,
                    error_code="unexpected",
                    error_message=f"{type(exc).__name__}: {exc}",
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            )

        text = _extract_message_content(response_json)
        json_payload: Any | None = None
        if response_format is not None and text:
            try:
                json_payload = json.loads(text)
            except json.JSONDecodeError:
                json_payload = _extract_json_from_text(text)

        latency_ms = _latency_ms_from_response(response_json, fallback_start=start)
        input_tokens = _optional_int(response_json.get("prompt_eval_count"))
        output_tokens = _optional_int(response_json.get("eval_count"))
        stop_reason = _stop_reason_from_response(response_json)

        result = ClaudeCallResult(
            ok=True,
            task=task,
            model=model,
            request_kind=request_kind,
            text=text,
            json_payload=json_payload,
            error_code=None,
            error_message=None,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=None,
            cache_hit=False,
            service_tier=None,
            stop_reason=stop_reason,
            request_id=request_id,
        )
        return self._log_and_return(result)

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        if self._http_client is not None:
            response = self._http_client.post(url, json=payload)
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise httpx.HTTPError(f"Ollama returned non-object JSON: {type(data).__name__}")
        return data

    def _log_and_return(self, result: ClaudeCallResult) -> ClaudeCallResult:
        log_event(
            self._logger,
            20 if result.ok else 40,  # INFO / ERROR
            "ai.ollama.call",
            ok=result.ok,
            task=result.task,
            model=result.model,
            request_kind=result.request_kind,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            error_code=result.error_code,
            request_id=result.request_id,
        )
        return result


# ---------- helpers ----------


def _build_messages(system: str, prompt: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    cleaned_system = (system or "").strip()
    if cleaned_system:
        messages.append({"role": "system", "content": cleaned_system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _extract_message_content(response: dict[str, Any]) -> str:
    message = response.get("message") or {}
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _latency_ms_from_response(response: dict[str, Any], *, fallback_start: float) -> float:
    nanos = response.get("total_duration")
    if isinstance(nanos, (int, float)) and nanos > 0:
        return round(float(nanos) / 1_000_000.0, 2)
    return round((time.perf_counter() - fallback_start) * 1000, 2)


def _stop_reason_from_response(response: dict[str, Any]) -> str | None:
    if response.get("done_reason"):
        return str(response["done_reason"])
    if response.get("done") is True:
        return "stop"
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _truncate(value: str | None, limit: int) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _error_result(
    *,
    task: ClaudeTask,
    model: str,
    request_kind: str,
    error_code: str,
    error_message: str,
    latency_ms: float,
    request_id: str | None = None,
) -> ClaudeCallResult:
    return ClaudeCallResult(
        ok=False,
        task=task,
        model=model,
        request_kind=request_kind,
        text=None,
        json_payload=None,
        error_code=error_code,
        error_message=error_message,
        latency_ms=latency_ms,
        input_tokens=None,
        output_tokens=None,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
        cache_hit=False,
        service_tier=None,
        stop_reason=None,
        request_id=request_id,
    )


def _replace_result(result: ClaudeCallResult, **changes: Any) -> ClaudeCallResult:
    from dataclasses import replace

    return replace(result, **changes)


_DEFAULT_CLIENT: OllamaClient | None = None


def get_default_ollama_client() -> OllamaClient:
    """Module-level singleton. Mirrors `get_default_router()` in ai/router.py."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = OllamaClient()
    return _DEFAULT_CLIENT
