from __future__ import annotations

import re
from typing import Optional

from .utils import normalize_space

PROMPT_START_TOKENS = {
    "describe",
    "define",
    "discuss",
    "explain",
    "identify",
    "list",
    "outline",
    "state",
    "summarize",
}


def is_bullet_like(value: str) -> bool:
    return bool(
        re.match(r"^\s*(?:[•\-\u2022\u2013\u2014]+|\(?\d+\)?[.)]|\d+\.\d+)\s+", str(value or ""))
    )


def strip_bullet_prefix(value: str) -> str:
    return normalize_space(
        re.sub(r"^\s*(?:[•\-\u2022\u2013\u2014]+|\(?\d+\)?[.)]?|\d+\.\d+)\s+", "", str(value or ""))
    )


def is_footer_or_noise(value: str) -> bool:
    text = normalize_space(str(value or ""))
    lowered = text.lower()
    if not text:
        return True
    if any(term in lowered for term in ("copyright", "all rights reserved", "pearson education")):
        return True
    if re.fullmatch(r"[\W\d_]+", text):
        return True
    alpha = sum(char.isalpha() for char in text)
    return alpha < 3 and len(text) < 24


def is_outline_text(value: str, topic_hint: Optional[str] = None) -> bool:
    text = normalize_space(str(value or ""))
    lowered = text.lower()
    topic = str(topic_hint or "").lower()
    if any(
        phrase in lowered
        for phrase in (
            "learning objectives",
            "chapter outline",
            "table of contents",
            "contents",
            "overview",
            "agenda",
        )
    ):
        return True
    if any(
        phrase in topic
        for phrase in (
            "learning objectives",
            "chapter outline",
            "table of contents",
            "contents",
            "overview",
            "agenda",
        )
    ):
        return True
    if re.match(r"^\d+(?:\.\d+)+(?:\s+|:)", text) and len(text.split()) <= 14:
        return True
    return False


def is_formula_text(value: str) -> bool:
    text = normalize_space(str(value or ""))
    alpha = sum(char.isalpha() for char in text)
    digits_or_symbols = sum(char.isdigit() or char in "=+-*/^%()[]{}" for char in text)
    if digits_or_symbols >= max(alpha, 1) and any(
        token in text.lower() for token in ("=", "var", "cov", "beta", "capm", "std")
    ):
        return True
    return bool(re.search(r"\b[a-z]\s*=\s*", text, flags=re.IGNORECASE))


def is_heading_like_text(value: str) -> bool:
    text = normalize_space(str(value or ""))
    if not text:
        return False
    words = text.split()
    if len(words) > 12:
        return False
    lower = text.lower()
    if any(ch in lower for ch in ".!?") and len(words) > 8:
        return False
    capitalized = sum(1 for word in words if word[:1].isupper())
    return capitalized >= max(1, len(words) - 1)


def footer_or_noise_text(value: str) -> bool:
    return is_footer_or_noise(value)


def outline_like_text(value: str, topic_hint: Optional[str] = None) -> bool:
    text = normalize_space(str(value or ""))
    if not text:
        return False
    if is_outline_text(text, topic_hint):
        return True
    first_token = text.split()[0].lower() if text.split() else ""
    return first_token in PROMPT_START_TOKENS and len(text.split()) <= 18


def classify_span_role(
    value: str,
    *,
    kind: str = "paragraph",
    topic_hint: Optional[str] = None,
) -> str:
    text = normalize_space(str(value or ""))
    if not text:
        return "noise"
    if outline_like_text(text, topic_hint):
        return "outline"
    if footer_or_noise_text(text):
        lowered = text.lower()
        if any(
            term in lowered for term in ("copyright", "all rights reserved", "pearson education")
        ):
            return "footer"
        return "noise"
    if kind in {"title", "slide"}:
        return "title"
    if kind == "heading":
        return "heading"
    if is_formula_text(text):
        return "formula"
    if is_heading_like_text(text):
        return "heading"
    return "body"


def classify_pdf_role(
    text: str, *, kind: str = "paragraph", topic_hint: Optional[str] = None
) -> str:
    return classify_span_role(text, kind=kind, topic_hint=topic_hint)
