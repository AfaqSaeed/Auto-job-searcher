"""Search-query deduplication helpers."""

from __future__ import annotations

from job_searcher.schemas import SearchQuery
from job_searcher.utils.text import jaccard_similarity, normalize_text


def dedupe_queries(queries: list[SearchQuery], threshold: float = 0.82) -> list[SearchQuery]:
    """Remove near-duplicate queries while preserving early high-value items."""

    unique: list[SearchQuery] = []
    seen_exact: set[str] = set()
    for query in queries:
        exact_key = normalize_text(query.text)
        if exact_key in seen_exact:
            continue
        if any(jaccard_similarity(query.text, existing.text) >= threshold for existing in unique):
            continue
        seen_exact.add(exact_key)
        unique.append(query)
    return unique
