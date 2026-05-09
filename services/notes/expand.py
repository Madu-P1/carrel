from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from ai.providers import get_default_provider
from services.helpers import concept_takeaway, split_sentences
from services.ingestion import build_concept_payloads, summarize_document


ProviderFactory = Callable[[], Any]


_SUBMIT_EXPANDED_NOTE_TOOL: Dict[str, Any] = {
    "name": "submit_expanded_note",
    "description": "Produce a structured study-notes expansion of a terse user input.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "2 to 4 sentences that EXPLAIN the concept. Must add real "
                    "information beyond the user's input. Never a restatement."
                ),
            },
            "key_ideas": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "1 to 3 word noun phrase, no punctuation.",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "1 or 2 sentences that explain the sub-concept "
                                "concretely. Never a reword of the name."
                            ),
                        },
                    },
                    "required": ["name", "description"],
                },
            },
            "organized_notes": {
                "type": "array",
                "minItems": 4,
                "maxItems": 8,
                "items": {"type": "string"},
                "description": (
                    "Study-ready factual bullets in logical order: definition, "
                    "mechanism, examples, edge cases. Each a single sentence."
                ),
            },
            "review_prompts": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {"type": "string"},
                "description": (
                    "Questions that test comprehension, not name recall. "
                    "Prefer how, why, when, and compare questions."
                ),
            },
        },
        "required": ["summary", "key_ideas", "organized_notes", "review_prompts"],
    },
}

_EXPAND_NOTE_SYSTEM = (
    "You expand rough study notes into rigorous, concrete study material for a "
    "serious learner.\n\n"
    "Non-negotiables:\n"
    "1. Never restate the user's input. If they write \"Bonds are issued by "
    'government bodies," your summary is NOT that sentence. It explains what '
    "a bond IS (a debt security, fixed-income instrument), how it works (face "
    "value, coupon, maturity, yield), who else issues them (corporations, "
    "agencies, municipalities), and why it matters.\n"
    "2. Add substance. If the note leaves out an obvious mechanism, add it. "
    "If it implies a partial truth, expand to the fuller picture. If a term "
    "has a standard definition, give that definition.\n"
    "3. Be concrete. Use real examples, real organizations, real numbers, "
    "real timeframes.\n"
    "4. Short sentences. One idea per sentence.\n"
    "5. Do not use: delve, crucial, comprehensive, robust, nuanced, "
    "multifaceted, furthermore, moreover, additionally, pivotal, landscape, "
    "tapestry, underscore, foster, showcase, intricate, vibrant, fundamental, "
    "significant, interplay. Do not use em dashes. Do not hedge with "
    "essentially, basically, in essence.\n"
    "6. Review prompts must be COMPLETE QUESTIONS ending with a question mark. "
    'Four words minimum. Test understanding, not name recall. Prefer "How '
    'does X change when Y increases?" over "What is X?". NEVER emit a '
    'plain heading like "Bond Yields" or a field identifier like '
    '"yield_and_bond_prices" as a review prompt. Every prompt is a '
    "grammatical question.\n"
    "7. Organized notes are COMPLETE SENTENCES ending with a period. Not "
    'headings. Not labels. Not outline points. "Bonds pay fixed coupon '
    'interest until maturity." is right. "Bond Valuation" is wrong.\n\n'
    "Fill every field of the submit_expanded_note tool."
)


_IDENTIFIER_LOOKALIKE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
_TITLE_CASE_HEADING = re.compile(
    r"^(?:[A-Z][A-Za-z0-9-]*)(?:[ :][A-Z][A-Za-z0-9-]*){0,5}[A-Za-z0-9]$"
)


def expand_note_content(
    *,
    title: str,
    content: str,
    provider_factory: ProviderFactory = get_default_provider,
) -> Dict[str, Optional[str]]:
    ai_payload, error_code = _try_ai_expansion(title, content, provider_factory)
    if ai_payload is not None:
        return {
            "expanded_markdown": _format_expansion_markdown(title, ai_payload),
            "mode": "ai",
            "error_code": None,
        }

    return {
        "expanded_markdown": _build_deterministic_expansion(title, content),
        "mode": "deterministic",
        "error_code": error_code or "ai_failed",
    }


def _looks_like_schema_leak(text: str) -> bool:
    if not text:
        return True
    return bool(_IDENTIFIER_LOOKALIKE.match(text))


def _is_real_sentence(text: str) -> bool:
    if not text or len(text) < 12:
        return False
    if " " not in text:
        return False
    if _TITLE_CASE_HEADING.match(text):
        return False
    return text.endswith((".", "!", "?"))


def _is_real_question(text: str) -> bool:
    if not text:
        return False
    if not text.endswith("?"):
        return False
    return len(text.split()) >= 4


def _format_expansion_markdown(title: str, payload: Dict[str, Any]) -> str:
    summary = str(payload.get("summary") or "").strip()
    lines: List[str] = [f"# {title}", "", "## Summary", summary or "No summary produced."]

    key_ideas = payload.get("key_ideas") or []
    if isinstance(key_ideas, list) and key_ideas:
        body: List[str] = []
        for item in key_ideas:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if not name or not description:
                continue
            if _looks_like_schema_leak(name) or _looks_like_schema_leak(description):
                continue
            body.append(f"- **{name}**: {description}")
        if body:
            lines.extend(["", "## Key Ideas", *body])

    notes = payload.get("organized_notes") or []
    if isinstance(notes, list) and notes:
        body = []
        for note in notes:
            text = str(note).strip()
            if not text or _looks_like_schema_leak(text):
                continue
            if not _is_real_sentence(text):
                continue
            body.append(text)
        if body:
            lines.extend(["", "## Organized Notes"])
            lines.extend(f"{index}. {note}" for index, note in enumerate(body, start=1))

    prompts = payload.get("review_prompts") or []
    if isinstance(prompts, list) and prompts:
        body = []
        for prompt in prompts:
            text = str(prompt).strip()
            if not text or _looks_like_schema_leak(text):
                continue
            if not _is_real_question(text):
                continue
            body.append(f"- {text}")
        if body:
            lines.extend(["", "## Review Prompts", *body])

    return "\n".join(lines).strip()


def _try_ai_expansion(
    title: str,
    content: str,
    provider_factory: ProviderFactory,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    provider = provider_factory()
    if not provider.ai_enabled():
        return None, "ai_disabled"

    result = provider.request_tool_call(
        request_kind="notes.expand",
        system=_EXPAND_NOTE_SYSTEM,
        prompt=f"Title: {title}\n\nUser's note:\n{content}",
        tool=_SUBMIT_EXPANDED_NOTE_TOOL,
        max_tokens=1600,
        task="fast",
    )
    if not result.ok or not isinstance(result.json_payload, dict):
        return None, result.error_code or "ai_failed"
    payload = result.json_payload
    required_lists = ("key_ideas", "organized_notes", "review_prompts")
    if not isinstance(payload.get("summary"), str):
        return None, "malformed_payload"
    if any(not isinstance(payload.get(key), list) for key in required_lists):
        return None, "malformed_payload"
    return payload, None


def _build_deterministic_expansion(title: str, content: str) -> str:
    summary = summarize_document(content, max_sentences=3)
    concepts = build_concept_payloads(content, title, limit=5)
    sentences = split_sentences(content)

    lines = [
        f"# {title}",
        "",
        "## Summary",
        summary or "Review the note once, then restate the main idea in your own words.",
    ]

    if concepts:
        lines.extend(["", "## Key Ideas"])
        for concept in concepts[:5]:
            description = str(
                concept.get("description") or concept.get("summary") or concept["name"]
            )
            lines.append(f"- **{concept['name']}**: {concept_takeaway(description)}")

    if sentences:
        lines.extend(["", "## Organized Notes"])
        for index, sentence in enumerate(sentences[:6], start=1):
            lines.append(f"{index}. {sentence}")

    review_prompts = [
        f"How would you explain **{concept['name']}** without looking?" for concept in concepts[:3]
    ]
    if not review_prompts:
        review_prompts = [
            "What is the single most important idea in this note?",
            "Which part would you want to practice from memory next?",
        ]
    lines.extend(["", "## Review Prompts", *[f"- {prompt}" for prompt in review_prompts]])
    return "\n".join(lines).strip()
