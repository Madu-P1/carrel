from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from .concept_candidates import (
    clean_candidate_label,
    compute_token_counts,
    select_concept_phrases,
    supporting_sentences,
)
from .text_utils import (
    _valid_learning_sentence,
    canonicalize,
    clean_learning_text,
    split_sentences,
    strip_inline_noise,
    tokenize,
)


def chunk_text(text: str, chunk_size: int = 1200) -> List[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) <= chunk_size:
                current = paragraph
            else:
                sentences = split_sentences(paragraph)
                sentence_bucket = ""
                for sentence in sentences:
                    if len(sentence_bucket) + len(sentence) + 1 <= chunk_size:
                        sentence_bucket = f"{sentence_bucket} {sentence}".strip()
                    else:
                        if sentence_bucket:
                            chunks.append(sentence_bucket)
                        sentence_bucket = sentence
                current = sentence_bucket
    if current:
        chunks.append(current)
    return chunks or [text.strip()]


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
                best_sentence = strip_inline_noise(cleaned[:280])
                best_score = score
    if best_sentence:
        return best_sentence
    return strip_inline_noise(" ".join(text.split())[:280])


def initial_mastery() -> float:
    return 0.0


def concept_description(term: str, text: str) -> str:
    support = supporting_sentences(text, term, limit=2)
    context = support[0] if support else sentence_for_term(text, term)
    if not context:
        return ""
    if context.lower().startswith(term.lower()):
        return context
    if len(context) > 1:
        return f"{term} is important because {context[0].lower() + context[1:]}"
    return f"{term} is important because {context.lower()}"


def summarize_document(text: str, max_sentences: int = 3) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return "This document was uploaded successfully."
    token_counts = compute_token_counts(text)
    scored = []
    for sentence in sentences:
        if not _valid_learning_sentence(sentence):
            continue
        score = sum(token_counts.get(token, 0) for token in tokenize(sentence))
        if any(
            marker in sentence.lower()
            for marker in (" is ", " are ", " uses ", " converts ", " causes ")
        ):
            score += 2
        scored.append((score, sentence))
    top = [
        sentence
        for _score, sentence in sorted(scored, key=lambda item: (-item[0], len(item[1])))[
            :max_sentences
        ]
    ]
    summary = " ".join(
        strip_inline_noise(sentence) for sentence in top if strip_inline_noise(sentence)
    )
    return summary or "This document was uploaded successfully."


def build_concept_payloads(text: str, filename: str, limit: int = 5) -> List[Dict[str, object]]:
    from .topics import build_concept_payloads_from_chunks

    cleaned_text = clean_learning_text(text)
    chunk_rows = [
        {
            "id": f"manual-chunk-{index}",
            "content": chunk,
            "section": clean_candidate_label(
                Path(filename).stem.replace("-", " ").replace("_", " ")
            )
            or "Core Ideas",
            "page_num": None,
            "chunk_index": index,
        }
        for index, chunk in enumerate(chunk_text(cleaned_text), start=1)
        if str(chunk or "").strip()
    ]
    return build_concept_payloads_from_chunks(chunk_rows, filename, limit=limit)


def find_related_concept_name(concepts: List[Dict[str, object]], current_name: str) -> str:
    current_tokens = set(tokenize(current_name))
    current_mastery = next(item["mastery"] for item in concepts if item["name"] == current_name)
    best_name = current_name
    best_score = -1
    for concept in concepts:
        if concept["name"] == current_name:
            continue
        overlap = len(current_tokens & set(tokenize(concept["name"])))
        score = overlap - abs(concept["mastery"] - current_mastery)
        if score > best_score:
            best_score = score
            best_name = concept["name"]
    return best_name
