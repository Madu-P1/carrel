from __future__ import annotations

import re
from typing import Dict, List, Optional

from services.extraction.quality import (
    classify_span_role,
    footer_or_noise_text as _is_footer_or_noise_text,
    is_bullet_like as _is_bullet_like,
    is_formula_text as _is_formula_like_text,
    outline_like_text as _is_outline_like_text,
    strip_bullet_prefix as _strip_bullet_prefix,
)

from .answers import (
    _best_evidence_sentences,
    _concept_label_from_sentence,
    _is_valid_answer_text,
    _normalize_candidate_phrase,
    _normalize_structural_label,
)
from .concept_candidates import is_valid_concept_label
from .constants import BAD_LABEL_PREFIXES, CARD_DEFINITION_MARKERS, CONNECTOR_TOKENS
from .text_utils import _normalize_space, split_sentences, tokenize


def _ensure_terminal_period(text: str) -> str:
    """Ensure a sentence ends in `.`, `!`, `?`, or `:`.

    Bullet-point source text frequently lacks terminal punctuation; when
    two such bullets are joined with a space, downstream readers (the
    Concept Atlas "takeaway" field, the Reader chunk preview) render
    the result as one run-on sentence. Adding a period per sentence
    before the join keeps the original evidence words intact while
    preserving sentence boundaries for split_sentences and human
    readers.

    Idempotent: re-running the function on already-terminated text is a
    no-op.
    """
    stripped = str(text or "").rstrip()
    if not stripped:
        return ""
    if stripped[-1] in ".!?:;":
        return stripped
    return stripped + "."


def _segment_chunk_for_study(chunk: Dict[str, object]) -> List[Dict[str, object]]:
    content = str(chunk.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
    content = content.replace("▪", "\n• ").replace("•", "\n• ").replace("\uf0b7", "\n• ")
    if not content.strip():
        return []
    section = _normalize_structural_label(str(chunk.get("section") or ""))
    lines = [_normalize_space(line) for line in content.splitlines() if _normalize_space(line)]
    if not lines:
        return []

    slide_like = bool(
        str(chunk.get("section") or "").lower().startswith("page ")
        or sum(1 for line in lines if _is_bullet_like(line)) >= 1
        or len(lines) >= 4
    )
    spans: List[Dict[str, object]] = []
    chunk_id = str(chunk.get("id") or "")
    page_num = chunk.get("page_num")

    def append_span(text: str, role: str, topic: Optional[str]) -> None:
        cleaned = _normalize_space(text)
        if not cleaned:
            return
        spans.append(
            {
                "chunk_id": chunk_id,
                "page_num": page_num,
                "section": section,
                "topic": topic or section or "Core Ideas",
                "role": role,
                "text": cleaned,
                "slide_like": slide_like,
            }
        )

    if not slide_like:
        for sentence in split_sentences(content):
            role = classify_span_role(sentence, kind="paragraph", topic_hint=section)
            append_span(sentence, role, section)
        return spans

    index = 0
    title_lines: List[str] = []
    while index < len(lines):
        line = lines[index]
        if _is_footer_or_noise_text(line) and not _is_outline_like_text(line, section):
            index += 1
            continue
        if _is_bullet_like(line) or _is_formula_like_text(line):
            break
        if title_lines and (re.search(r"[.!?]$", line) or len(line.split()) > 8):
            break
        title_lines.append(_strip_bullet_prefix(line))
        index += 1
        next_line = lines[index] if index < len(lines) else ""
        if (
            len(title_lines) >= 3
            or len(" ".join(title_lines)) >= 140
            or _is_bullet_like(next_line)
            or _is_formula_like_text(next_line)
        ):
            break

    active_topic = section or "Core Ideas"
    title_is_outline = False
    if title_lines:
        title_text = _normalize_structural_label(" ".join(title_lines))
        title_role = classify_span_role(title_text, kind="heading", topic_hint=section)
        append_span(
            title_text, title_role, title_text if title_role in {"title", "heading"} else section
        )
        if title_role in {"title", "heading"}:
            active_topic = title_text
        title_is_outline = title_role == "outline"

    buffer: List[str] = []
    buffer_role: Optional[str] = None

    def flush_buffer() -> None:
        nonlocal buffer, buffer_role
        if not buffer or not buffer_role:
            buffer = []
            buffer_role = None
            return
        append_span(" ".join(buffer), buffer_role, active_topic)
        buffer = []
        buffer_role = None

    for raw_line in lines[index:]:
        line = _strip_bullet_prefix(raw_line)
        if not line:
            flush_buffer()
            continue
        if _is_footer_or_noise_text(line):
            flush_buffer()
            continue
        kind = "bullet_list" if _is_bullet_like(raw_line) else "paragraph"
        role = (
            "outline"
            if title_is_outline
            else classify_span_role(line, kind=kind, topic_hint=active_topic)
        )
        if role in {"noise", "footer"}:
            flush_buffer()
            continue
        if (
            buffer
            and role == buffer_role
            and not _is_bullet_like(raw_line)
            and buffer_role in {"body", "formula", "outline"}
            and (len(buffer[-1]) < 110 or not re.search(r"[.!?]$", buffer[-1]))
        ):
            buffer[-1] = f"{buffer[-1]} {line}".strip()
            continue
        flush_buffer()
        buffer = [line]
        buffer_role = role
    flush_buffer()
    return spans


def _build_semantic_topics(
    chunk_rows: List[Dict[str, object]], title: str
) -> List[Dict[str, object]]:
    spans: List[Dict[str, object]] = []
    for chunk in chunk_rows:
        spans.extend(_segment_chunk_for_study(chunk))
    topics: Dict[str, Dict[str, object]] = {}
    document_title = _normalize_candidate_phrase(title) or "Core Ideas"
    for span in spans:
        role = str(span.get("role") or "body")
        if role in {"noise", "footer"}:
            continue
        topic = _normalize_structural_label(str(span.get("topic") or "")) or document_title
        if _is_outline_like_text(topic):
            topic = document_title
        entry = topics.setdefault(topic, {"title": topic, "spans": []})
        entry["spans"].append(span)
    return list(topics.values())


def _is_useful_section_concept(label: str) -> bool:
    cleaned = _normalize_candidate_phrase(label)
    lowered = cleaned.lower()
    if not is_valid_concept_label(cleaned):
        return False
    if any(lowered.startswith(prefix.strip()) for prefix in BAD_LABEL_PREFIXES):
        return False
    if lowered.startswith(
        ("historical returns", "computing historical returns", "realized returns for")
    ):
        return False
    if lowered.startswith(
        ("returns of individual", "volatility versus excess", "average annual return")
    ):
        return False
    if " problem" in lowered or " solution" in lowered:
        return False
    return True


def build_concept_payloads_from_chunks(
    chunk_rows: List[Dict[str, object]], filename: str, limit: int = 5
) -> List[Dict[str, object]]:
    topic_entries = _build_semantic_topics(chunk_rows, filename)
    candidates: Dict[str, Dict[str, object]] = {}
    slide_heavy = (
        sum(1 for chunk in chunk_rows if chunk.get("page_num") is not None)
        / max(len(chunk_rows), 1)
    ) >= 0.4

    def register_candidate(
        name: str,
        topic_label: str,
        evidence_spans: List[Dict[str, object]],
        base_score: float = 0.0,
    ) -> None:
        normalized_name = _normalize_candidate_phrase(name)
        if not is_valid_concept_label(normalized_name):
            return
        evidence = _best_evidence_sentences(
            evidence_spans, normalized_name, topic_label=topic_label, limit=2
        )
        if not evidence:
            return
        summary = _ensure_terminal_period(evidence[0][0])
        # Each evidence string is its own sentence in the source — but
        # bullet-point text frequently lacks a terminal period, so a
        # naive " ".join produced run-on output like
        #   "...what they do Meta analysis shows..."
        # in the Concept Atlas takeaway field. Adding a period per
        # sentence before joining gives readable prose without
        # altering the underlying evidence semantics.
        description = " ".join(
            _ensure_terminal_period(sentence)
            for sentence, _chunk_id in evidence[:2]
        ).strip()
        if not _is_valid_answer_text(summary, normalized_name):
            return
        chunk_ids = list(dict.fromkeys(chunk_id for _sentence, chunk_id in evidence if chunk_id))
        key = normalized_name.lower()
        score = base_score + len(chunk_ids) * 2.0 + len(summary.split()) / 8
        if any(marker in summary.lower() for marker in CARD_DEFINITION_MARKERS):
            score += 2.5
        payload = {
            "name": normalized_name,
            "description": description[:420],
            "summary": summary,
            "mastery": 0.0,
            "difficulty_label": "Medium",
            "topic": topic_label,
            "supporting_chunk_ids": chunk_ids,
            "_score": score,
        }
        existing = candidates.get(key)
        if existing is None or float(payload["_score"]) > float(existing.get("_score", 0)):
            candidates[key] = payload

    if slide_heavy:
        for chunk in chunk_rows:
            section_label = _normalize_structural_label(str(chunk.get("section") or ""))
            if not _is_useful_section_concept(section_label):
                continue
            chunk_spans = _segment_chunk_for_study(chunk)
            body_spans = [span for span in chunk_spans if span.get("role") == "body"]
            if body_spans:
                register_candidate(section_label, section_label, body_spans, base_score=4.0)

    for topic in topic_entries:
        topic_label = str(topic.get("title") or "Core Ideas")
        spans = list(topic.get("spans") or [])
        body_spans = [span for span in spans if span.get("role") == "body"]
        if not body_spans:
            continue
        normalized_topic = _normalize_candidate_phrase(topic_label)
        topic_evidence = (
            _best_evidence_sentences(body_spans, normalized_topic, topic_label=topic_label, limit=1)
            if normalized_topic
            else []
        )
        if (
            is_valid_concept_label(normalized_topic)
            and (not slide_heavy or _is_useful_section_concept(normalized_topic))
            and (
                len(
                    [token for token in tokenize(normalized_topic) if token not in CONNECTOR_TOKENS]
                )
                >= 2
                or any(
                    normalized_topic.lower() in sentence.lower()
                    for sentence, _chunk_id in topic_evidence
                )
            )
        ):
            register_candidate(normalized_topic, topic_label, body_spans, base_score=2.5)
        for span in body_spans:
            if slide_heavy and candidates:
                break
            for sentence in split_sentences(str(span.get("text") or "")):
                candidate_name = _concept_label_from_sentence(
                    sentence,
                    topic_label=topic_label,
                    allow_subject_fallback=not bool(span.get("slide_like")),
                )
                if candidate_name:
                    register_candidate(candidate_name, topic_label, body_spans, base_score=1.5)

    ordered = sorted(
        candidates.values(),
        key=lambda item: (-float(item.get("_score", 0)), str(item.get("name") or "").lower()),
    )
    for index, item in enumerate(ordered[:limit]):
        item["difficulty_label"] = "Medium" if index < 3 else "Easy"
        item.pop("_score", None)
    return ordered[:limit]
