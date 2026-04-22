"""Artifact Studio — generates durable learning artifacts from source material."""
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services import artifact_prompts
from services import extraction_pipeline
from services.documents import clean_concept_label
from services.helpers import split_sentences, tokenize
from services.ingestion import build_flashcard_deck, clean_learning_text
from services import provenance_service


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
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads"


# ---------------------------------------------------------------------------
# Fallback generators (no Claude required)
# ---------------------------------------------------------------------------

def _chunk_text_for_scope(
    conn: sqlite3.Connection,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        rows = conn.execute(
            f"""
            SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
            FROM concepts c
            JOIN chunks ch ON ch.doc_id = c.doc_id
            JOIN documents d ON d.id = ch.doc_id
            WHERE c.id IN ({placeholders})
            ORDER BY ch.chunk_index ASC
            LIMIT ?
            """,
            (*concept_ids, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"""
            SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
            FROM chunks ch
            JOIN documents d ON d.id = ch.doc_id
            WHERE ch.doc_id IN ({placeholders})
            ORDER BY ch.chunk_index ASC
            LIMIT ?
            """,
            (*source_ids, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    rows = conn.execute(
        """
        SELECT ch.id, ch.content, ch.section, ch.page_num, d.filename, d.id AS doc_id
        FROM chunks ch
        JOIN documents d ON d.id = ch.doc_id
        ORDER BY ch.rowid DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _fresh_chunks_for_sources(conn: sqlite3.Connection, source_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    if not source_ids:
        return []
    placeholders = ",".join("?" * len(source_ids))
    rows = conn.execute(
        f"""
        SELECT id, filename, storage_name
        FROM documents
        WHERE id IN ({placeholders})
        ORDER BY rowid ASC
        """,
        source_ids,
    ).fetchall()
    fresh_chunks: List[Dict[str, Any]] = []
    for row in rows:
        storage_name = str(row["storage_name"] or "").strip()
        if not storage_name:
            continue
        candidate_path = UPLOAD_DIR / storage_name
        if not candidate_path.exists():
            continue
        try:
            asset = extraction_pipeline.extract_asset(candidate_path)
        except Exception:
            continue
        fresh_chunks.extend(
            {
                "id": f"{row['id']}::{index}",
                "content": chunk.content,
                "section": chunk.section,
                "page_num": chunk.page_num,
                "filename": row["filename"],
                "doc_id": row["id"],
                "chunk_index": chunk.chunk_index,
            }
            for index, chunk in enumerate(asset.chunks, start=1)
            if str(chunk.content or "").strip()
        )
    return fresh_chunks


def _concepts_for_scope(
    conn: sqlite3.Connection,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if concept_ids:
        placeholders = ",".join("?" * len(concept_ids))
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.id IN ({placeholders})
            LIMIT ?
            """,
            (*concept_ids, limit),
        ).fetchall()
        concepts = [dict(r) for r in rows]
        for concept in concepts:
            concept["raw_name"] = concept["name"]
            concept["name"] = clean_concept_label(concept["name"])
            try:
                concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
            except Exception:
                concept["source_chunk_ids"] = []
        return concepts
    if source_ids:
        placeholders = ",".join("?" * len(source_ids))
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
            FROM concepts c
            JOIN documents d ON d.id = c.doc_id
            WHERE c.doc_id IN ({placeholders})
            ORDER BY c.mastery ASC
            LIMIT ?
            """,
            (*source_ids, limit),
        ).fetchall()
        concepts = [dict(r) for r in rows]
        for concept in concepts:
            concept["raw_name"] = concept["name"]
            concept["name"] = clean_concept_label(concept["name"])
            try:
                concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
            except Exception:
                concept["source_chunk_ids"] = []
        return concepts
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.description, c.mastery, c.source_chunks, d.filename AS document_name
        FROM concepts c
        JOIN documents d ON d.id = c.doc_id
        ORDER BY c.mastery ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    concepts = [dict(r) for r in rows]
    for concept in concepts:
        concept["raw_name"] = concept["name"]
        concept["name"] = clean_concept_label(concept["name"])
        try:
            concept["source_chunk_ids"] = json.loads(concept.get("source_chunks") or "[]")
        except Exception:
            concept["source_chunk_ids"] = []
    return concepts


def _support_snippet(concept: Dict[str, Any], chunks: List[Dict[str, Any]]) -> str:
    name_tokens = set(tokenize(str(concept.get("name") or "")))
    best_sentence = ""
    best_score = 0
    for chunk in chunks:
        for sentence in split_sentences(chunk.get("content") or "")[:3]:
            score = len(name_tokens & set(tokenize(sentence)))
            if concept.get("name", "").lower() in sentence.lower():
                score += 2
            if score > best_score:
                best_score = score
                best_sentence = sentence
    return best_sentence


def retrieve_grounding_chunks(
    conn: sqlite3.Connection,
    *,
    source_ids: Optional[List[str]],
    concept_ids: Optional[List[str]],
    query: str,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    candidate_limit = max(limit * 4, 24)
    candidates = _chunk_text_for_scope(conn, source_ids, concept_ids, limit=candidate_limit)
    if not candidates:
        return []

    query_tokens = set(tokenize(query or ""))
    if not query_tokens:
        return candidates[:limit]

    ranked: List[Dict[str, Any]] = []
    for chunk in candidates:
        content = str(chunk.get("content") or "")
        if not content:
            continue
        content_tokens = tokenize(content)
        overlap = sum(1 for token in content_tokens if token in query_tokens)
        if overlap <= 0:
            continue
        section = str(chunk.get("section") or "")
        filename = str(chunk.get("filename") or "")
        score = overlap * 5
        score += sum(3 for token in query_tokens if token in section.lower())
        score += sum(2 for token in query_tokens if token in filename.lower())
        if chunk.get("page_num") is not None:
            score += 0.5
        ranked.append({**chunk, "_score": score})

    ordered = sorted(
        ranked or [{**chunk, "_score": 0} for chunk in candidates],
        key=lambda item: (-float(item.get("_score", 0)), item.get("filename", ""), item.get("chunk_index", 0)),
    )
    return [{key: value for key, value in chunk.items() if key != "_score"} for chunk in ordered[:limit]]


def render_grounding_text(chunks: List[Dict[str, Any]]) -> str:
    blocks = []
    for chunk in chunks:
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        label = " · ".join(
            piece
            for piece in [
                str(chunk.get("filename") or "").strip(),
                str(chunk.get("section") or "").strip(),
                f"p.{chunk['page_num']}" if chunk.get("page_num") is not None else "",
            ]
            if piece
        )
        blocks.append(f"[{label or 'Source'}]\n{content}")
    return "\n\n".join(blocks)


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


def _flashcard_items(concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for index, concept in enumerate(concepts):
        summary = concept.get("study_description") or concept.get("name") or ""
        items.append(
            {
                "kind": "definition",
                "front": f"What is {concept['name']}?",
                "back": summary,
                "topic": concept.get("topic"),
                "confidence": round(min(0.95, 0.62 + (_concept_importance(concept, []) / 15)), 2),
                "supporting_chunk_ids": concept.get("source_chunk_ids") or [],
            }
        )
        other = next(
            (
                candidate
                for candidate in concepts[index + 1 :]
                if candidate["name"].lower() not in concept["name"].lower()
                and concept["name"].lower() not in candidate["name"].lower()
                and (candidate.get("study_description") or "") != summary
            ),
            None,
        )
        if other:
            items.append(
                {
                    "kind": "distinction",
                    "front": f"How does {concept['name']} differ from {other['name']}?",
                    "back": f"{concept['name']}: {summary} In contrast, {other['name']}: {other.get('study_description') or other.get('name')}.",
                    "topic": concept.get("topic"),
                    "confidence": 0.7,
                    "supporting_chunk_ids": list(dict.fromkeys((concept.get("source_chunk_ids") or []) + (other.get("source_chunk_ids") or []))),
                }
            )
        else:
            items.append(
                {
                    "kind": "application",
                    "front": f"Why is {concept['name']} important?",
                    "back": summary,
                    "topic": concept.get("topic"),
                    "confidence": 0.68,
                    "supporting_chunk_ids": concept.get("source_chunk_ids") or [],
                }
            )
    return items


def _quiz_items(concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for concept in concepts:
        correct = concept.get("study_description") or concept.get("name") or ""
        same_topic = [
            other for other in concepts
            if other["id"] != concept["id"] and other.get("topic") == concept.get("topic")
        ]
        pool = same_topic or [other for other in concepts if other["id"] != concept["id"]]
        distractors = [other.get("study_description") or other.get("name") for other in pool if (other.get("study_description") or other.get("name")) and (other.get("study_description") or other.get("name")) != correct][:3]
        if len(distractors) < 2:
            continue
        items.append(
            {
                "kind": "mcq",
                "question": f"Which statement best explains {concept['name']}?",
                "answer": correct,
                "choices": [correct, *distractors][:4],
                "topic": concept.get("topic"),
                "confidence": 0.72,
                "supporting_chunk_ids": concept.get("source_chunk_ids") or [],
            }
        )
    return items


def _mock_exam_items(topic_map: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for topic in topic_map[:5]:
        if not topic.get("concept_names"):
            continue
        names = topic["concept_names"][:3]
        items.append(
            {
                "kind": "essay",
                "prompt": f"Explain the key ideas in {topic['title']} and show how {', '.join(names)} relate to each other.",
                "topic": topic["title"],
                "confidence": 0.74,
                "supporting_chunk_ids": [],
            }
        )
    return items


# ---------------------------------------------------------------------------
# Per-kind fallback generators
# ---------------------------------------------------------------------------

def _generate_study_guide(concepts: List[Dict], chunks: List[Dict], depth: str, topic_map: Optional[List[Dict[str, Any]]] = None) -> str:
    lines = ["# Study Guide\n"]
    for topic in topic_map or [{"title": "Core Ideas", "concept_names": [concept["name"] for concept in concepts[:8]]}]:
        lines.append(f"## {topic['title']}")
        matching = [concept for concept in concepts if concept["name"] in set(topic.get("concept_names") or [])]
        for concept in matching[:4]:
            lines.append(f"- **{concept['name']}**: {concept.get('study_description') or concept.get('description') or ''}")
        lines.append("")
    if depth in ("standard", "rigorous") and chunks:
        lines.append("## Key Takeaways")
        for chunk in chunks[:4]:
            sentences = split_sentences(chunk["content"])
            takeaway = " ".join(sentences[:2]).strip()
            if takeaway:
                lines.append(f"- {takeaway}")
    return "\n".join(lines)


def _generate_briefing(concepts: List[Dict], chunks: List[Dict], topic_map: Optional[List[Dict[str, Any]]] = None) -> str:
    lines = ["# Briefing\n", "## What You Need to Know\n"]
    for idx, concept in enumerate(concepts[:5], 1):
        lines.append(f"{idx}. **{concept['name']}** — {concept.get('study_description') or concept.get('description', '')}")
    if topic_map:
        lines.append("\n## Major Topics\n")
        for topic in topic_map[:4]:
            lines.append(f"- **{topic['title']}**: {topic.get('summary') or ', '.join(topic.get('concept_names', [])[:3])}")
    return "\n".join(lines)


def _generate_faq(concepts: List[Dict], chunks: List[Dict]) -> str:
    lines = ["# FAQ\n"]
    for concept in concepts[:6]:
        name = concept["name"]
        desc = concept.get("study_description") or concept.get("description") or f"{name} is part of the uploaded material."
        lines.append(f"**Q: What is {name}?**")
        lines.append(f"A: {desc}\n")
        lines.append(f"**Q: Why does {name} matter?**")
        lines.append(f"A: {desc}\n")
    return "\n".join(lines)


def _generate_flashcard_set(concepts: List[Dict], chunks: List[Dict], deck_items: Optional[List[Dict[str, Any]]] = None) -> str:
    cards = []
    for item in (deck_items or _flashcard_items(concepts))[:12]:
        front = item.get("front") or item.get("q") or ""
        back = item.get("back") or item.get("a") or ""
        if front and back:
            cards.append(f"FRONT: {front}\nBACK: {back}")
    return "\n\n---\n\n".join(cards)


def _generate_quiz(concepts: List[Dict], chunks: List[Dict]) -> str:
    lines = ["# Quiz\n"]
    for idx, item in enumerate(_quiz_items(concepts)[:6], 1):
        lines.append(f"**Q{idx}: {item['question']}**")
        for option_label, distractor in zip(("A", "B", "C", "D"), item["choices"]):
            lines.append(f"{option_label}) {distractor}")
        lines.append("")
        lines.append(f"_Answer: A_\n")
    return "\n".join(lines)


def _generate_outline(concepts: List[Dict], chunks: List[Dict]) -> str:
    lines = ["# Outline\n"]
    for idx, concept in enumerate(concepts[:8], 1):
        lines.append(f"{idx}. {concept['name']}")
        desc = concept.get("description") or ""
        if desc:
            lines.append(f"   - {desc[:120]}")
    return "\n".join(lines)


def _generate_summary(concepts: List[Dict], chunks: List[Dict]) -> str:
    lines = ["# Summary\n"]
    if chunks:
        sentences = []
        for chunk in chunks[:4]:
            sentences.extend(split_sentences(chunk["content"])[:2])
        lines.append(" ".join(sentences[:6]))
        lines.append("")
    lines.append("## Core Concepts")
    for concept in concepts[:6]:
        lines.append(f"- **{concept['name']}**: {(concept.get('study_description') or concept.get('description', ''))[:140]}")
    return "\n".join(lines)


def _generate_report(concepts: List[Dict], chunks: List[Dict], goal: str) -> str:
    goal_text = f"Goal: {goal}\n\n" if goal else ""
    lines = [f"# Learning Report\n\n{goal_text}"]
    lines.append("## Executive Summary\n")
    concept_names = ", ".join(c["name"] for c in concepts[:5])
    lines.append(f"This report covers: {concept_names}.\n")
    lines.append("## Concept Inventory\n")
    for concept in concepts[:8]:
        mastery = round(float(concept.get("mastery", 0.1) or 0.1) * 100)
        band = "Struggling" if mastery < 45 else "Developing" if mastery < 75 else "Strong"
        lines.append(f"**{concept['name']}** ({band}, {mastery}%)")
        lines.append(concept.get("study_description", "") or concept.get("description", ""))
        lines.append("")
    return "\n".join(lines)


def _generate_mock_exam(topic_map: List[Dict[str, Any]]) -> str:
    lines = ["# Mock Exam\n"]
    for index, item in enumerate(_mock_exam_items(topic_map), start=1):
        lines.append(f"**Question {index}.** {item['prompt']}")
        lines.append("")
    return "\n".join(lines)


_KIND_TO_GENERATOR = {
    "study_guide": lambda c, ch, **kw: _generate_study_guide(c, ch, kw.get("depth", "standard"), kw.get("topic_map")),
    "briefing": lambda c, ch, **kw: _generate_briefing(c, ch, kw.get("topic_map")),
    "faq": lambda c, ch, **kw: _generate_faq(c, ch),
    "flashcards": lambda c, ch, **kw: _generate_flashcard_set(c, ch, kw.get("deck_items")),
    "quiz": lambda c, ch, **kw: _generate_quiz(c, ch),
    "mock_exam": lambda c, ch, **kw: _generate_mock_exam(kw.get("topic_map") or []),
    "outline": lambda c, ch, **kw: _generate_outline(c, ch),
    "summary": lambda c, ch, **kw: _generate_summary(c, ch),
    "report": lambda c, ch, **kw: _generate_report(c, ch, kw.get("goal", "")),
    "concept_map": lambda c, ch, **kw: _generate_outline(c, ch),
}


def _hidden_artifact_payload(
    artifact_kind: str,
    concepts: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    topic_map: List[Dict[str, Any]],
    *,
    custom_prompt: Optional[str],
    deck_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if artifact_kind == "flashcards":
        raw_items = deck_items or _flashcard_items(concepts)[:12]
        items = [
            {
                "kind": item.get("type") or item.get("kind") or "definition",
                "front": item.get("q") or item.get("front"),
                "back": item.get("a") or item.get("back"),
                "topic": item.get("topic"),
                "confidence": item.get("confidence", 0.7),
                "supporting_chunk_ids": item.get("supporting_chunk_ids") or [],
            }
            for item in raw_items[:12]
        ]
    elif artifact_kind == "quiz":
        items = _quiz_items(concepts)[:8]
    elif artifact_kind == "mock_exam":
        items = _mock_exam_items(topic_map)[:6]
    else:
        items = [
            {
                "kind": "concept",
                "title": concept["name"],
                "content": concept.get("study_description") or concept.get("description"),
                "topic": concept.get("topic"),
                "confidence": 0.7,
                "supporting_chunk_ids": concept.get("source_chunk_ids") or [],
            }
            for concept in concepts[:10]
        ]
    return {
        "grounding_mode": "internal_only",
        "show_citations": False,
        "artifact_kind": artifact_kind,
        "custom_prompt": custom_prompt,
        "topic_map": topic_map,
        "items": items,
        "supporting_chunks": [
            {
                "chunk_id": chunk.get("id"),
                "section": chunk.get("section"),
                "page_num": chunk.get("page_num"),
                "doc_id": chunk.get("doc_id"),
            }
            for chunk in chunks[:12]
        ],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_kind: str,
    source_ids: Optional[List[str]] = None,
    concept_ids: Optional[List[str]] = None,
    goal_id: Optional[str] = None,
    session_id: Optional[str] = None,
    audience: str = "student",
    difficulty: str = "standard",
    depth: str = "standard",
    style: str = "prose",
    output_length: str = "medium",
    evidence_strictness: str = "normal",
    custom_prompt: Optional[str] = None,
    show_citations: bool = False,
    grounding_mode: str = "internal_only",
) -> Dict[str, Any]:
    if artifact_kind not in _KIND_TO_GENERATOR:
        artifact_kind = "study_guide"

    concepts = _concepts_for_scope(conn, source_ids, concept_ids, limit=16)

    goal_text = ""
    if goal_id:
        row = conn.execute("SELECT title FROM goals WHERE id = ?", (goal_id,)).fetchone()
        if row:
            goal_text = row["title"]

    retrieval_query = " ".join(
        part
        for part in [
            artifact_kind.replace("_", " "),
            custom_prompt or "",
            goal_text,
            " ".join(concept.get("name", "") for concept in concepts[:6]),
        ]
        if part
    ).strip()
    if artifact_kind == "flashcards" and source_ids and not concept_ids:
        chunks = _fresh_chunks_for_sources(conn, source_ids) or _chunk_text_for_scope(conn, source_ids, concept_ids, limit=96)
    else:
        chunks = retrieve_grounding_chunks(
            conn,
            source_ids=source_ids,
            concept_ids=concept_ids,
            query=retrieval_query,
            limit=12,
        )
    focus_concepts = _select_focus_concepts(concepts, chunks, limit=10)
    topic_map = _build_topic_map(focus_concepts)
    deck_items = None
    if artifact_kind == "flashcards":
        deck_title = str(custom_prompt or goal_text or (chunks[0].get("filename") if chunks else "") or artifact_kind).strip()
        deck_items = build_flashcard_deck(chunks, title=deck_title, count=12)
    markdown = _KIND_TO_GENERATOR[artifact_kind](
        focus_concepts,
        chunks,
        depth=depth,
        goal=goal_text,
        topic_map=topic_map,
        deck_items=deck_items,
    )
    hidden_payload = _hidden_artifact_payload(
        artifact_kind,
        focus_concepts,
        chunks,
        topic_map,
        custom_prompt=custom_prompt,
        deck_items=deck_items,
    )
    prompt_text = artifact_prompts.build_artifact_prompt(
        artifact_kind=artifact_kind,
        topic_map=topic_map,
        concepts=[
            {
                "id": concept["id"],
                "name": concept["name"],
                "description": concept.get("study_description") or concept.get("description"),
                "topic": concept.get("topic"),
            }
            for concept in focus_concepts
        ],
        grounding_chunks=[
            {
                "id": chunk.get("id"),
                "section": chunk.get("section"),
                "page_num": chunk.get("page_num"),
                "content": chunk.get("content"),
            }
            for chunk in chunks
        ],
        custom_prompt=custom_prompt,
    )

    source_scope_json = json.dumps(source_ids or [])
    concept_scope_json = json.dumps(concept_ids or [])

    # Build snapshot hash from all participating sources
    source_hashes = []
    if source_ids:
        rows = conn.execute(
            f"SELECT COALESCE(source_hash, id) AS h FROM documents WHERE id IN ({','.join('?' * len(source_ids))})",
            source_ids,
        ).fetchall()
        source_hashes = [r["h"] for r in rows]
    snapshot_hash = ":".join(sorted(source_hashes)) if source_hashes else None

    artifact_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO artifacts (
            id, artifact_kind, goal_id, session_id, source_scope, concept_scope,
            audience, difficulty, depth, style, output_length, evidence_strictness,
            prompt_text, output_markdown, output_json, source_snapshot_hash, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
        """,
        (
            artifact_id, artifact_kind, goal_id, session_id,
            source_scope_json, concept_scope_json,
            audience, difficulty, depth, style, output_length, evidence_strictness,
            prompt_text, markdown, json.dumps(hidden_payload, ensure_ascii=False), snapshot_hash,
        ),
    )
    # --- Link evidence references to artifact (Phase 1c) ---
    evidence_ids: List[str] = []
    for ch in chunks[:6]:
        snippet = (ch.get("content") or "")[:200].strip()
        doc_id = ch.get("doc_id")
        chunk_id = ch.get("id")
        if not snippet or not doc_id or not chunk_id:
            continue
        try:
            ev = provenance_service.build_evidence_reference(
                conn,
                {"document_id": doc_id, "chunk_id": chunk_id, "snippet": snippet,
                 "page_num": ch.get("page_num"), "section": ch.get("section")},
                confidence=0.65,
            )
            evidence_ids.append(ev["id"])
        except Exception:
            pass
    if evidence_ids:
        provenance_service.link_evidence_to_artifact(conn, artifact_id, evidence_ids)

    # --- Link to session if provided (Phase 1d) ---
    if session_id:
        provenance_service.link_session_artifact(conn, session_id, artifact_id)

    conn.commit()

    return {
        "id": artifact_id,
        "artifact_kind": artifact_kind,
        "output_markdown": markdown,
        "audience": audience,
        "depth": depth,
        "output_length": output_length,
        "status": "ready",
        "stale": False,
        "concept_count": len(concepts),
        "source_count": len(set(ch.get("doc_id", "") for ch in chunks)),
        "evidence_count": len(evidence_ids),
        "grounding_mode": grounding_mode,
        "show_citations": show_citations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def list_artifacts(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, artifact_kind, audience, depth, output_length, status, stale,
               output_markdown, created_at, updated_at
        FROM artifacts
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        md = item.get("output_markdown") or ""
        item["preview"] = md[:200] + "…" if len(md) > 200 else md
        item.pop("output_markdown", None)
        items.append(item)
    return items


def get_artifact(conn: sqlite3.Connection, artifact_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """
        SELECT id, artifact_kind, goal_id, session_id, source_scope, concept_scope,
               audience, difficulty, depth, style, output_length, evidence_strictness,
               prompt_text, output_markdown, output_json, source_snapshot_hash, version, status, stale,
               created_at, updated_at
        FROM artifacts
        WHERE id = ?
        """,
        (artifact_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    for field in ("source_scope", "concept_scope"):
        try:
            item[field] = json.loads(item[field] or "[]")
        except Exception:
            item[field] = []
    try:
        item["output_json"] = json.loads(item.get("output_json") or "{}")
    except Exception:
        item["output_json"] = {}
    return item
