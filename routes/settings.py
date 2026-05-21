"""User-facing AI settings: provider choice + Claude API key.

Read/write surface behind ``/api/settings/ai``. The provider choice is
persisted to the existing ``app_settings`` table; the Claude API key is
persisted to the OS secret store (Keychain, with a memory fallback) and
is **never** written to SQLite, ``.env``, or any log line.

Runtime switching is hot-swap, no backend restart: a write mutates
``os.environ`` and drops the cached provider singletons so the next
request re-selects. ``ai/providers.select_provider`` stays a pure env
reader — the bridge from persistence to env happens here and at startup
(``main._hydrate_ai_settings_into_env``).

Route skeleton copied from ``routes/onboarding.py``; the provider
payload mirrors ``routes/system.py::_provider_payload``. Auth is
automatic — the local-API-token middleware (``main.py``) gates every
``/api/*`` path.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

import db
from ai.afm_client import reset_default_afm_client
from ai.providers import probe_all_providers, reset_default_provider
from services.app_state import get_setting, set_setting
from services.secret_store import delete_secret, get_secret, store_secret


router = APIRouter()

# Secret-store name for the Claude API key. Service id on macOS Keychain.
ANTHROPIC_KEY_SECRET_NAME = "carrel.ai.anthropic-key"
# app_settings key for the persisted provider choice.
PROVIDER_SETTING_KEY = "ai.provider"
# Allowed provider values. Mirrors select_provider's accepted set plus
# the "auto" default; "off" is the explicit privacy-lockdown choice.
ALLOWED_PROVIDERS = frozenset({"claude", "ollama", "afm", "auto", "off"})


class AiSettingsUpdate(BaseModel):
    """POST body for /api/settings/ai. Both fields optional — a request
    may set just the provider, just the key, or both."""

    provider: Optional[str] = Field(default=None, max_length=32)
    # Capped well above any real Anthropic key length. The value is
    # trimmed and never logged or echoed back to the client.
    anthropic_key: Optional[str] = Field(default=None, max_length=512)


def validate_anthropic_key(key: str) -> tuple[bool, str]:
    """Best-effort liveness check for a Claude API key.

    Calls ``client.models.list()`` — the cheapest authenticated Anthropic
    endpoint (consumes no tokens). Returns ``(valid, detail)``:

    * ``(True, ...)``  — the key authenticated.
    * ``(False, ...)`` — the API rejected the key (auth/permission error).

    A connection failure (offline) raises ``ConnectionError`` so the
    caller can record "not checked" rather than "invalid". This is a
    *best-effort* check: a failure here must never block the save.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - anthropic is a dep
        raise ConnectionError("anthropic SDK unavailable") from exc

    client = anthropic.Anthropic(api_key=key, timeout=10.0, max_retries=0)
    try:
        client.models.list(limit=1)
        return True, "Claude API key authenticated."
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        return False, "Claude API key was rejected by Anthropic."
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
        raise ConnectionError(str(exc)) from exc
    except anthropic.APIStatusError as exc:
        # Any other HTTP status: treat 401/403 as invalid, everything
        # else (5xx, rate limit) as "could not check" rather than "bad".
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return False, "Claude API key was rejected by Anthropic."
        raise ConnectionError(f"Anthropic returned status {status}") from exc


def _ai_settings_payload(*, key_valid: bool | None = None) -> Dict[str, Any]:
    """Build the GET/POST response: persisted provider + key_set flag +
    serialized per-provider availability. Never includes the key value.

    ``key_valid`` is None for plain GET and for POSTs that did not touch
    the key; True/False/None on a key-setting POST per validate result.
    """
    with db.get_db() as conn:
        provider = get_setting(conn, PROVIDER_SETTING_KEY, "auto") or "auto"

    key_set = bool((get_secret(ANTHROPIC_KEY_SECRET_NAME) or "").strip())

    # probe_all_providers() returns {kind: ProviderAvailability dataclass}.
    # asdict() serializes each frozen dataclass to a plain dict for JSON.
    availability = {kind: asdict(verdict) for kind, verdict in probe_all_providers().items()}

    return {
        "provider": provider,
        "key_set": key_set,
        "key_valid": key_valid,
        "availability": availability,
    }


@router.get("/api/settings/ai")
def get_ai_settings() -> Dict[str, Any]:
    """Current AI provider choice, whether a Claude key is stored, and
    live per-provider availability. The key value is never returned —
    only the ``key_set`` boolean."""
    return _ai_settings_payload()


@router.post("/api/settings/ai")
def update_ai_settings(body: AiSettingsUpdate) -> Dict[str, Any]:
    """Persist a provider choice and/or Claude API key, then hot-swap.

    No backend restart: after persisting, ``os.environ`` is mutated and
    the cached provider singletons are dropped so the next request
    re-selects. Returns the same shape as GET.
    """
    key_valid: bool | None = None

    if body.provider is not None:
        provider = body.provider.strip().lower()
        if provider not in ALLOWED_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=("provider must be one of: " + ", ".join(sorted(ALLOWED_PROVIDERS))),
            )
        with db.get_db() as conn:
            set_setting(conn, PROVIDER_SETTING_KEY, provider)
        os.environ["CARREL_AI_PROVIDER"] = provider

    if body.anthropic_key is not None:
        key = body.anthropic_key.strip()
        if key:
            store_secret(ANTHROPIC_KEY_SECRET_NAME, key)
            os.environ["ANTHROPIC_API_KEY"] = key
            # Best-effort validation. A failure must NOT block the save —
            # an offline user still gets their key persisted; key_valid
            # stays None ("not checked") in that case.
            try:
                key_valid, _ = validate_anthropic_key(key)
            except ConnectionError:
                key_valid = None
        else:
            # Empty string is the explicit "clear my key" path.
            delete_secret(ANTHROPIC_KEY_SECRET_NAME)
            os.environ.pop("ANTHROPIC_API_KEY", None)

    # Hot-swap: drop both cached singletons so the next request
    # re-selects against the freshly-mutated env. No restart needed.
    reset_default_provider()
    reset_default_afm_client()

    return _ai_settings_payload(key_valid=key_valid)


def register_settings_routes(app: FastAPI) -> None:
    app.include_router(router)
