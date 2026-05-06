"""Concept-label cleanup + selector ranking + curated-options cache.

A "concept" is a noun-phrase the ingestion pipeline extracted from a
document. Raw concept names are noisy: PDFs leak copyright lines,
camelCase / underscore conventions sneak in from textbook headings,
and the same idea ("Mitosis", "MITOSIS", "mitosis-1") gets duplicated
across chunks.

This module owns:
  * `clean_concept_label`: collapse noise, split camelCase, drop boilerplate
  * `build_concept_options`: rank concepts for the document's "what should
    I study next?" picker. Uses the user's `learning_goal` (from
    `app_settings`) as a soft tie-breaker; caches the curated list keyed
    by a content signature so re-reads are deterministic until the
    document or goal changes.
  * `collect_document_concepts`: pull every concept row for a doc and
    enrich each with its display_name + source_chunk_ids list.

Lifted from `services.documents` (the audit's biggest god-object).
The 11 caller sites — every service module that renders a concept
label — keep working unchanged because `services.documents` re-exports
the public names.

The internal helpers (`_selector_score`, `_selector_reason`, etc.)
are kept module-private but exposed under their old names from
`services.documents` for the few internal callers in `fetch_document_detail`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Dict, List


SELECTOR_CACHE_PREFIX = "concept_selector:"
SELECTOR_LIMIT = 8
SELECTOR_NOISE_PATTERNS = [
    r"all rights reserved",
    r"all right reserved",
    r"copyright",
    r"pearson education",
    r"\bltd\b",
    r"\breserved\b",
]


# --- app_settings I/O (private to this module + label cache) ---------------


def _get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row and row["value"] is not None else default


def _set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


def _selector_cache_key(doc_id: str) -> str:
    return f"{SELECTOR_CACHE_PREFIX}{doc_id}"


def _load_messages(raw: Any) -> Any:
    """Local copy of `services.documents.load_messages` so this module
    is self-contained. Returns [] for any non-JSON input."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


# --- Public: label cleanup --------------------------------------------------


def clean_concept_label(value: str) -> str:
    """Render a noisy raw concept name as a human-readable label.

    Pipeline:
      1. Split camelCase ("MitosisPhase" → "Mitosis Phase")
      2. Replace `_`, `/`, `\\`, `-` with spaces
      3. Split letter-digit boundaries ("Q1Lab" → "Q 1 Lab")
      4. Strip noise patterns (copyright, "all rights reserved", etc.)
      5. Collapse whitespace
      6. Dedupe adjacent words (case-insensitive) — "Mitosis Mitosis" → "Mitosis"

    Empty / whitespace inputs always return "Study concept" so the UI
    never has to render a blank label.
    """
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    cleaned = re.sub(r"[_/\\-]+", " ", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    for pattern in SELECTOR_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    deduped_words: List[str] = []
    for word in cleaned.split():
        if not deduped_words or deduped_words[-1].lower() != word.lower():
            deduped_words.append(word)
    cleaned = " ".join(deduped_words)
    return cleaned or "Study concept"


def _concept_name_replacements(
    concepts: List[Dict[str, Any]],
) -> List[tuple[str, str]]:
    pairs: List[tuple[str, str]] = []
    seen = set()
    for concept in concepts:
        raw_name = str(concept.get("name") or "").strip()
        if not raw_name or raw_name in seen:
            continue
        seen.add(raw_name)
        cleaned = clean_concept_label(raw_name)
        if cleaned and cleaned != raw_name:
            pairs.append((raw_name, cleaned))
    return pairs


def _normalize_concept_text(
    text: str, replacements: List[tuple[str, str]]
) -> str:
    """Apply the replacements from `_concept_name_replacements` to a
    free-form text (a question stem, an answer, an explanation) so the
    rendered text uses the cleaned label, not the raw one."""
    value = str(text or "")
    for raw_name, cleaned in replacements:
        value = value.replace(raw_name, cleaned)
    return value


# --- Selector scoring (private to this module) -----------------------------


def _selector_reason(concept: Dict[str, Any], goal: str) -> str:
    reason_parts = []
    if goal:
        goal_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", goal.lower())
            if len(token) > 3
        }
        concept_text = (
            f"{concept.get('name', '')} {concept.get('description', '')}".lower()
        )
        if goal_tokens and any(token in concept_text for token in goal_tokens):
            reason_parts.append("Aligned with the current learning goal")
    if concept.get("description"):
        reason_parts.append("Grounded in the document's extracted explanation")
    if concept.get("source_chunk_ids"):
        reason_parts.append("Backed by source chunks")
    return ". ".join(reason_parts[:2]) or "Selected as a high-signal study concept."


def _selector_score(concept: Dict[str, Any], goal: str) -> float:
    raw_name = str(concept.get("name") or "")
    clean_name = clean_concept_label(raw_name)
    description = str(concept.get("description") or "")
    score = 50.0
    if clean_name != raw_name.strip():
        score += 8
    if 2 <= len(clean_name.split()) <= 6:
        score += 10
    if description:
        score += min(len(description) / 24, 12)
    if concept.get("source_chunk_ids"):
        score += 8
    try:
        score += float(concept.get("mastery") or 0) * 5
    except (TypeError, ValueError):
        pass
    if goal:
        goal_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", goal.lower())
            if len(token) > 3
        }
        concept_text = f"{raw_name} {description}".lower()
        score += sum(6 for token in goal_tokens if token in concept_text)
    if len(clean_name) < 4:
        score -= 25
    if any(
        re.search(pattern, raw_name, flags=re.IGNORECASE)
        for pattern in SELECTOR_NOISE_PATTERNS
    ):
        score -= 20
    return score


def _build_selector_context(
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> str:
    """LLM-prompt-style context block (kept for forward compat with a
    future LLM-driven selector). Currently unused by the fallback
    ranker but referenced by external callers."""
    chunk_lookup = {item["id"]: item.get("content", "") for item in chunk_items}
    blocks = []
    for concept in concepts:
        chunk_preview = ""
        for chunk_id in concept.get("source_chunk_ids", [])[:2]:
            content = chunk_lookup.get(chunk_id, "").strip()
            if content:
                chunk_preview = " ".join(content.split())[:280]
                break
        blocks.append(
            "\n".join(
                [
                    f"Concept id: {concept['id']}",
                    f"Raw name: {concept.get('name', '')}",
                    f"Description: {concept.get('description', '')}",
                    f"Preview: {chunk_preview}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_concept_options(
    concepts: List[Dict[str, Any]],
    goal: str,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        concepts,
        key=lambda item: (
            -_selector_score(item, goal),
            str(item.get("name") or "").lower(),
        ),
    )
    if len(ordered) > SELECTOR_LIMIT:
        ordered = ordered[:SELECTOR_LIMIT]
    curated: List[Dict[str, Any]] = []
    seen_labels = set()
    for concept in ordered:
        label = clean_concept_label(str(concept.get("name") or ""))
        key = label.lower()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        curated.append(
            {
                "concept_id": concept["id"],
                "display_name": label,
                "reason": _selector_reason(concept, goal),
            }
        )
    return curated or [
        {
            "concept_id": concept["id"],
            "display_name": clean_concept_label(
                str(concept.get("name") or "Study concept")
            ),
            "reason": "Fallback selector option.",
        }
        for concept in concepts[:1]
    ]


def _concept_selector_signature(
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    goal: str,
) -> str:
    payload = {
        "doc_id": document_row["id"],
        "filename": document_row["filename"],
        "goal": goal,
        "concepts": [
            {
                "id": item["id"],
                "name": item.get("name"),
                "description": item.get("description"),
                "mastery": item.get("mastery"),
            }
            for item in concepts
        ],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# --- Public: option-builder entry points -----------------------------------


def build_concept_options(
    conn: sqlite3.Connection,
    *,
    document_row: Dict[str, Any],
    concepts: List[Dict[str, Any]],
    chunk_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return up to SELECTOR_LIMIT (8) curated study options for a
    document. Cached in app_settings keyed by a content signature so
    repeated reads return identical lists; the cache invalidates
    automatically when the document, its concepts, or the user's
    learning goal changes."""
    if not concepts:
        return []

    goal = _get_setting(conn, "learning_goal", "")
    signature = _concept_selector_signature(document_row, concepts, goal)
    cache_key = _selector_cache_key(document_row["id"])
    cached = _load_messages(_get_setting(conn, cache_key, ""))
    if (
        isinstance(cached, dict)
        and cached.get("signature") == signature
        and isinstance(cached.get("options"), list)
    ):
        cached_options = cached["options"]
    else:
        cached_options = _fallback_concept_options(concepts, goal)
        _set_setting(
            conn,
            cache_key,
            json.dumps({"signature": signature, "options": cached_options}),
        )

    by_id = {concept["id"]: concept for concept in concepts}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for rank, item in enumerate(cached_options):
        concept = by_id.get(item.get("concept_id"))
        if not concept or concept["id"] in seen:
            continue
        seen.add(concept["id"])
        selected.append(
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": item.get("display_name")
                or clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": item.get("reason")
                or _selector_reason(concept, goal),
                "selector_rank": rank,
            }
        )

    if not selected:
        return [
            {
                **concept,
                "raw_name": concept.get("name"),
                "name": clean_concept_label(str(concept.get("name") or "")),
                "selector_reason": _selector_reason(concept, goal),
                "selector_rank": index,
            }
            for index, concept in enumerate(concepts[:SELECTOR_LIMIT])
        ]
    return selected


def collect_document_concepts(
    conn: sqlite3.Connection, doc_id: str
) -> List[Dict[str, object]]:
    """Load all concepts for a document and enrich each row with the
    cleaned `display_name` plus the parsed `source_chunk_ids` list."""
    if not doc_id:
        return []
    rows = conn.execute(
        """
        SELECT c.id, c.doc_id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name,
               d.subject_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        WHERE c.doc_id = ?
        ORDER BY c.rowid ASC
        """,
        (doc_id,),
    ).fetchall()
    concepts: List[Dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["source_chunk_ids"] = _load_messages(item["source_chunks"])
        item.pop("source_chunks", None)
        item["display_name"] = clean_concept_label(item.get("name"))
        concepts.append(item)
    return concepts
