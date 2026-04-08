"""Text normalization and keyword helpers."""

from __future__ import annotations

import re
from collections import Counter


WHITESPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^a-z0-9+#]+")


def normalize_text(value: str) -> str:
    """Normalize free text for matching."""

    lowered = value.lower().strip()
    collapsed = WHITESPACE_RE.sub(" ", lowered)
    return collapsed


def tokenise(value: str) -> list[str]:
    """Split text into normalized tokens."""

    normalized = PUNCT_RE.sub(" ", normalize_text(value))
    return [token for token in normalized.split() if token]


def unique_preserve_order(values: list[str]) -> list[str]:
    """Remove duplicates while preserving the first occurrence."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def extract_bullets(text: str) -> list[str]:
    """Extract bullet-like lines or return sentences as a fallback."""

    bullets = [line.lstrip("-* ").strip() for line in text.splitlines() if line.strip().startswith(("-", "*"))]
    if bullets:
        return bullets
    sentences = [segment.strip() for segment in re.split(r"[.\n]+", text) if len(segment.strip()) > 20]
    return sentences


def phrase_in_text(phrase: str, text: str) -> bool:
    """Check phrase presence after normalization."""

    return normalize_text(phrase) in normalize_text(text)


def collect_phrase_matches(text: str, phrases: list[str]) -> list[str]:
    """Return phrases present in text."""

    normalized_text = normalize_text(text)
    return [phrase for phrase in phrases if normalize_text(phrase) in normalized_text]


def keyword_overlap_score(left: list[str], right: list[str]) -> float:
    """Simple 0-100 token overlap score."""

    left_set = {normalize_text(item) for item in left if item}
    right_set = {normalize_text(item) for item in right if item}
    if not left_set or not right_set:
        return 0.0
    overlap = left_set & right_set
    return round(100.0 * len(overlap) / len(left_set | right_set), 2)


def jaccard_similarity(left: str, right: str) -> float:
    """Token-level Jaccard similarity for dedupe."""

    left_tokens = set(tokenise(left))
    right_tokens = set(tokenise(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def most_common_terms(text: str, stop_words: set[str] | None = None, top_n: int = 15) -> list[str]:
    """Return frequently repeated content words from text."""

    ignored = stop_words or {
        "and",
        "the",
        "with",
        "for",
        "from",
        "that",
        "this",
        "have",
        "into",
        "across",
        "using",
        "built",
        "developed",
        "worked",
        "led",
    }
    tokens = [token for token in tokenise(text) if len(token) > 2 and token not in ignored]
    counts = Counter(tokens)
    return [token for token, _ in counts.most_common(top_n)]
