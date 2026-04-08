"""Query expansion helpers."""

from __future__ import annotations

from job_searcher.models import DOMAIN_SYNONYMS, ROLE_FAMILY_SYNONYMS
from job_searcher.utils.text import normalize_text, unique_preserve_order


GERMAN_TITLE_MAP = {
    "engineer": "ingenieur",
    "research engineer": "forschungsingenieur",
    "computer vision": "computer vision",
    "perception": "perception",
    "mapping": "mapping",
    "localization": "lokalisierung",
}


def expand_role_titles(titles: list[str], role_families: list[str]) -> list[str]:
    """Expand user-facing titles into adjacent role variants."""

    expanded = list(titles)
    normalized_titles = " ".join(normalize_text(title) for title in titles)

    for family_key, variants in ROLE_FAMILY_SYNONYMS.items():
        family_label = family_key.replace("_", " ")
        if family_label in " ".join(role_families).lower() or any(variant in normalized_titles for variant in variants):
            expanded.extend(variants)
    return unique_preserve_order(expanded)


def expand_domain_terms(domains: list[str], include_keywords: list[str]) -> list[str]:
    """Expand domain terms into close search phrases."""

    expanded = list(domains) + list(include_keywords)
    normalized = [normalize_text(item) for item in expanded]
    for domain, related in DOMAIN_SYNONYMS.items():
        if normalize_text(domain) in normalized or any(normalize_text(term) in normalized for term in related):
            expanded.append(domain)
            expanded.extend(related)
    return unique_preserve_order(expanded)


def german_variants(title: str) -> list[str]:
    """Generate a small set of German-market title variants."""

    variants = [title]
    lowered = title.lower()
    for source, target in GERMAN_TITLE_MAP.items():
        if source in lowered:
            variants.append(lowered.replace(source, target))
    return unique_preserve_order(variants)
