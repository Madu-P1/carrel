from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .constants import (
    BAD_LABEL_PREFIXES,
    BOUNDARY_WORDS,
    COMMON_VERBS,
    CONNECTOR_TOKENS,
    DEFINITION_MARKERS,
    DISPLAY_ACRONYMS,
    GENERIC_TERMS,
    NOISE_TOKENS,
    OUTLINE_HINT_PATTERNS,
    PROMPT_START_TOKENS,
    STOPWORDS,
)
from .text_utils import (
    _is_heading_like_line,
    _valid_learning_sentence,
    canonicalize,
    clean_learning_text,
    phrase_case,
    split_sentences,
    tokenize,
)


def supporting_sentences(text: str, term: str, limit: int = 3) -> List[str]:
    term_tokens = set(tokenize(term))
    if not term_tokens:
        return []
    ranked: List[Tuple[float, str]] = []
    for sentence in split_sentences(text):
        if not _valid_learning_sentence(sentence):
            continue
        sentence_tokens = set(tokenize(sentence))
        overlap = len(term_tokens & sentence_tokens)
        if not overlap:
            continue
        score = overlap * 4
        lowered = sentence.lower()
        if any(marker in lowered for marker in DEFINITION_MARKERS):
            score += 2
        ranked.append((score, " ".join(sentence.split())[:320]))
    ranked.sort(key=lambda item: (-item[0], len(item[1])))

    selected: List[str] = []
    seen = set()
    for _score, sentence in ranked:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        selected.append(sentence)
        if len(selected) == limit:
            break
    return selected


def clean_candidate_label(value: str) -> str:
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(value or ""))
    cleaned = re.sub(r"^\d+(?:\.\d+)+(?:\s*[:.-]?\s*)", "", cleaned)
    cleaned = re.sub(r"\(\d+\s+of\s+\d+\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[_/\\-]+", " ", cleaned)
    cleaned = re.sub(r"[^A-Za-z0-9\s]+", " ", cleaned)
    cleaned = re.sub(r"(\d)([A-Za-z])", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])(\d)", r"\1 \2", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-_")
    parts = []
    for word in cleaned.split():
        if not parts or parts[-1].lower() != word.lower():
            parts.append(word)
    return phrase_case(" ".join(parts))


def is_valid_concept_label(candidate: str) -> bool:
    cleaned = clean_candidate_label(candidate)
    if not cleaned or re.search(r"\d", cleaned):
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix) for prefix in BAD_LABEL_PREFIXES):
        return False
    words = cleaned.split()
    tokens = [canonicalize(word) for word in words if canonicalize(word)]
    lexical_tokens = [token for token in tokens if token not in CONNECTOR_TOKENS]
    connector_count = sum(1 for token in tokens if token in CONNECTOR_TOKENS)
    if not lexical_tokens:
        return False
    if len(words) > 4:
        return False
    if len(lexical_tokens) > 5:
        return False
    if (
        tokens[0] in PROMPT_START_TOKENS
        or tokens[0] in CONNECTOR_TOKENS
        or tokens[0] in STOPWORDS
        or tokens[0] in COMMON_VERBS
    ):
        return False
    if connector_count > 1:
        return False
    if len(lexical_tokens) == 1:
        first_word = words[0] if words else ""
        if len(lexical_tokens[0]) < 4 and first_word.upper() not in DISPLAY_ACRONYMS:
            return False
    short_words = [
        word for word in words if len(word) <= 2 and word.upper() not in DISPLAY_ACRONYMS
    ]
    if short_words:
        return False
    if any(token.endswith("ing") and len(token) > 5 for token in lexical_tokens):
        return False
    if any(
        token in NOISE_TOKENS or any(noise in token for noise in NOISE_TOKENS if len(noise) >= 5)
        for token in tokens
    ):
        return False
    if (
        tokens[-1] in STOPWORDS
        or tokens[-1] in BOUNDARY_WORDS
        or tokens[-1] in COMMON_VERBS
        or tokens[-1] in CONNECTOR_TOKENS
    ):
        return False
    if all(
        token in STOPWORDS or token in GENERIC_TERMS or token in CONNECTOR_TOKENS
        for token in tokens
    ):
        return False
    if lowered in {"study concept", "core idea", "core ideas", "key process", "key relationship"}:
        return False
    if connector_count and lowered.endswith((" cost", " profit", " payoff")):
        return False
    if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in OUTLINE_HINT_PATTERNS):
        return False
    return True


def leading_subject_phrase(sentence: str) -> Optional[str]:
    words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", sentence)
    if not words:
        return None
    normalized = [canonicalize(word.replace("-", "")) for word in words]
    verb_index = next(
        (index for index, token in enumerate(normalized) if token in COMMON_VERBS), None
    )
    if verb_index is None or verb_index > 5:
        return None
    subject_words = words[:verb_index]
    while subject_words and canonicalize(subject_words[0].replace("-", "")) in {"the", "a", "an"}:
        subject_words.pop(0)
    if not subject_words:
        return None
    filtered = []
    for word in subject_words[:4]:
        base = canonicalize(word.replace("-", ""))
        if base in STOPWORDS or base in GENERIC_TERMS or base in NOISE_TOKENS:
            continue
        filtered.append(word)
    if not filtered:
        return None
    candidate = clean_candidate_label(" ".join(filtered))
    return candidate if is_valid_concept_label(candidate) else None


def build_phrase_candidates(sentence: str, token_counts: Dict[str, int]) -> Dict[str, float]:
    words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", sentence)
    normalized = [canonicalize(word.replace("-", "")) for word in words]
    candidates: Dict[str, float] = {}

    def add_candidate(raw_tokens: List[str], bonus: float = 0.0) -> None:
        phrase_tokens: List[str] = []
        for token in raw_tokens:
            for part in token.split("-"):
                normalized_part = canonicalize(part)
                if (
                    normalized_part
                    and normalized_part not in STOPWORDS
                    and normalized_part not in GENERIC_TERMS
                    and normalized_part not in NOISE_TOKENS
                ):
                    phrase_tokens.append(normalized_part)
        if not phrase_tokens or any(token in COMMON_VERBS for token in phrase_tokens):
            return
        phrase = clean_candidate_label(" ".join(phrase_tokens[:3]))
        if not is_valid_concept_label(phrase):
            return
        score = sum(token_counts.get(token, 0) for token in phrase_tokens) + bonus
        candidates[phrase] = max(candidates.get(phrase, 0), score)

    verb_index = next(
        (index for index, token in enumerate(normalized) if token in COMMON_VERBS), None
    )
    if verb_index is not None:
        subject = [word for word in words[:verb_index] if canonicalize(word) not in STOPWORDS]
        if subject:
            add_candidate(subject[-3:], bonus=3.0)

        object_tokens: List[str] = []
        for word in words[verb_index + 1 :]:
            lowered = canonicalize(word)
            if lowered in STOPWORDS or lowered in COMMON_VERBS or lowered in NOISE_TOKENS:
                if object_tokens:
                    break
                continue
            if lowered in BOUNDARY_WORDS and object_tokens:
                break
            object_tokens.append(word)
            if len(object_tokens) == 3:
                break
        if object_tokens:
            add_candidate(object_tokens, bonus=2.0)

    title_like: List[str] = []
    for word in words:
        if word.isupper() or word[:1].isupper():
            title_like.append(word)
        elif title_like:
            break
    if title_like:
        add_candidate(title_like, bonus=2.5)

    for pair_size in (3, 2):
        for start in range(len(normalized) - pair_size + 1):
            raw = words[start : start + pair_size]
            if any(canonicalize(token) in COMMON_VERBS for token in raw):
                continue
            add_candidate(raw, bonus=0.4 * pair_size)
    return candidates


def heading_candidates(text: str, token_counts: Dict[str, int]) -> Dict[str, float]:
    candidates: Dict[str, float] = {}
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line or not _is_heading_like_line(line):
            continue
        phrase = clean_candidate_label(line)
        if not is_valid_concept_label(phrase):
            continue
        score = 10.0 + sum(token_counts.get(token, 0) for token in tokenize(phrase))
        candidates[phrase] = max(candidates.get(phrase, 0.0), score)
    return candidates


def compute_token_counts(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for token in tokenize(text):
        if token in STOPWORDS or len(token) < 4:
            continue
        counts[token] = counts.get(token, 0) + 1
    return counts


def select_concept_phrases(text: str, filename: str, limit: int = 5) -> List[str]:
    cleaned_text = clean_learning_text(text)
    token_counts = compute_token_counts(cleaned_text)
    phrase_scores: Dict[str, float] = {}
    heading_scores = heading_candidates(cleaned_text, token_counts)

    for phrase, score in heading_scores.items():
        phrase_scores[phrase] = phrase_scores.get(phrase, 0.0) + score

    for sentence in split_sentences(cleaned_text):
        if not _valid_learning_sentence(sentence):
            continue
        subject = leading_subject_phrase(sentence)
        if subject:
            phrase_scores[subject] = phrase_scores.get(subject, 0.0) + 4.0
        for phrase, score in build_phrase_candidates(sentence, token_counts).items():
            support_count = len(supporting_sentences(cleaned_text, phrase, limit=2))
            lowered = sentence.lower()
            phrase_scores[phrase] = phrase_scores.get(phrase, 0.0) + score + support_count * 2.0
            if any(marker in lowered for marker in DEFINITION_MARKERS):
                phrase_scores[phrase] += 1.5

    stem = clean_candidate_label(Path(filename).stem.replace("-", " ").replace("_", " "))
    if is_valid_concept_label(stem) and supporting_sentences(cleaned_text, stem, limit=1):
        phrase_scores[stem] = phrase_scores.get(stem, 0.0) + 1.2

    ranked = sorted(
        phrase_scores.items(), key=lambda item: (-item[1], -len(item[0]), item[0].lower())
    )
    selected: List[str] = []
    selected_token_sets: List[set[str]] = []

    def maybe_add(candidate: str) -> None:
        cleaned = clean_candidate_label(candidate)
        tokens = set(tokenize(cleaned))
        if not tokens or not is_valid_concept_label(cleaned):
            return
        if len(supporting_sentences(cleaned_text, cleaned, limit=1)) == 0:
            return
        if any(
            len(tokens & existing) / max(len(tokens | existing), 1) >= 0.6
            for existing in selected_token_sets
        ):
            return
        selected.append(cleaned)
        selected_token_sets.append(tokens)

    for candidate, _score in sorted(
        heading_scores.items(), key=lambda item: (-item[1], -len(item[0]), item[0].lower())
    ):
        maybe_add(candidate)
        if len(selected) == limit:
            break

    for candidate, _score in ranked:
        maybe_add(candidate)
        if len(selected) == limit:
            break

    if not selected:
        fallback = [
            clean_candidate_label(term)
            for term, _count in sorted(token_counts.items(), key=lambda item: (-item[1], item[0]))
            if term not in COMMON_VERBS and term not in GENERIC_TERMS and term not in NOISE_TOKENS
        ]
        for term in fallback:
            maybe_add(term)
            if len(selected) == limit:
                break

    return selected[:limit]


def extract_terms(text: str, filename: str, limit: int = 5) -> List[str]:
    return select_concept_phrases(text, filename, limit=limit)
