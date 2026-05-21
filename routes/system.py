"""System-level status endpoints.

Small by design: these answer "is the app alive and what's powering it?"
Consumed by the sidebar footer and by any future status page / menu bar
indicator. Does not touch document or SRS state — that lives under
/api/workspace and /api/srs respectively.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict

from fastapi import APIRouter

import db
from ai.providers import get_default_provider

router = APIRouter()


def _provider_payload() -> Dict[str, Any]:
    provider = get_default_provider()
    # All four provider classes (ClaudeRouter, OllamaClient, AFMClient,
    # NullProvider) now carry a `.kind` attribute, so this is the primary
    # path. The class-name inference is kept only as defence in case a
    # future provider lands without the attribute.
    kind = getattr(provider, "kind", None)
    if kind is None:
        cls = provider.__class__.__name__.lower()
        if "claude" in cls:
            kind = "claude"
        elif "ollama" in cls:
            kind = "ollama"
        elif "afm" in cls:
            kind = "afm"
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
        # Prefer CARREL_AI_PROVIDER post-rename; fall back to legacy
        # EINSTEIN_AI_PROVIDER so existing .env files keep working. Mirrors
        # the resolution order in `ai/providers.py::select_provider`.
        "preference": (
            os.getenv("CARREL_AI_PROVIDER") or os.getenv("EINSTEIN_AI_PROVIDER", "auto") or "auto"
        )
        .strip()
        .lower(),
    }


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
    return _provider_payload()


@router.get("/api/shell/status")
def shell_status() -> Dict[str, Any]:
    today = date.today().isoformat()
    with db.get_db() as conn:
        docs = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM documents
            WHERE COALESCE(status, '') != 'deleted'
            """
        ).fetchone()
        due = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM srs_cards
            WHERE due_date IS NULL OR due_date <= ?
            """,
            (today,),
        ).fetchone()
    return {
        "due_count": int(due["count"] if due else 0),
        "doc_count": int(docs["count"] if docs else 0),
        "provider": _provider_payload(),
    }


def register_system_routes(app) -> None:
    app.include_router(router)
