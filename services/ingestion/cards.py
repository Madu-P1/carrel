from __future__ import annotations

from typing import Dict, List

from .answers import _clean_answer_text, _definition_front, _is_valid_answer_text
from .topics import build_concept_payloads_from_chunks


def build_card_records(concept: Dict[str, object], concepts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    del concepts
    summary = _clean_answer_text(str(concept.get("summary") or concept.get("description") or ""))
    description = _clean_answer_text(str(concept.get("description") or summary))
    if not _is_valid_answer_text(summary, str(concept.get("name") or "")):
        summary = description
    if not _is_valid_answer_text(summary, str(concept.get("name") or "")):
        return []

    cards = [
        {
            "card_type": "definition",
            "front": _definition_front(str(concept["name"])),
            "back": summary,
            "difficulty": 0.42,
        }
    ]

    comparison_target = concept.get("comparison_target")
    comparison_evidence = _clean_answer_text(str(concept.get("comparison_evidence") or ""))
    if comparison_target and _is_valid_answer_text(comparison_evidence, str(concept.get("name") or "")):
        cards.append(
            {
                "card_type": "comparison",
                "front": f"How does {concept['name']} differ from {comparison_target}?",
                "back": comparison_evidence,
                "difficulty": 0.56,
            }
        )
        return cards

    if description and description != summary and _is_valid_answer_text(description, str(concept.get("name") or "")):
        cards.append(
            {
                "card_type": "application",
                "front": f"Why does {concept['name']} matter?",
                "back": description,
                "difficulty": 0.52,
            }
        )
    return cards


def build_flashcard_deck(chunk_rows: List[Dict[str, object]], title: str, count: int = 8) -> List[Dict[str, object]]:
    concepts = build_concept_payloads_from_chunks(chunk_rows, title, limit=max(count * 2, 8))
    cards: List[Dict[str, object]] = []
    seen_pairs = set()
    seen_fronts = set()
    seen_answers = set()

    for concept in concepts:
        answer = _clean_answer_text(str(concept.get("summary") or concept.get("description") or ""))
        if not _is_valid_answer_text(answer, str(concept.get("name") or "")):
            continue
        front = _definition_front(str(concept.get("name") or "this concept"))
        pair_key = (front.lower(), answer.lower())
        if pair_key in seen_pairs or front.lower() in seen_fronts or answer.lower() in seen_answers:
            continue
        seen_pairs.add(pair_key)
        seen_fronts.add(front.lower())
        seen_answers.add(answer.lower())
        cards.append(
            {
                "q": front,
                "a": answer,
                "type": "definition",
                "confidence": 0.78,
                "topic": concept.get("topic"),
                "supporting_chunk_ids": concept.get("supporting_chunk_ids") or [],
                "grounding_mode": "internal_only",
                "show_citations": False,
            }
        )
        if len(cards) >= max(1, min(count, 16)):
            break
    return cards
