import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_LOGGER_NAMESPACE = "einstein"
_CONFIGURED = False
_REDACTED = "[redacted]"
_URL_REDACTED = "[redacted-url]"
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "token",
    "secret",
    "password",
)
_LOCAL_CONTENT_KEY_PARTS = (
    "filename",
    "file_name",
    "storage_name",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, str) and event:
            payload["event"] = event
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload.update(redact_context(context))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def configure_backend_logging(log_dir: Path) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAMESPACE)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = JsonFormatter()

    file_handler = RotatingFileHandler(
        log_dir / "einstein-backend.jsonl",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAMESPACE}.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **context: Any) -> None:
    logger.log(level, event, extra={"event": event, "context": redact_context(context)})


def redact_context(value: Any) -> Any:
    return _redact_value(value)


def _redact_value(value: Any, key: str | None = None) -> Any:
    if _is_secret_key(key):
        return _URL_REDACTED if key and "url" in key.lower() else _REDACTED

    if isinstance(value, dict):
        return {str(k): _redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, key) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, key) for item in value)
    if isinstance(value, str):
        return _redact_url_like_string(value)
    return value


def _is_secret_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower().replace("-", "_")
    return (
        "url" in normalized
        or any(part in normalized for part in _SECRET_KEY_PARTS)
        or any(part in normalized for part in _LOCAL_CONTENT_KEY_PARTS)
    )


def _redact_url_like_string(value: str) -> str:
    if "://" not in value:
        return value

    def replace(match: re.Match[str]) -> str:
        parsed = urlsplit(match.group(0))
        if not parsed.scheme or not parsed.netloc:
            return _URL_REDACTED
        return f"{parsed.scheme}://{parsed.netloc}/***"

    return _URL_PATTERN.sub(replace, value)
