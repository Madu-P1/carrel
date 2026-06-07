import json
import math
import re
from typing import Any, Dict, List, Optional


def load_messages(raw: Optional[str]) -> List[Dict[str, str]]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def split_sentences(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    raw_sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip() for sentence in raw_sentences if len(sentence.strip()) > 30]


def canonicalize(token: str) -> str:
    token = token.lower()
    if token.endswith("ies") and len(token) > 5:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 5 and not token.endswith(("ss", "is", "us")):
        return token[:-1]
    return token


def tokenize(text: str) -> List[str]:
    return [canonicalize(token) for token in re.findall(r"[A-Za-z]{4,}", text.lower())]


def sentence_for_term(text: str, term: str) -> str:
    sentences = split_sentences(text)
    term_tokens = [canonicalize(token) for token in re.findall(r"[A-Za-z]{4,}", term)]
    if not term_tokens:
        term_tokens = [canonicalize(term)]
    token_set = set(term_tokens)
    best_sentence = ""
    best_score = -1
    for sentence in sentences:
        sentence_tokens = set(tokenize(sentence))
        overlap = len(token_set & sentence_tokens)
        if overlap:
            cleaned = " ".join(sentence.split())
            score = overlap * 10 + min(len(cleaned), 220) / 220
            lowered_sentence = cleaned.lower()
            lowered_term = term.lower()
            if lowered_sentence.startswith(lowered_term):
                score += 8
            elif lowered_term in lowered_sentence:
                score += 4
            if score > best_score:
                best_sentence = cleaned[:280]
                best_score = score
    if best_sentence:
        return best_sentence
    first_sentence = " ".join(text.split())[:280]
    return first_sentence or f"{term} appears repeatedly in the uploaded material."


def concept_positions(concepts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    total = max(len(concepts), 1)
    center_x = 360
    center_y = 200
    radius = 130
    positioned = []
    for index, concept in enumerate(concepts):
        angle = (2 * math.pi * index / total) - math.pi / 2
        concept["x"] = round(center_x + radius * math.cos(angle), 2)
        concept["y"] = round(center_y + radius * math.sin(angle), 2)
        positioned.append(concept)
    return positioned


def concept_takeaway(description: str) -> str:
    sentences = split_sentences(description)
    return sentences[0] if sentences else description[:220]
