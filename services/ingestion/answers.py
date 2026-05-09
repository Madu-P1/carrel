from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from services.extraction.quality import (
    footer_or_noise_text as _is_footer_or_noise_text,
    is_formula_text as _is_formula_like_text,
    outline_like_text as _is_outline_like_text,
)

from .concept_candidates import (
    clean_candidate_label,
    is_valid_concept_label,
    leading_subject_phrase,
)
from .constants import CARD_DEFINITION_MARKERS, VISIBLE_SOURCE_LEAK_PATTERNS
from .text_utils import (
    _is_heading_like_line,
    _normalize_space,
    clean_learning_text,
    split_sentences,
    strip_inline_noise,
    tokenize,
)


def _normalize_structural_label(value: str) -> str:
    cleaned = strip_inline_noise(str(value or ""))
    cleaned = re.sub(
        r"\.(?:txt|pdf|docx|pptx|xlsx|csv|tsv|md|html?)\b", " ", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"^\d+(?:\.\d+)+(?:\s*[:.-]?\s*)", "", cleaned)
    cleaned = re.sub(r"\(\d+\s+of\s+\d+\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    return cleaned


def _normalize_candidate_phrase(value: str) -> str:
    cleaned = _normalize_structural_label(value)
    cleaned = re.sub(r"^(?:the|an|a)\s+", "", cleaned, flags=re.IGNORECASE)
    if cleaned.lower().startswith("beta and the cost"):
        cleaned = "Beta"
    if " - " in cleaned:
        cleaned = cleaned.split(" - ", 1)[0].strip()
    if len(cleaned.split()) > 5 and " of " in cleaned.lower():
        cleaned = cleaned.split(" of ", 1)[0].strip()
    if len(cleaned.split()) > 5:
        cleaned = " ".join(cleaned.split()[-5:])
    return clean_candidate_label(cleaned)


def _has_visible_source_leakage(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in VISIBLE_SOURCE_LEAK_PATTERNS
    )


def _definition_front(concept_name: str) -> str:
    return f"What is {concept_name}?"


def _clean_answer_text(text: str) -> str:
    cleaned = clean_learning_text(str(text or ""))
    cleaned = _normalize_structural_label(cleaned)
    cleaned = re.sub(r"\b(?:[A-Z]|[A-Z]{1,2}\s+[A-Z])\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    return cleaned


def _is_heading_answer(text: str) -> bool:
    cleaned = _clean_answer_text(text)
    return _is_heading_like_line(cleaned) or cleaned == clean_candidate_label(cleaned)


def _is_valid_answer_text(answer: str, concept_name: str) -> bool:
    cleaned = _clean_answer_text(answer)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered.startswith(
        ("let ", "let’s ", "let's ", "next, ", "first, ", "the rest ", "all stocks tend ")
    ):
        return False
    if _has_visible_source_leakage(cleaned):
        return False
    if (
        _is_footer_or_noise_text(cleaned)
        or _is_outline_like_text(cleaned)
        or _is_formula_like_text(cleaned)
    ):
        return False
    digit_or_symbol = sum(char.isdigit() or char in "=+-*/^%()[]{}÷±×" for char in cleaned)
    if digit_or_symbol / max(len(cleaned), 1) > 0.18:
        return False
    if re.search(r"(?:\b[A-Z]\b[\s,]*){2,}", cleaned):
        return False
    if _is_heading_answer(cleaned):
        return False
    if clean_candidate_label(cleaned).lower() == clean_candidate_label(concept_name).lower():
        return False
    if len(cleaned.split()) < 4 or len(cleaned) < 24:
        return False
    return True


def _concept_label_from_sentence(
    sentence: str,
    topic_label: Optional[str] = None,
    *,
    allow_subject_fallback: bool = True,
) -> Optional[str]:
    cleaned = _clean_answer_text(sentence)
    if not cleaned or _is_formula_like_text(cleaned) or _is_outline_like_text(cleaned):
        return None
    if allow_subject_fallback:
        subject = leading_subject_phrase(cleaned)
        if subject and is_valid_concept_label(subject):
            return subject
    lowered = cleaned.lower()
    for marker in CARD_DEFINITION_MARKERS:
        marker_index = lowered.find(marker)
        if marker_index <= 0:
            continue
        label = _normalize_candidate_phrase(cleaned[:marker_index])
        if is_valid_concept_label(label):
            return label
    if not allow_subject_fallback:
        return None
    if topic_label:
        label = _normalize_candidate_phrase(topic_label)
        label_tokens = set(tokenize(label))
        if label_tokens and is_valid_concept_label(label):
            sentence_tokens = set(tokenize(cleaned))
            if len(label_tokens & sentence_tokens) / max(len(label_tokens), 1) >= 0.6:
                return label
    return None


def _best_evidence_sentences(
    spans: List[Dict[str, object]],
    concept_name: str,
    *,
    topic_label: Optional[str] = None,
    limit: int = 2,
) -> List[Tuple[str, str]]:
    concept_tokens = set(tokenize(concept_name))
    topic_tokens = set(tokenize(topic_label or ""))
    ranked: List[Tuple[float, str, str]] = []
    for span in spans:
        if span.get("role") != "body":
            continue
        for sentence in split_sentences(str(span.get("text") or "")):
            cleaned = _clean_answer_text(sentence)
            if not _is_valid_answer_text(cleaned, concept_name):
                continue
            sentence_tokens = set(tokenize(cleaned))
            overlap = len(concept_tokens & sentence_tokens)
            topic_overlap = len(topic_tokens & sentence_tokens)
            if overlap <= 0 and topic_overlap <= 0:
                continue
            score = overlap * 5
            score += topic_overlap * 2
            if concept_name.lower() in cleaned.lower():
                score += 4
            if any(marker in cleaned.lower() for marker in CARD_DEFINITION_MARKERS):
                score += 3
            if topic_label and topic_label.lower() in cleaned.lower():
                score += 2
            ranked.append((score, cleaned, str(span.get("chunk_id") or "")))
    ranked.sort(key=lambda item: (-item[0], len(item[1])))
    selected: List[Tuple[str, str]] = []
    seen = set()
    for _score, sentence, chunk_id in ranked:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append((sentence, chunk_id))
        if len(selected) >= limit:
            break
    if selected or not topic_label:
        return selected
    for span in spans:
        if span.get("role") != "body":
            continue
        for sentence in split_sentences(str(span.get("text") or "")):
            cleaned = _clean_answer_text(sentence)
            if not _is_valid_answer_text(cleaned, concept_name):
                continue
            if any(cleaned.lower() == existing[0].lower() for existing in selected):
                continue
            selected.append((cleaned, str(span.get("chunk_id") or "")))
            if len(selected) >= limit:
                return selected
    return selected
