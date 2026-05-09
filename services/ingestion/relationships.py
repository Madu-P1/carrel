from __future__ import annotations

import sqlite3
import uuid
from typing import Dict, List, Optional, Tuple

from .text_utils import _valid_learning_sentence, split_sentences, tokenize


def infer_relationship(a_name: str, b_name: str, text: str) -> Optional[str]:
    sentences = split_sentences(text)
    a_tokens = set(tokenize(a_name))
    b_tokens = set(tokenize(b_name))
    for sentence in sentences:
        if not _valid_learning_sentence(sentence):
            continue
        sentence_tokens = set(tokenize(sentence))
        if a_tokens & sentence_tokens and b_tokens & sentence_tokens:
            lowered = sentence.lower()
            if "compare" in lowered or "contrast" in lowered or "different" in lowered:
                return "contrasts with"
            if (
                "because" in lowered
                or "therefore" in lowered
                or "allows" in lowered
                or "uses" in lowered
            ):
                return "supports"
            if "part of" in lowered or "includes" in lowered:
                return "includes"
    return None


def _extract_concept_depth(
    conn: sqlite3.Connection,
    concept_id: str,
    concept_name: str,
    text: str,
    chunk_ids: List[str],
) -> None:
    sentences = split_sentences(text)
    name_tokens = set(tokenize(concept_name))
    relevant = [sentence for sentence in sentences if name_tokens & set(tokenize(sentence))][:8]

    claim_count = 0
    for sentence in relevant[:4]:
        lowered = sentence.lower()
        if any(
            kw in lowered
            for kw in (" is ", " are ", " causes ", " converts ", " produces ", " uses ")
        ):
            conn.execute(
                "INSERT INTO claims (id, concept_id, source_chunk_id, claim_text, claim_type, confidence) VALUES (?, ?, ?, ?, 'fact', 0.6)",
                (
                    str(uuid.uuid4()),
                    concept_id,
                    chunk_ids[0] if chunk_ids else None,
                    sentence[:500],
                ),
            )
            claim_count += 1
            if claim_count >= 2:
                break

    example_count = 0
    for sentence in relevant:
        lowered = sentence.lower()
        if any(kw in lowered for kw in ("example", "for instance", "such as", "e.g.", "illustrat")):
            conn.execute(
                "INSERT INTO concept_examples (id, concept_id, source_chunk_id, example_text, example_type, confidence) VALUES (?, ?, ?, ?, 'worked_example', 0.5)",
                (
                    str(uuid.uuid4()),
                    concept_id,
                    chunk_ids[0] if chunk_ids else None,
                    sentence[:500],
                ),
            )
            example_count += 1
            if example_count >= 2:
                break

    misc_count = 0
    for sentence in relevant:
        lowered = sentence.lower()
        if any(
            kw in lowered
            for kw in (
                "not the same",
                "common mistake",
                "misconception",
                "often confused",
                "do not confuse",
                "incorrectly",
            )
        ):
            conn.execute(
                "INSERT INTO misconceptions (id, concept_id, source_chunk_id, label, description, repair_strategy, confidence) VALUES (?, ?, ?, ?, ?, ?, 0.5)",
                (
                    str(uuid.uuid4()),
                    concept_id,
                    chunk_ids[0] if chunk_ids else None,
                    f"Potential misconception about {concept_name}",
                    sentence[:500],
                    f"Review the source material that discusses {concept_name} to clarify this point.",
                ),
            )
            misc_count += 1
            if misc_count >= 1:
                break

    conn.execute(
        "UPDATE concepts SET misconception_count = ?, open_question_count = ? WHERE id = ?",
        (misc_count, 0, concept_id),
    )


def rank_supporting_chunk_ids(
    concept_name: str,
    concept_summary: str,
    chunk_rows: List[Dict[str, object]],
    limit: int = 3,
) -> List[str]:
    query = f"{concept_name} {concept_summary}".strip()
    query_tokens = set(tokenize(query))
    ranked: List[Tuple[float, str]] = []
    for chunk in chunk_rows:
        content = str(chunk.get("content") or "")
        content_tokens = set(tokenize(content))
        overlap = len(query_tokens & content_tokens)
        if not overlap:
            continue
        score = overlap * 4
        if concept_name.lower() in content.lower():
            score += 3
        if concept_summary and concept_summary.lower() in content.lower():
            score += 3
        ranked.append((score, str(chunk["id"])))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [chunk_id for _score, chunk_id in ranked[:limit]]
