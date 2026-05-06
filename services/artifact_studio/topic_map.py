"""Topic-map analysis — score concepts, pick focus, build topic groups.

Pure analysis, no DB I/O. Pure-function design makes this the easiest
submodule to test in isolation.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.helpers import split_sentences
from services.ingestion import clean_learning_text


# Prefix words that signal a concept name is a fragment, not a standalone
# noun phrase. Used to penalise selector candidates whose first word is
# one of these — e.g. "the user wants ...", "for sample sizes", etc.
NOISY_CONCEPT_PREFIXES = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "help",
    "helps",
    "more",
    "one",
    "reduce",
    "reduces",
    "same",
    "the",
    "this",
    "those",
    "using",
    "used",
}


def _clean_section_label(value: Optional[str]) -> Optional[str]:
    label = str(value or "").strip()
    if not label:
        return None
    lowered = label.lower()
    if lowered.startswith("section ") or lowered.startswith("page ") or lowered.startswith("slide "):
        return None
    if len(label.split()) > 12:
        return None
    return label


def _clean_description(value: str) -> str:
    cleaned = clean_learning_text(str(value or ""))
    words = cleaned.split()
    for size in (3, 2, 1):
        if len(words) >= size * 2:
            first = [word.lower() for word in words[:size]]
            second = [word.lower() for word in words[size : size * 2]]
            if first == second:
                cleaned = " ".join(words[size:])
                break
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    sentences = split_sentences(cleaned)
    if sentences:
        return " ".join(sentences[:2]).strip()
    return cleaned[:220].strip()


def _chunk_lookup(chunks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(chunk["id"]): chunk for chunk in chunks if chunk.get("id")}


def _dominant_topic(concept: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    lookup = _chunk_lookup(chunks)
    labels: List[str] = []
    for chunk_id in concept.get("source_chunk_ids") or []:
        chunk = lookup.get(str(chunk_id))
        if not chunk:
            continue
        label = _clean_section_label(chunk.get("section"))
        if label:
            labels.append(label)
    return labels[0] if labels else "Core Ideas"


def _concept_importance(concept: Dict[str, Any], chunks: List[Dict[str, Any]]) -> float:
    description = _clean_description(str(concept.get("description") or ""))
    chunk_support = len(concept.get("source_chunk_ids") or [])
    score = min(len(description) / 40, 8.0)
    score += chunk_support * 2.0
    score += max(0.0, 1.0 - float(concept.get("mastery") or 0.0)) * 3.0
    if _dominant_topic(concept, chunks) != "Core Ideas":
        score += 1.5
    return score


def _select_focus_concepts(concepts: List[Dict[str, Any]], chunks: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    ordered = sorted(
        concepts,
        key=lambda concept: (-_concept_importance(concept, chunks), str(concept.get("name") or "").lower()),
    )
    selected_by_description: Dict[str, Dict[str, Any]] = {}
    seen_names = set()
    for concept in ordered:
        label = str(concept.get("name") or "").strip().lower()
        if not label or label in seen_names:
            continue
        first_token = label.split()[0]
        if first_token in NOISY_CONCEPT_PREFIXES or " by " in label:
            continue
        seen_names.add(label)
        concept["study_description"] = _clean_description(str(concept.get("description") or concept.get("name") or ""))
        concept["topic"] = _dominant_topic(concept, chunks)
        description_key = (concept.get("study_description") or concept.get("name") or "").lower()
        current = selected_by_description.get(description_key)
        if current is None:
            selected_by_description[description_key] = concept
            continue
        current_score = _concept_importance(current, chunks)
        candidate_score = _concept_importance(concept, chunks)
        current_matches_topic = str(current.get("name") or "").lower() == str(current.get("topic") or "").lower()
        candidate_matches_topic = str(concept.get("name") or "").lower() == str(concept.get("topic") or "").lower()
        if candidate_matches_topic and not current_matches_topic:
            selected_by_description[description_key] = concept
        elif candidate_score > current_score:
            selected_by_description[description_key] = concept
    selected = sorted(
        selected_by_description.values(),
        key=lambda concept: (-_concept_importance(concept, chunks), str(concept.get("name") or "").lower()),
    )
    return selected[:limit]


def _build_topic_map(concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for concept in concepts:
        grouped.setdefault(concept.get("topic") or "Core Ideas", []).append(concept)
    topic_map: List[Dict[str, Any]] = []
    for title, items in grouped.items():
        topic_map.append(
            {
                "title": title,
                "concept_ids": [item["id"] for item in items],
                "concept_names": [item["name"] for item in items],
                "summary": " ".join(item.get("study_description", "") for item in items[:2]).strip(),
            }
        )
    return topic_map

