"""Artifact generators — markdown + structured JSON output.

Houses 9 markdown generators (study guide, briefing, FAQ, flashcards,
quiz, outline, summary, report, mock exam, concept_map alias), the 3
item-builders (`_flashcard_items`, `_quiz_items`, `_mock_exam_items`),
the kind→generator dispatch table (`_KIND_TO_GENERATOR`), and the
shadow JSON-payload generator (`_hidden_artifact_payload`).

Per the autoplan eng review, `_hidden_artifact_payload` lives here
(not in the orchestrator) because it's structurally a generator —
it produces the JSON twin of the markdown output and reuses the
same item builders.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.helpers import split_sentences

from .topic_map import _concept_importance


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
