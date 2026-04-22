import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

from app_logging import get_logger, log_event

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    _load_dotenv = None  # type: ignore[assignment]

try:
    import anthropic as _anthropic
except ImportError:  # pragma: no cover - optional dependency
    _anthropic = None  # type: ignore[assignment]

load_dotenv: Any = _load_dotenv
anthropic: Any = _anthropic

if load_dotenv is not None:
    from pathlib import Path

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path, override=True)


ClaudeTask = Literal["fast", "balanced", "deep"]


@dataclass(frozen=True)
class ClaudeCallResult:
    ok: bool
    task: ClaudeTask
    model: str
    request_kind: str
    text: str | None
    json_payload: Any | None
    error_code: str | None
    error_message: str | None
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    cache_hit: bool
    service_tier: str | None
    stop_reason: str | None
    request_id: str | None


def _extract_text_block(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif hasattr(item, "type") and getattr(item, "type", None) == "text":
                parts.append(str(getattr(item, "text", "") or ""))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _extract_json_from_text(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        alt_start = text.find("[")
        candidates = [position for position in (start, alt_start) if position != -1]
        if not candidates:
            return None
        try:
            return json.loads(text[min(candidates) :])
        except json.JSONDecodeError:
            return None


def _extract_tool_payload(content: Any, tool_name: str) -> Any | None:
    items = content if isinstance(content, list) else [content]
    for item in items:
        if isinstance(item, dict):
            item_type = item.get("type")
            item_name = item.get("name")
            item_input = item.get("input")
        else:
            item_type = getattr(item, "type", None)
            item_name = getattr(item, "name", None)
            item_input = getattr(item, "input", None)
        if item_type == "tool_use" and item_name == tool_name:
            return item_input
    return None


def _classify_claude_exception(exc: BaseException) -> tuple[str, str]:
    """Map an Anthropic SDK (or generic) exception to a stable (code, message).

    Stability matters: tutor/services code stores the code in the grounded-answer
    response body and the frontend can branch on it. Using HTTP status codes for
    API failures keeps the surface consistent with the Ollama provider
    (`http_429`, `http_500`, ...) and insulates callers from SDK class renames.
    User-facing message is the SDK message verbatim; it is already short and
    does not include the API key.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return f"http_{status}", str(exc)
    name = exc.__class__.__name__
    # Normalize a few common SDK names to stable codes.
    if name in {"APITimeoutError", "APIConnectionError"}:
        return "timeout" if name == "APITimeoutError" else "connection_error", str(exc)
    return name, str(exc)


class ClaudeRouter:
    def __init__(self) -> None:
        self._logger = get_logger("ai.claude")
        self.fast_model = os.getenv("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5")
        self.balanced_model = os.getenv("ANTHROPIC_MODEL_BALANCED", "claude-sonnet-4-6")
        self.deep_model = os.getenv("ANTHROPIC_MODEL_DEEP", "claude-opus-4-7")
        self.default_service_tier = os.getenv("ANTHROPIC_SERVICE_TIER", "auto")

    def _client(self) -> Any | None:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key or anthropic is None:
            return None
        # Bounded timeout so a wedged API call can't hang a tutor turn for the
        # SDK default (10 min). max_retries lets the SDK handle 429 + 5xx with
        # exponential backoff that honors the Retry-After header.
        return anthropic.Anthropic(
            api_key=api_key,
            timeout=60.0,
            max_retries=3,
        )

    def ai_enabled(self) -> bool:
        return self._client() is not None

    def model_for_task(self, task: ClaudeTask) -> str:
        if task == "fast":
            return self.fast_model
        if task == "deep":
            return self.deep_model
        return self.balanced_model

    def _system_payload(self, system: str, *, cache_system_prompt: bool) -> str | list[dict[str, Any]]:
        cleaned = system.strip()
        if not cache_system_prompt or not cleaned:
            return cleaned
        return [
            {
                "type": "text",
                "text": cleaned,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _usage_metric(self, usage: Any, field_name: str) -> int | None:
        value = getattr(usage, field_name, None)
        return int(value) if isinstance(value, (int, float)) else None

    def request_text(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: ClaudeTask = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        model = self.model_for_task(task)
        start = time.perf_counter()
        client = self._client()
        if client is None:
            result = ClaudeCallResult(
                ok=False,
                task=task,
                model=model,
                request_kind=request_kind,
                text=None,
                json_payload=None,
                error_code="missing_api_key",
                error_message="ANTHROPIC_API_KEY is not configured or the anthropic package is unavailable.",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                input_tokens=None,
                output_tokens=None,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
                cache_hit=False,
                service_tier=None,
                stop_reason=None,
                request_id=None,
            )
            self._log_result(result)
            return result

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=self._system_payload(system, cache_system_prompt=cache_system_prompt),
                messages=[{"role": "user", "content": prompt}],
                service_tier=self.default_service_tier,
            )
        except Exception as exc:  # pragma: no cover - network / provider failures
            error_code, error_message = _classify_claude_exception(exc)
            result = ClaudeCallResult(
                ok=False,
                task=task,
                model=model,
                request_kind=request_kind,
                text=None,
                json_payload=None,
                error_code=error_code,
                error_message=error_message,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                input_tokens=None,
                output_tokens=None,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
                cache_hit=False,
                service_tier=None,
                stop_reason=None,
                request_id=None,
            )
            self._log_result(result)
            return result

        usage = getattr(response, "usage", None)
        text = _extract_text_block(getattr(response, "content", "")).strip() or None
        cache_read_input_tokens = self._usage_metric(usage, "cache_read_input_tokens")
        result = ClaudeCallResult(
            ok=bool(text),
            task=task,
            model=model,
            request_kind=request_kind,
            text=text,
            json_payload=None,
            error_code=None if text else "empty_response",
            error_message=None if text else "Claude returned no text blocks.",
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            input_tokens=self._usage_metric(usage, "input_tokens"),
            output_tokens=self._usage_metric(usage, "output_tokens"),
            cache_creation_input_tokens=self._usage_metric(usage, "cache_creation_input_tokens"),
            cache_read_input_tokens=cache_read_input_tokens,
            cache_hit=bool(cache_read_input_tokens),
            service_tier=str(getattr(usage, "service_tier", "") or "") or None,
            stop_reason=str(getattr(response, "stop_reason", "") or "") or None,
            request_id=str(getattr(response, "id", "") or "") or None,
        )
        self._log_result(result)
        return result

    def request_json(
        self,
        *,
        request_kind: str,
        system: str,
        prompt: str,
        max_tokens: int = 1600,
        task: ClaudeTask = "balanced",
        cache_system_prompt: bool = True,
    ) -> ClaudeCallResult:
        text_result = self.request_text(
            request_kind=request_kind,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            task=task,
            cache_system_prompt=cache_system_prompt,
        )
        if not text_result.ok or not text_result.text:
            return text_result

        payload = _extract_json_from_text(text_result.text)
        if payload is None:
            result = ClaudeCallResult(
                ok=False,
                task=text_result.task,
                model=text_result.model,
                request_kind=text_result.request_kind,
                text=text_result.text,
                json_payload=None,
                error_code="invalid_json",
                error_message="Claude returned text, but it was not valid JSON.",
                latency_ms=text_result.latency_ms,
                input_tokens=text_result.input_tokens,
                output_tokens=text_result.output_tokens,
                cache_creation_input_tokens=text_result.cache_creation_input_tokens,
                cache_read_input_tokens=text_result.cache_read_input_tokens,
                cache_hit=text_result.cache_hit,
                service_tier=text_result.service_tier,
                stop_reason=text_result.stop_reason,
                request_id=text_result.request_id,
            )
            self._log_result(result)
            return result

        result = ClaudeCallResult(
            ok=True,
            task=text_result.task,
            model=text_result.model,
            request_kind=text_result.request_kind,
            text=text_result.text,
            json_payload=payload,
            error_code=None,
            error_message=None,
            latency_ms=text_result.latency_ms,
            input_tokens=text_result.input_tokens,
            output_tokens=text_result.output_tokens,
            cache_creation_input_tokens=text_result.cache_creation_input_tokens,
            cache_read_input_tokens=text_result.cache_read_input_tokens,
            cache_hit=text_result.cache_hit,
            service_tier=text_result.service_tier,
            stop_reason=text_result.stop_reason,
            request_id=text_result.request_id,
        )
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
        model = self.model_for_task(task)
        start = time.perf_counter()
        client = self._client()
        if client is None:
            result = ClaudeCallResult(
                ok=False,
                task=task,
                model=model,
                request_kind=request_kind,
                text=None,
                json_payload=None,
                error_code="missing_api_key",
                error_message="ANTHROPIC_API_KEY is not configured or the anthropic package is unavailable.",
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                input_tokens=None,
                output_tokens=None,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
                cache_hit=False,
                service_tier=None,
                stop_reason=None,
                request_id=None,
            )
            self._log_result(result)
            return result

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=self._system_payload(system, cache_system_prompt=cache_system_prompt),
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice={"type": "tool", "name": str(tool.get("name") or "")},
                service_tier=self.default_service_tier,
            )
        except Exception as exc:  # pragma: no cover - network / provider failures
            error_code, error_message = _classify_claude_exception(exc)
            result = ClaudeCallResult(
                ok=False,
                task=task,
                model=model,
                request_kind=request_kind,
                text=None,
                json_payload=None,
                error_code=error_code,
                error_message=error_message,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                input_tokens=None,
                output_tokens=None,
                cache_creation_input_tokens=None,
                cache_read_input_tokens=None,
                cache_hit=False,
                service_tier=None,
                stop_reason=None,
                request_id=None,
            )
            self._log_result(result)
            return result

        usage = getattr(response, "usage", None)
        content = getattr(response, "content", "")
        text = _extract_text_block(content).strip() or None
        payload = _extract_tool_payload(content, str(tool.get("name") or ""))
        cache_read_input_tokens = self._usage_metric(usage, "cache_read_input_tokens")
        result = ClaudeCallResult(
            ok=isinstance(payload, dict),
            task=task,
            model=model,
            request_kind=request_kind,
            text=text,
            json_payload=payload if isinstance(payload, dict) else None,
            error_code=None if isinstance(payload, dict) else "no_tool_call",
            error_message=None if isinstance(payload, dict) else "Claude did not return a tool_use block.",
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            input_tokens=self._usage_metric(usage, "input_tokens"),
            output_tokens=self._usage_metric(usage, "output_tokens"),
            cache_creation_input_tokens=self._usage_metric(usage, "cache_creation_input_tokens"),
            cache_read_input_tokens=cache_read_input_tokens,
            cache_hit=bool(cache_read_input_tokens),
            service_tier=str(getattr(usage, "service_tier", "") or "") or None,
            stop_reason=str(getattr(response, "stop_reason", "") or "") or None,
            request_id=str(getattr(response, "id", "") or "") or None,
        )
        self._log_result(result)
        return result

    def _log_result(self, result: ClaudeCallResult) -> None:
        log_event(
            self._logger,
            logging.INFO if result.ok else logging.ERROR,
            "claude_call",
            ok=result.ok,
            task=result.task,
            model=result.model,
            request_kind=result.request_kind,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
            cache_hit=result.cache_hit,
            service_tier=result.service_tier,
            stop_reason=result.stop_reason,
            error_code=result.error_code,
            error_message=result.error_message,
            request_id=result.request_id,
        )


_DEFAULT_ROUTER: ClaudeRouter | None = None


def get_default_router() -> ClaudeRouter:
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        _DEFAULT_ROUTER = ClaudeRouter()
    return _DEFAULT_ROUTER
