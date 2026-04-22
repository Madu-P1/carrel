"""System-level status endpoints.

Small by design: these answer "is the app alive and what's powering it?"
Consumed by the sidebar footer and by any future status page / menu bar
indicator. Does not touch document or SRS state — that lives under
/api/workspace and /api/srs respectively.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter

from ai.providers import get_default_provider

router = APIRouter()


@router.get("/api/system/provider")
def provider_status() -> Dict[str, Any]:
    """Which AI backend is active, and what model will balanced-tier
    requests hit?

    The sidebar renders this as a trust signal — local (Ollama) vs cloud
    (Claude) vs disabled (NullProvider) — so the user always knows what's
    synthesising their answers. Never cached; cheap to compute. Does NOT
    make a network call to verify reachability; `ai_enabled()` is a config
    check, not a ping. A real call surfacing ok=False is still the canonical
    "reachable or not" signal.
    """
    provider = get_default_provider()
    kind = getattr(provider, "kind", None)
    if kind is None:
        # ClaudeRouter / OllamaClient don't carry a `kind` attribute; infer
        # from class name so the UI sees a stable lowercase token.
        cls = provider.__class__.__name__.lower()
        if "claude" in cls:
            kind = "claude"
        elif "ollama" in cls:
            kind = "ollama"
        elif "null" in cls:
            kind = "null"
        else:
            kind = "unknown"

    model_balanced = ""
    try:
        model_balanced = provider.model_for_task("balanced")
    except Exception:  # defensive — never let the sidebar poll crash
        model_balanced = ""

    return {
        "kind": kind,
        "ai_enabled": bool(provider.ai_enabled()),
        "model_balanced": model_balanced,
        # Env echo so the UI can show "auto (preferred claude)" type text.
        # Trimmed and lowercased for stable comparison on the client.
        "preference": (os.getenv("EINSTEIN_AI_PROVIDER", "auto") or "auto").strip().lower(),
    }


def register_system_routes(app) -> None:
    app.include_router(router)
