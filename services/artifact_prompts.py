from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


BASE_RULES = """You are generating study artefacts from a source-grounded internal document representation.

You are given:
- a topic map
- cleaned extracted content
- prioritized concepts
- relevant supporting evidence
- hidden provenance metadata

Your job is to generate clean user-facing study artefacts.

Rules:
1. Base every output on the provided source material.
2. Do not invent facts not supported by the source.
3. Do not expose citations, source labels, file names, section ids, chunk ids, or evidence markers unless citation mode is explicitly enabled.
4. Do not use raw extraction debris.
5. Do not generate items from boilerplate, chapter outlines, repeated headers, page numbers, copyright lines, or decorative text.
6. Prefer concept understanding over phrase copying.
7. Questions must sound natural and educational.
8. Answers must be precise, self-contained, and useful for revision.
9. Avoid trivial, duplicate, or malformed items.
10. If source support is weak, skip the item instead of guessing.

Grounding mode: internal_only
Show citations: false
"""


KIND_TEMPLATES = {
    "flashcards": """Flashcard-specific rules:
- Generate cards only from high-value concepts.
- Prefer definitions, distinctions, rules, examples, processes, exceptions, and applications.
- Never use “What does the source say about...” phrasing.
- Never use section titles alone as answers.
- Never expose file names or source references in the flashcard.
- Keep fronts concise.
- Keep backs accurate and complete.
""",
    "quiz": """Quiz-specific rules:
- Create a topic-balanced coverage plan before writing questions.
- Make distractors plausible but wrong.
- Avoid mixing unrelated sections into one question.
- Ensure one clearly best answer.
- Do not expose source citations in question text or answers.
""",
    "mock_exam": """Mock-exam-specific rules:
- Test understanding and application.
- Reflect the main themes and weight of the source.
- Use realistic academic wording.
- Avoid vague or generic questions.
- Keep outputs citation-free unless explicitly requested.
""",
    "summary": """Summary-specific rules:
- Group content by topic instead of extraction order.
- Prefer coherent explanations over copied fragments.
- Keep hierarchy clean and avoid raw extraction debris.
""",
    "study_guide": """Study-guide-specific rules:
- Organize by major topic, then subtopic.
- Lead with definitions, rules, distinctions, and key examples.
- Keep source evidence internal only.
""",
}


def build_artifact_prompt(
    *,
    artifact_kind: str,
    topic_map: List[Dict[str, Any]],
    concepts: List[Dict[str, Any]],
    grounding_chunks: List[Dict[str, Any]],
    custom_prompt: Optional[str] = None,
) -> str:
    payload = {
        "artifact_kind": artifact_kind,
        "custom_prompt": custom_prompt or "",
        "topic_map": topic_map,
        "concepts": concepts[:10],
        "grounding_chunks": grounding_chunks[:10],
    }
    return "\n".join(
        [
            BASE_RULES.strip(),
            "",
            KIND_TEMPLATES.get(artifact_kind, KIND_TEMPLATES["study_guide"]).strip(),
            "",
            "Normalized document representation:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    ).strip()

