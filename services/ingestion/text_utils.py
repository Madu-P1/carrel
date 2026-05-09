from __future__ import annotations

import re
from typing import Dict, List, Optional

from .constants import (
    DISPLAY_ACRONYMS,
    INLINE_NOISE_PATTERNS,
    NOISE_LINE_PATTERNS,
    PROMPT_START_TOKENS,
)


def normalize_subject_name(subject_name: Optional[str]) -> str:
    cleaned = (subject_name or "").strip()
    return cleaned or "General"


def canonicalize(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", term.lower())


def tokenize(text: str) -> List[str]:
    return [
        canonicalize(token) for token in re.findall(r"[A-Za-z]{3,}", text) if canonicalize(token)
    ]


def split_sentences(text: str) -> List[str]:
    if not text.strip():
        return []
    normalized_text = str(text or "").replace("▪", ". ").replace("•", ". ").replace("\uf0b7", ". ")
    parts = re.split(r"(?<=[.!?])\s+|\n+", normalized_text.strip())
    sentences: List[str] = []
    for part in parts:
        normalized = re.sub(r"\s+", " ", part).strip()
        if normalized:
            sentences.append(normalized)
    return sentences


def phrase_case(term: str) -> str:
    words = [word for word in re.split(r"\s+", term.strip()) if word]
    formatted: List[str] = []
    for word in words:
        if word.upper() in DISPLAY_ACRONYMS:
            formatted.append(word.upper())
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted)


def strip_inline_noise(text: str) -> str:
    cleaned = str(text or "")
    for pattern in INLINE_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    return cleaned


def _normalize_space(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _normalized_line_key(line: str) -> str:
    lowered = re.sub(r"\d+", "", line.lower())
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _is_noise_line(line: str, repeated_counts: Dict[str, int]) -> bool:
    normalized = _normalized_line_key(line)
    if not normalized:
        return True
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in NOISE_LINE_PATTERNS):
        return True
    if repeated_counts.get(normalized, 0) >= 3 and len(normalized.split()) <= 12:
        return True
    if re.fullmatch(r"[\W\d_]+", line):
        return True
    alpha_count = sum(char.isalpha() for char in line)
    if alpha_count < 3 and len(line) < 24:
        return True
    weird_ratio = sum(
        1 for char in line if not (char.isalnum() or char.isspace() or char in "-_.,;:!?()/&%+")
    ) / max(len(line), 1)
    if weird_ratio > 0.18:
        return True
    return False


def clean_learning_text(text: str) -> str:
    sanitized = re.sub(r"[\x00-\x1F\x7F]", " ", text)
    raw_lines = [line.strip() for line in sanitized.splitlines()]
    repeated_counts: Dict[str, int] = {}
    for line in raw_lines:
        key = _normalized_line_key(line)
        if key:
            repeated_counts[key] = repeated_counts.get(key, 0) + 1

    cleaned_lines: List[str] = []
    for raw_line in raw_lines:
        line = raw_line.replace("•", " ").replace("\uf0b7", " ").replace("|", " ")
        line = strip_inline_noise(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or _is_noise_line(line, repeated_counts):
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if cleaned_lines and cleaned_lines[-1] == line:
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned:
        return cleaned
    return re.sub(r"\s+", " ", text).strip()


def _valid_learning_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", sentence)
    if not words:
        return False
    if canonicalize(words[0]) in PROMPT_START_TOKENS:
        return False
    if "?" in sentence:
        return False
    if len(sentence) > 340:
        return False
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in NOISE_LINE_PATTERNS):
        return False
    alpha_count = sum(char.isalpha() for char in sentence)
    if _is_heading_like_line(sentence):
        return alpha_count >= 12
    return len(sentence) >= 28 and alpha_count >= 20


def _is_heading_like_line(line: str) -> bool:
    words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", line)
    if not 2 <= len(words) <= 6:
        return False
    if any(char in line for char in ".?!:"):
        return False
    if canonicalize(words[0]) in PROMPT_START_TOKENS:
        return False
    titleish = sum(1 for word in words if word.isupper() or word[:1].isupper()) / max(len(words), 1)
    return titleish >= 0.6
