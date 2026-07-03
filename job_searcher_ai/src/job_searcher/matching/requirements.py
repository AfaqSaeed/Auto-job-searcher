"""Requirement extraction for explainable matching."""

from __future__ import annotations

import re

from job_searcher.llm.ollama_client import OllamaClient, OllamaClientError
from job_searcher.llm.prompts import REQUIREMENT_EXTRACTION_SYSTEM, build_requirement_extraction_prompt
from job_searcher.schemas import JobListing
from job_searcher.utils.text import extract_bullets, normalize_text, unique_preserve_order


MAX_REQUIREMENTS = 15
MAX_REQUIREMENT_CHARS = 180
VAGUE_REQUIREMENT_TERMS = {
    "communication",
    "communicate",
    "team player",
    "collaboration",
    "collaborative",
    "self-starter",
    "fast-paced",
    "passion",
}
EMPHASIS_TERMS = {
    "required",
    "must",
    "essential",
    "excellent",
    "strong",
    "demonstrated",
    "proven",
    "responsible for",
}


def extract_requirements(job: JobListing, client: OllamaClient | None) -> list[str]:
    """Extract concise, deduplicated requirements from a job listing."""

    llm_requirements = _extract_with_llm(job, client) if client is not None else []
    deterministic = _extract_deterministic(job)
    return _normalize_requirements(deterministic + llm_requirements, job.description, MAX_REQUIREMENTS)


def _extract_with_llm(job: JobListing, client: OllamaClient | None) -> list[str]:
    if client is None:
        return []
    try:
        payload = client.generate_json(
            build_requirement_extraction_prompt(job, max_requirements=MAX_REQUIREMENTS),
            system=REQUIREMENT_EXTRACTION_SYSTEM,
        )
    except (OllamaClientError, ValueError, TypeError):
        return []

    raw_requirements = payload.get("requirements", [])
    if isinstance(raw_requirements, str):
        return [raw_requirements]
    if not isinstance(raw_requirements, list):
        return []
    return [str(item).strip() for item in raw_requirements if str(item).strip()]


def _extract_deterministic(job: JobListing) -> list[str]:
    candidates: list[str] = []
    candidates.extend(job.required_skills)
    candidates.extend(job.minimum_qualifications)
    candidates.extend(job.preferred_skills)
    candidates.extend(job.responsibilities)
    candidates.extend(_description_requirements(job.description))
    candidates.extend(f"Experience with {signal}" for signal in job.domain_signals)
    return candidates


def _description_requirements(description: str) -> list[str]:
    if not description.strip():
        return []

    lines = extract_bullets(description)
    if not lines:
        lines = [segment.strip() for segment in re.split(r"(?<=[.;])\s+|\n+", description) if segment.strip()]

    selected: list[str] = []
    requirement_markers = (
        "require",
        "qualification",
        "experience",
        "proficiency",
        "responsible",
        "build",
        "develop",
        "design",
        "implement",
        "maintain",
        "knowledge",
        "familiar",
        "must",
        "preferred",
        "nice to have",
    )
    for line in lines:
        cleaned = _clean_requirement(line)
        lowered = normalize_text(cleaned)
        if not cleaned or len(cleaned) < 4:
            continue
        if any(marker in lowered for marker in requirement_markers):
            selected.append(cleaned)
    return selected


def _normalize_requirements(requirements: list[str], description: str, limit: int) -> list[str]:
    normalized: list[str] = []
    for requirement in requirements:
        cleaned = _clean_requirement(requirement)
        if not cleaned:
            continue
        if _is_noise_requirement(cleaned, description):
            continue
        if _is_vague_requirement(cleaned, description):
            continue
        normalized.append(cleaned)
    return unique_preserve_order(normalized)[:limit]


def _clean_requirement(requirement: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", requirement)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -*\t\r\n:.;")
    cleaned = re.sub(r"^(requirements?|responsibilities|qualifications?|preferred|nice to have)\s*[:\-]\s*", "", cleaned, flags=re.I)
    if len(cleaned) > MAX_REQUIREMENT_CHARS:
        cleaned = cleaned[:MAX_REQUIREMENT_CHARS].rsplit(" ", 1)[0].rstrip(",;:")
    return cleaned


def _is_vague_requirement(requirement: str, description: str) -> bool:
    lowered = normalize_text(requirement)
    if not any(term in lowered for term in VAGUE_REQUIREMENT_TERMS):
        return False
    if any(term in lowered for term in EMPHASIS_TERMS):
        return False
    description_lowered = normalize_text(description)
    emphasized_patterns = [
        f"{emphasis} {term}"
        for emphasis in EMPHASIS_TERMS
        for term in VAGUE_REQUIREMENT_TERMS
    ]
    return not any(pattern in description_lowered for pattern in emphasized_patterns)


def _is_noise_requirement(requirement: str, description: str) -> bool:
    if len(requirement) > 1:
        return False
    if requirement.lower() != "c":
        return True
    return re.search(r"(?<![A-Za-z])C(?:\s*(?:/|\+\+)|\s+programming|\s+language|[,\.;:]|$)", description) is None
