import json
from typing import Any, Callable, Dict, List, Optional

from ai.router import ClaudeCallResult, ClaudeTask, get_default_router

_ROUTER = get_default_router()
DEFAULT_MODEL = _ROUTER.balanced_model
LAST_CALL_RESULT: Optional[ClaudeCallResult] = None

def ai_enabled() -> bool:
    return _ROUTER.ai_enabled()


def get_last_call_result() -> Optional[ClaudeCallResult]:
    return LAST_CALL_RESULT


def _request_text_result(
    request_kind: str,
    *,
    system: str,
    prompt: str,
    max_tokens: int = 1600,
    task: ClaudeTask = "balanced",
) -> ClaudeCallResult:
    global LAST_CALL_RESULT
    LAST_CALL_RESULT = _ROUTER.request_text(
        request_kind=request_kind,
        system=system,
        prompt=prompt,
        max_tokens=max_tokens,
        task=task,
    )
    return LAST_CALL_RESULT


def _request_text(
    request_kind: str,
    *,
    system: str,
    prompt: str,
    max_tokens: int = 1600,
    task: ClaudeTask = "balanced",
) -> Optional[str]:
    result = _request_text_result(
        request_kind,
        system=system,
        prompt=prompt,
        max_tokens=max_tokens,
        task=task,
    )
    return result.text if result.ok else None


def _request_json(
    request_kind: str,
    *,
    system: str,
    prompt: str,
    fallback: Any,
    max_tokens: int = 1600,
    task: ClaudeTask = "balanced",
):
    global LAST_CALL_RESULT
    LAST_CALL_RESULT = _ROUTER.request_json(
        request_kind=request_kind,
        system=system,
        prompt=prompt,
        max_tokens=max_tokens,
        task=task,
    )
    if LAST_CALL_RESULT.ok:
        return LAST_CALL_RESULT.json_payload
    return fallback


def generate_summary(text: str, fallback: Callable[[], str]) -> str:
    response = _request_text(
        "generate_summary",
        system="You summarize study material into concise, grounded learning summaries.",
        prompt=(
            "Summarize the following study material in 2-3 sentences. Focus on the main mechanisms, relationships, "
            "and study-worthy ideas. Do not invent details.\n\n"
            f"{text[:12000]}"
        ),
        max_tokens=500,
        task="fast",
    )
    return response or fallback()


def extract_concepts(text: str, doc_title: str, fallback: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    payload = _request_json(
        "extract_concepts",
        system="You extract key study concepts and return strict JSON only.",
        prompt=(
            "Return a JSON array with 5-10 key concepts for this document. "
            "Each item must include: name, description, mastery, related_terms.\n\n"
            f"Document title: {doc_title}\n\n"
            f"Document text:\n{text[:16000]}"
        ),
        fallback=None,
        max_tokens=1800,
        task="balanced",
    )
    if not isinstance(payload, list) or not payload:
        return fallback()
    concepts: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        mastery = item.get("mastery", 0.5)
        try:
            mastery = max(0.05, min(1.0, float(mastery)))
        except (TypeError, ValueError):
            mastery = 0.5
        concepts.append(
            {
                "name": str(item["name"]).strip(),
                "description": str(item.get("description") or item["name"]).strip(),
                "summary": str(item.get("description") or item["name"]).strip(),
                "mastery": round(mastery, 2),
                "difficulty_label": "Hard" if mastery >= 0.7 else "Medium" if mastery >= 0.45 else "Easy",
                "related_terms": [str(term).strip() for term in item.get("related_terms", []) if str(term).strip()],
            }
        )
    return concepts or fallback()


def curate_concept_options(
    doc_title: str,
    goal: str,
    concepts: List[Dict[str, Any]],
    context: str,
    fallback: Callable[[], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    payload = _request_json(
        "curate_concept_options",
        system="You curate concept selector options for a study workspace and return strict JSON only.",
        prompt=(
            "Return a JSON array with 4-8 concept selector items chosen only from the provided concept ids. "
            "Each item must include: concept_id, display_name, reason. "
            "Pick the concepts that are most central, readable, and study-worthy for a learner. "
            "Rewrite noisy OCR-like labels into short learner-friendly labels. "
            "Avoid boilerplate, copyright fragments, and duplicate concepts.\n\n"
            f"Document title: {doc_title}\n"
            f"Learning goal: {goal or 'No goal set'}\n\n"
            f"Candidate concepts: {json.dumps(concepts)}\n\n"
            f"Document context:\n{context[:12000]}"
        ),
        fallback=None,
        max_tokens=1600,
        task="fast",
    )
    if not isinstance(payload, list) or not payload:
        return fallback()
    curated: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("concept_id") or not item.get("display_name"):
            continue
        curated.append(
            {
                "concept_id": str(item["concept_id"]).strip(),
                "display_name": str(item["display_name"]).strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return curated or fallback()


def generate_questions(
    concepts: List[str],
    context: str,
    fallback: Callable[[], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    payload = _request_json(
        "generate_questions",
        system="You create grounded multiple-choice questions from study material and return strict JSON only.",
        prompt=(
            "Return a JSON array with one multiple-choice question per concept. "
            "Each item must include: concept, question, answer, distractors, explanation, difficulty_value.\n\n"
            f"Concepts: {json.dumps(concepts)}\n\nContext:\n{context[:12000]}"
        ),
        fallback=None,
        max_tokens=1800,
        task="balanced",
    )
    if not isinstance(payload, list) or not payload:
        return fallback()
    normalized = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("question") or not item.get("answer"):
            continue
        distractors = item.get("distractors", [])
        if not isinstance(distractors, list):
            distractors = []
        try:
            difficulty_value = float(item.get("difficulty_value", 0.5))
        except (TypeError, ValueError):
            difficulty_value = 0.5
        normalized.append(
            {
                "concept": str(item.get("concept") or "").strip(),
                "question": str(item["question"]).strip(),
                "answer": str(item["answer"]).strip(),
                "distractors": [str(choice).strip() for choice in distractors if str(choice).strip()][:3],
                "explanation": str(item.get("explanation") or "").strip(),
                "difficulty_value": max(0.05, min(1.0, difficulty_value)),
            }
        )
    return normalized or fallback()


def generate_srs_cards(
    concept: str,
    context: str,
    fallback: Callable[[], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    payload = _request_json(
        "generate_srs_cards",
        system="You create compact spaced-repetition cards and return strict JSON only.",
        prompt=(
            "Return a JSON array with 2 flashcards for the concept. "
            "Each card must include: card_type, front, back, difficulty.\n\n"
            f"Concept: {concept}\n\nContext:\n{context[:9000]}"
        ),
        fallback=None,
        max_tokens=1200,
        task="fast",
    )
    if not isinstance(payload, list) or not payload:
        return fallback()
    cards = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("front") or not item.get("back"):
            continue
        try:
            difficulty = float(item.get("difficulty", 0.5))
        except (TypeError, ValueError):
            difficulty = 0.5
        cards.append(
            {
                "card_type": str(item.get("card_type") or "definition"),
                "front": str(item["front"]).strip(),
                "back": str(item["back"]).strip(),
                "difficulty": max(0.05, min(0.95, difficulty)),
            }
        )
    return cards or fallback()


def generate_concept_edges(
    concepts: List[Dict[str, Any]],
    text: str,
    fallback: Callable[[], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    payload = _request_json(
        "generate_concept_edges",
        system="You identify semantic relationships between study concepts and return strict JSON only.",
        prompt=(
            "Return a JSON array of concept relationships. "
            "Each item must include: source_name, target_name, relationship.\n\n"
            f"Concepts: {json.dumps([item.get('name') for item in concepts])}\n\nText:\n{text[:12000]}"
        ),
        fallback=None,
        max_tokens=1200,
        task="balanced",
    )
    if not isinstance(payload, list) or not payload:
        return fallback()
    edges = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("source_name") or not item.get("target_name"):
            continue
        edges.append(
            {
                "source_name": str(item["source_name"]).strip(),
                "target_name": str(item["target_name"]).strip(),
                "relationship": str(item.get("relationship") or "relates to").strip(),
            }
        )
    return edges or fallback()


def tutor_response(
    question: str,
    chunks: List[str],
    concepts: List[str],
    fallback: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    response = _request_text(
        "tutor_response",
        system=(
            "You are Carrel, a study tutor. Answer using only the supplied study material, keep the answer concise, "
            "and avoid unsupported claims."
        ),
        prompt=(
            f"Question: {question}\n\nConcepts: {json.dumps(concepts)}\n\nStudy material:\n"
            + "\n\n".join(chunks[:8])
        ),
        max_tokens=900,
        task="balanced",
    )
    if not response:
        return fallback()
    payload = fallback()
    payload["answer"] = response
    return payload


def compare_documents(
    left_context: str,
    right_context: str,
    question: str,
    fallback: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    payload = _request_json(
        "compare_documents",
        system="You compare study concepts and return strict JSON only.",
        prompt=(
            "Return JSON with keys: similarities, differences, study_prompt.\n\n"
            f"Question: {question}\n\nLeft:\n{left_context[:5000]}\n\nRight:\n{right_context[:5000]}"
        ),
        fallback=None,
        max_tokens=1200,
        task="balanced",
    )
    if not isinstance(payload, dict):
        return fallback()
    result = fallback()
    if isinstance(payload.get("similarities"), list) and payload["similarities"]:
        result["similarities"] = [str(item) for item in payload["similarities"]]
    if isinstance(payload.get("differences"), list) and payload["differences"]:
        result["differences"] = [str(item) for item in payload["differences"]]
    if payload.get("study_prompt"):
        result["study_prompt"] = str(payload["study_prompt"])
    return result


# ── Artifact generation ────────────────────────────────────────────────────────

def generate_artifact(
    artifact_kind: str,
    context: str,
    concepts: List[str],
    goal: str,
    audience: str = "student",
    depth: str = "standard",
    output_length: str = "medium",
    custom_prompt: Optional[str] = None,
    fallback: Optional[Callable[[], str]] = None,
) -> str:
    """Generate a Markdown artifact powered by Claude."""
    length_hint = {"short": "300-500 words", "medium": "600-1200 words", "long": "1400-2500 words"}.get(output_length, "600-1200 words")
    token_limit = {"short": 1200, "medium": 2400, "long": 4000}.get(output_length, 2400)

    system = (
        f"You generate high-quality {artifact_kind.replace('_', ' ')} study artifacts in Markdown. "
        f"Audience: {audience}. Depth: {depth}. Target length: {length_hint}. "
        "Ground every claim in the supplied study material. Do not invent facts."
    )
    user_prompt = (
        f"Generate a {artifact_kind.replace('_', ' ')} from the following study material.\n\n"
        f"Concepts: {json.dumps(concepts)}\n"
        f"{'Goal: ' + goal + chr(10) if goal else ''}"
        f"{'Custom instructions: ' + custom_prompt + chr(10) if custom_prompt else ''}\n"
        f"Study material:\n{context[:14000]}"
    )
    response = _request_text(
        "generate_artifact",
        system=system,
        prompt=user_prompt,
        max_tokens=token_limit,
        task="deep",
    )
    if response:
        return response
    if fallback:
        return fallback()
    return f"# {artifact_kind.replace('_', ' ').title()}\n\nArtifact generation requires a valid ANTHROPIC_API_KEY."


# ── Enhanced tutor response (with citations, scaffolds, misconceptions) ───────

def tutor_response_v2(
    question: str,
    chunks: List[Dict[str, Any]],
    concepts: List[str],
    learner_confidence: int = 50,
    selected_text: Optional[str] = None,
    response_mode: str = "standard",
    fallback: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Enhanced tutor response returning structured JSON with citations, scaffolds, misconceptions."""
    chunk_context = "\n\n".join(
        f"[chunk_id={ch.get('id', i)}, source={ch.get('filename', 'Unknown')}, page={ch.get('page_num', '?')}]\n{ch.get('content', '')}"
        for i, ch in enumerate(chunks[:8])
    )
    sel_block = f"\nThe learner selected this text: \"{selected_text}\"\n" if selected_text else ""
    mode_hint = {
        "easier": "Use simpler language, shorter sentences, and concrete analogies.",
        "deeper": "Go deeper into mechanisms and edge cases. Be thorough.",
        "exam": "Frame the answer as exam preparation with key facts to remember.",
    }.get(response_mode, "")

    payload = _request_json(
        "tutor_response_v2",
        system=(
            "You are Carrel, a source-grounded adaptive tutor. "
            "Answer ONLY from the supplied study material. Never invent claims. "
            "Return a JSON object with these keys:\n"
            "  answer: string (the main explanation, Markdown OK)\n"
            "  citations: array of {label, chunk_id, snippet, page_num} — reference chunks used\n"
            "  scaffolds: array of strings — 2-3 follow-up study steps\n"
            "  misconceptions: array of strings — common mistakes related to this topic\n"
            "  confidence_model: float 0-1 — how confident YOU are in the answer based on evidence\n"
            f"Learner self-reported confidence: {learner_confidence}%. "
            f"{mode_hint}"
        ),
        prompt=f"Question: {question}\n{sel_block}\nConcepts: {json.dumps(concepts)}\n\nStudy material:\n{chunk_context}",
        fallback=None,
        max_tokens=2000,
        task="deep",
    )
    if isinstance(payload, dict) and payload.get("answer"):
        return payload
    return None


# ── Synthesis: AI-powered cross-source analysis ───────────────────────────────

def synthesize_sources(
    synthesis_type: str,
    source_chunks: Dict[str, List[Dict[str, Any]]],
    concept_names: List[str],
    fallback: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Cross-source synthesis using Claude."""
    type_instructions = {
        "compare": "Compare all sources. Return JSON with: contradictions (array), agreements (array), gaps (array), themes (array of strings).",
        "agreement": "Find all points of agreement across sources. Return JSON with: shared_concepts (array of {name, source_count}), themes (array of strings), source_count (int).",
        "gaps": "Find concepts that appear in some sources but not others. Return JSON with: gaps (array of {concept_name, present_in (array), missing_in (array)}).",
        "terminology": "Find terms that mean similar things but use different names. Return JSON with: alignments (array of {term_a, term_b, source_a, source_b, overlap_reason}).",
    }.get(synthesis_type, "Compare all sources and return JSON with contradictions, agreements, gaps, themes.")

    source_text = ""
    for source_name, chunks in list(source_chunks.items())[:4]:
        chunk_text = "\n".join(ch.get("content", "")[:800] for ch in chunks[:4])
        source_text += f"\n\n--- SOURCE: {source_name} ---\n{chunk_text}"

    payload = _request_json(
        "synthesize_sources",
        system=(
            "You perform cross-source synthesis for adaptive learning. "
            "Ground every finding in the actual source text. Do not invent. "
            f"{type_instructions}"
        ),
        prompt=f"Concepts: {json.dumps(concept_names)}\n\nSources:{source_text[:16000]}",
        fallback=None,
        max_tokens=2400,
        task="deep",
    )
    if isinstance(payload, dict):
        return payload
    return None


# ── Evaluate learner response ─────────────────────────────────────────────────

def evaluate_response(
    exchange_context: str,
    learner_response: str,
    concept_name: str,
    fallback: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Classify a learner's self-check answer and suggest a repair path."""
    payload = _request_json(
        "evaluate_response",
        system=(
            "You are an examiner for an adaptive tutor. Classify the learner's response. "
            "Return JSON with:\n"
            "  classification: one of 'omission', 'misconception', 'wrong_relation', 'wrong_example', 'shallow_but_correct', 'robust_and_transferable'\n"
            "  explanation: string — brief feedback\n"
            "  repair_path: {strategy: string, next_action: string, surface: string (one of 'tutor','review','concept')}\n"
            "  revisit: {schedule_in_minutes: int}\n"
            "  score: float 0-1"
        ),
        prompt=(
            f"Concept: {concept_name}\n\n"
            f"Exchange context:\n{exchange_context[:4000]}\n\n"
            f"Learner response: {learner_response}"
        ),
        fallback=None,
        max_tokens=800,
        task="balanced",
    )
    if isinstance(payload, dict) and payload.get("classification"):
        return payload
    return None
