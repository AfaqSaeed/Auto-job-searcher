"""Candidate evidence construction and retrieval."""

from __future__ import annotations

import re

from job_searcher.matching.schemas import EvidenceItem
from job_searcher.profile.ingest import split_markdown_sections
from job_searcher.ranking.embeddings import EmbeddingBackend
from job_searcher.schemas import DocumentSection, UserProfile
from job_searcher.utils.text import extract_bullets, normalize_text, unique_preserve_order


MAX_CHUNK_CHARS = 520


def build_candidate_evidence(profile: UserProfile, raw_profile_text: str | None = None) -> list[EvidenceItem]:
    """Build compact evidence chunks from a structured profile and optional raw text."""

    candidates: list[tuple[str, str]] = []
    if profile.summary:
        candidates.extend(_chunk_text(profile.summary, "summary"))
    if profile.llm_summary and profile.llm_summary != profile.summary:
        candidates.extend(_chunk_text(profile.llm_summary, "summary"))

    skills = unique_preserve_order(
        [skill.name for skill in profile.skills]
        + profile.tools
        + profile.programming_languages
        + profile.research_topics
    )
    candidates.extend(_chunk_group("Skills", skills, "skills"))
    candidates.extend(_chunk_group("Domain strengths", profile.domain_strengths, "domains"))
    candidates.extend(_chunk_group("Role families", profile.role_families, "roles"))

    for experience in profile.work_experience:
        heading = " | ".join(part for part in [experience.title, experience.company] if part)
        text = "\n".join([heading, *experience.highlights, *experience.technologies, *experience.domains]).strip()
        candidates.extend(_chunk_text(text, "work_history"))

    for project in profile.projects:
        text = "\n".join(
            [
                project.name,
                project.description,
                *project.highlights,
                *project.technologies,
                *project.domains,
            ]
        ).strip()
        candidates.extend(_chunk_text(text, "projects"))

    for education in profile.education:
        text = "\n".join(
            [
                " | ".join(part for part in [education.degree, education.institution, education.date_range] if part),
                *education.notes,
            ]
        ).strip()
        candidates.extend(_chunk_text(text, "education"))

    for section in profile.sections:
        candidates.extend(_chunk_text(section.content, _section_label(section)))

    if raw_profile_text:
        for section in split_markdown_sections(raw_profile_text):
            candidates.extend(_chunk_text(section.content, _section_label(section)))

    return _dedupe_evidence(candidates)


def retrieve_evidence(
    requirement: str,
    evidence_items: list[EvidenceItem],
    backend: EmbeddingBackend,
    top_k: int = 3,
) -> list[EvidenceItem]:
    """Return the top evidence chunks for a requirement using the configured backend."""

    if top_k <= 0 or not requirement.strip() or not evidence_items:
        return []

    scored: list[EvidenceItem] = []
    for item in evidence_items:
        similarity = _clamp_similarity(backend.similarity(requirement, item.text))
        scored.append(
            EvidenceItem(
                text=item.text,
                source_section=item.source_section,
                similarity=similarity,
            )
        )
    scored.sort(key=lambda item: item.similarity, reverse=True)
    return scored[:top_k]


def _chunk_group(label: str, values: list[str], source_section: str) -> list[tuple[str, str]]:
    cleaned = unique_preserve_order([value for value in values if value and value.strip()])
    if not cleaned:
        return []
    chunks: list[tuple[str, str]] = []
    current: list[str] = []
    for value in cleaned:
        candidate = ", ".join([*current, value])
        if len(candidate) > MAX_CHUNK_CHARS and current:
            chunks.append((f"{label}: {', '.join(current)}", source_section))
            current = [value]
        else:
            current.append(value)
    if current:
        chunks.append((f"{label}: {', '.join(current)}", source_section))
    return chunks


def _chunk_text(text: str, source_section: str) -> list[tuple[str, str]]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []

    pieces = extract_bullets(text)
    if not pieces:
        pieces = [segment.strip() for segment in re.split(r"(?<=[.!?;])\s+|\n+", text) if segment.strip()]
    if not pieces:
        pieces = [cleaned]

    chunks: list[tuple[str, str]] = []
    for piece in pieces:
        compact = re.sub(r"\s+", " ", piece).strip(" -*\t\r\n")
        if not compact:
            continue
        if len(compact) <= MAX_CHUNK_CHARS:
            chunks.append((compact, source_section))
            continue
        chunks.extend((part, source_section) for part in _split_long_piece(compact))
    return chunks


def _split_long_piece(text: str) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) > MAX_CHUNK_CHARS and current:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _section_label(section: DocumentSection) -> str:
    heading = normalize_text(section.heading)
    if any(term in heading for term in ["experience", "employment", "work history"]):
        return "work_history"
    if "project" in heading:
        return "projects"
    if "education" in heading or "degree" in heading:
        return "education"
    if "skill" in heading or "tool" in heading or "technology" in heading:
        return "skills"
    if any(term in heading for term in ["summary", "profile", "introduction"]):
        return "summary"
    if any(term in heading for term in ["domain", "research"]):
        return "domains"
    if "role" in heading:
        return "roles"
    return heading.replace(" ", "_") or "profile"


def _dedupe_evidence(candidates: list[tuple[str, str]]) -> list[EvidenceItem]:
    seen: set[str] = set()
    result: list[EvidenceItem] = []
    for text, source_section in candidates:
        cleaned = re.sub(r"\s+", " ", text).strip()
        key = normalize_text(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        result.append(EvidenceItem(text=cleaned, source_section=source_section, similarity=0.0))
    return result


def _clamp_similarity(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
