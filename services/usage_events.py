from __future__ import annotations

import json
import math
import re
import sqlite3
from typing import Any, Dict, Iterable, Mapping, Optional


ALLOWED_EVENT_NAMES = {
    "app.first_launch",
    "onboarding.step",
    "import.started",
    "import.completed",
    "import.failed",
    "first_source_import_started",
    "first_source_ready",
    "first_scoped_question_submitted",
    "first_grounded_answer_rendered",
    "first_citation_verified",
    "activation_completed",
    "onboarding.demo_library_loaded",
    "library.search_used",
    "reader.find_used",
    "reader.focus_toggled",
    "ask.first_question",
    "srs.review_started",
    "srs.review_completed",
    # PR 7 — per-card timing telemetry. Properties:
    #   seconds_to_first_reveal: float, time from card-shown to first
    #     front→back transition. Untouched by subsequent re-flips
    #     (PR 1 made flips bidirectional; without this carve-out the
    #     metric inflates as users review the question again).
    #   seconds_to_rate: float, time from first reveal to rating.
    #   rating: again|hard|good|easy.
    # Used to decide whether PRs 5/6 (citation, cloze) ship in week 3.
    "srs.card_rated",
    # PR 6.3 — emitted when the user defers a card to the end of the
    # session queue (different from "Again", which records an SRS
    # rating). Properties:
    #   card_id: string, the SRS card id.
    #   remaining: int, cards remaining in the session after the
    #     defer (excluding the just-deferred card).
    "srs.card_deferred",
    # PR 0a — emitted once per install when auto-card-creation on
    # upload has been disabled, so the dashboard can confirm the
    # migration flipped.
    "cards.auto_generation_disabled",
}

EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")
SURFACE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PROPERTY_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DENIED_KEY_FRAGMENTS = {
    "answer",
    "api_key",
    "content",
    "document_text",
    "email",
    "filename",
    "file_name",
    "name",
    "path",
    "question",
    "query",
    "quote",
    "secret",
    "selected",
    "snippet",
    "text",
    "token",
    "user",
}
MAX_PROPERTIES_BYTES = 4000
MAX_STRING_VALUE_LENGTH = 120


def _is_denied_key(key: str) -> bool:
    normalized = key.lower()
    return any(fragment in normalized for fragment in DENIED_KEY_FRAGMENTS)


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) > MAX_STRING_VALUE_LENGTH:
            return None
        return stripped
    return None


def sanitize_properties(properties: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not properties:
        return {}

    safe: Dict[str, Any] = {}
    for raw_key, raw_value in properties.items():
        key = str(raw_key).strip()
        if not PROPERTY_KEY_RE.match(key) or _is_denied_key(key):
            continue
        value = _json_safe_value(raw_value)
        if value is None and raw_value is not None:
            continue
        safe[key] = value
    return safe


def _properties_json(properties: Mapping[str, Any]) -> str:
    encoded = json.dumps(properties, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= MAX_PROPERTIES_BYTES:
        return encoded
    return "{}"


def validate_event_name(event_name: str) -> str:
    normalized = event_name.strip()
    if not EVENT_NAME_RE.match(normalized):
        raise ValueError("Event name must use dotted lowercase segments.")
    if normalized not in ALLOWED_EVENT_NAMES:
        raise ValueError(f"Unsupported usage event: {normalized}")
    return normalized


def validate_surface(surface: Optional[str]) -> Optional[str]:
    if surface is None:
        return None
    normalized = surface.strip().lower()
    if not normalized:
        return None
    if not SURFACE_RE.match(normalized):
        raise ValueError("Surface must be a short lowercase identifier.")
    return normalized


def _row_to_event(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        properties = json.loads(row["properties"] or "{}")
    except json.JSONDecodeError:
        properties = {}
    return {
        "id": row["id"],
        "event_name": row["event_name"],
        "surface": row["surface"],
        "properties": properties if isinstance(properties, dict) else {},
        "created_at": row["created_at"],
    }


def record_event(
    conn: sqlite3.Connection,
    *,
    event_name: str,
    properties: Optional[Mapping[str, Any]] = None,
    surface: Optional[str] = None,
) -> Dict[str, Any]:
    safe_name = validate_event_name(event_name)
    safe_surface = validate_surface(surface)
    safe_properties = sanitize_properties(properties)
    cursor = conn.execute(
        """
        INSERT INTO usage_events (event_name, surface, properties)
        VALUES (?, ?, ?)
        """,
        (safe_name, safe_surface, _properties_json(safe_properties)),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT id, event_name, surface, properties, created_at
        FROM usage_events
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return _row_to_event(row)


def list_recent_events(conn: sqlite3.Connection, *, limit: int = 100) -> Iterable[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, event_name, surface, properties, created_at
        FROM usage_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, min(200, int(limit))),),
    ).fetchall()
    return [_row_to_event(row) for row in rows]
