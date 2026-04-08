"""Normalization helpers for job listings."""

from __future__ import annotations

import re

from job_searcher.models import DOMAIN_SYNONYMS, INDUSTRY_SYNONYMS, SKILL_CATEGORIES
from job_searcher.schemas import JobListing, SalaryRange, WorkMode
from job_searcher.utils.text import collect_phrase_matches, unique_preserve_order


SALARY_RE = re.compile(
    r"(?P<currency>[$EURGBP€£])\s?(?P<min>\d[\d,\.]+)(?:\s?[-–to]+\s?(?P<max>\d[\d,\.]+))?",
    re.IGNORECASE,
)


def parse_salary_range(text: str) -> SalaryRange | None:
    """Extract a best-effort salary range from free text."""

    match = SALARY_RE.search(text)
    if not match:
        return None
    currency = match.group("currency")
    minimum = float(match.group("min").replace(",", ""))
    maximum_raw = match.group("max")
    maximum = float(maximum_raw.replace(",", "")) if maximum_raw else None
    normalized_currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(currency, currency)
    return SalaryRange(currency=normalized_currency, minimum=minimum, maximum=maximum, interval="year")


def infer_work_mode(*texts: str) -> WorkMode:
    """Infer work mode from free text and location fields."""

    combined = " ".join(texts).lower()
    if "hybrid" in combined:
        return WorkMode.HYBRID
    if "remote" in combined or "work from home" in combined:
        return WorkMode.REMOTE
    if "on-site" in combined or "onsite" in combined or "office" in combined:
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def extract_skill_mentions(text: str) -> list[str]:
    """Extract skills from job text using known taxonomies."""

    phrases: list[str] = []
    for category_terms in SKILL_CATEGORIES.values():
        phrases.extend(category_terms)
    return unique_preserve_order(collect_phrase_matches(text, phrases))


def extract_domain_signals(text: str) -> list[str]:
    """Extract domain and industry cues from job text."""

    matches: list[str] = []
    normalized = text.lower()
    for domain, related in DOMAIN_SYNONYMS.items():
        if domain in normalized or any(term in normalized for term in related):
            matches.append(domain)
    for industry, related in INDUSTRY_SYNONYMS.items():
        if industry in normalized or any(term in normalized for term in related):
            matches.append(industry)
    return unique_preserve_order(matches)


def extract_language_requirements(text: str) -> list[str]:
    """Pull out explicit language requirements when present."""

    requirements: list[str] = []
    lowered = text.lower()
    for language in ["english", "german", "french", "spanish"]:
        if language in lowered:
            requirements.append(language)
    return unique_preserve_order(requirements)


def normalize_job_listing(job: JobListing) -> JobListing:
    """Normalize common fields across sources."""

    updated = job.model_copy(deep=True)
    updated.required_skills = unique_preserve_order(updated.required_skills)
    updated.preferred_skills = unique_preserve_order(updated.preferred_skills)
    updated.responsibilities = unique_preserve_order(updated.responsibilities)
    updated.minimum_qualifications = unique_preserve_order(updated.minimum_qualifications)
    updated.domain_signals = unique_preserve_order(updated.domain_signals)
    updated.language_requirements = unique_preserve_order(updated.language_requirements)
    if updated.salary is None:
        updated.salary = parse_salary_range(updated.description)
    if updated.work_mode == WorkMode.UNKNOWN:
        updated.work_mode = infer_work_mode(updated.location or "", updated.description)
    return updated
