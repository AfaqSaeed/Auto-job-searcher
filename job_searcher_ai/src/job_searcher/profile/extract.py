"""Deterministic profile extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable

from job_searcher.models import DOMAIN_SYNONYMS, INDUSTRY_SYNONYMS, ROLE_FAMILY_SYNONYMS, SKILL_CATEGORIES
from job_searcher.schemas import DocumentSection, Education, ProfileDocument, Project, Skill, UserProfile, WorkExperience
from job_searcher.utils.text import collect_phrase_matches, extract_bullets, most_common_terms, unique_preserve_order


LINK_RE = re.compile(r"https?://\S+")


def _extract_name_and_headline(document: ProfileDocument) -> tuple[str | None, str | None]:
    first_section = document.sections[0] if document.sections else None
    name = first_section.heading if first_section and first_section.heading != "Introduction" else None
    headline = None
    if first_section and first_section.content:
        for line in first_section.content.splitlines():
            if line.strip():
                headline = line.strip()
                break
    return name, headline


def _parse_dated_heading(heading: str) -> tuple[str, str | None, str | None]:
    parts = [part.strip() for part in heading.split("|")]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], None
    return heading.strip(), None, None


def _child_sections(document: ProfileDocument, parent_terms: Iterable[str]) -> list[DocumentSection]:
    for index, section in enumerate(document.sections):
        heading = section.heading.lower()
        if not any(term in heading for term in parent_terms):
            continue
        children: list[DocumentSection] = []
        for candidate in document.sections[index + 1 :]:
            if candidate.level <= section.level:
                break
            if candidate.level == section.level + 1:
                children.append(candidate)
        return children
    return []


def _split_date_range(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in re.split(r"\s+-\s+|\s+to\s+", value, maxsplit=1)]
    if len(parts) == 2:
        return parts[0], parts[1]
    return value, None


def _extract_skill_names(text: str) -> list[str]:
    skills: list[str] = []
    for phrases in SKILL_CATEGORIES.values():
        skills.extend(collect_phrase_matches(text, phrases))
    return unique_preserve_order(skills)


def _extract_domains(text: str) -> list[str]:
    matches: list[str] = []
    normalized = text.lower()
    for domain, related in DOMAIN_SYNONYMS.items():
        if domain in normalized or any(term in normalized for term in related):
            matches.append(domain)
    return unique_preserve_order(matches)


def _extract_role_families(text: str) -> list[str]:
    normalized = text.lower()
    families = [
        family.replace("_", " ")
        for family, variants in ROLE_FAMILY_SYNONYMS.items()
        if family.replace("_", " ") in normalized or any(variant in normalized for variant in variants)
    ]
    return unique_preserve_order(families)


def _extract_industries(text: str) -> list[str]:
    normalized = text.lower()
    industries = [
        industry
        for industry, variants in INDUSTRY_SYNONYMS.items()
        if industry in normalized or any(term in normalized for term in variants)
    ]
    return unique_preserve_order(industries)


def _parse_experience(document: ProfileDocument) -> list[WorkExperience]:
    items: list[WorkExperience] = []
    for section in _child_sections(document, ["experience", "employment", "work history"]):
        title, company, date_range = _parse_dated_heading(section.heading)
        highlights = extract_bullets(section.content)
        combined = " ".join(highlights) or section.content
        start_date, end_date = _split_date_range(date_range)
        items.append(
            WorkExperience(
                title=title,
                company=company,
                start_date=start_date,
                end_date=end_date,
                highlights=highlights,
                technologies=_extract_skill_names(combined),
                domains=_extract_domains(combined),
                leadership_signals=collect_phrase_matches(combined, SKILL_CATEGORIES["leadership"]),
            )
        )
    return items


def _parse_projects(document: ProfileDocument) -> list[Project]:
    items: list[Project] = []
    for section in _child_sections(document, ["project"]):
        highlights = extract_bullets(section.content)
        combined = " ".join(highlights) or section.content
        items.append(
            Project(
                name=section.heading,
                description=combined,
                highlights=highlights,
                technologies=_extract_skill_names(combined),
                domains=_extract_domains(combined),
                links=LINK_RE.findall(section.content),
            )
        )
    return items


def _parse_education(document: ProfileDocument) -> list[Education]:
    items: list[Education] = []
    for section in _child_sections(document, ["education"]):
        degree, institution, date_range = _parse_dated_heading(section.heading)
        items.append(
            Education(
                degree=degree,
                institution=institution or degree,
                date_range=date_range,
                notes=extract_bullets(section.content),
            )
        )
    return items


def _classify_skill(skill: str) -> str:
    normalized = skill.lower()
    for category, skills in SKILL_CATEGORIES.items():
        if normalized in skills:
            return category
    return "general"


def _infer_seniority(text: str) -> str | None:
    normalized = text.lower()
    for hint in ["principal", "staff", "senior", "lead", "mid", "junior", "intern"]:
        if hint in normalized:
            return hint
    return None


def extract_profile(document: ProfileDocument) -> UserProfile:
    """Build a structured user profile from the ingested document."""

    name, headline = _extract_name_and_headline(document)
    raw_text = document.raw_text
    work_experience = _parse_experience(document)
    projects = _parse_projects(document)
    education = _parse_education(document)
    extracted_skills = _extract_skill_names(raw_text)
    role_families = _extract_role_families(raw_text)
    industries = _extract_industries(raw_text)
    domains = _extract_domains(raw_text)
    leadership = collect_phrase_matches(raw_text, SKILL_CATEGORIES["leadership"])
    programming_languages = collect_phrase_matches(raw_text, SKILL_CATEGORIES["programming_languages"])
    tools = unique_preserve_order(collect_phrase_matches(raw_text, SKILL_CATEGORIES["frameworks"] + SKILL_CATEGORIES["cloud"]))
    links = LINK_RE.findall(raw_text)
    summary_terms = most_common_terms(raw_text, top_n=12)
    summary = headline or " ".join(summary_terms[:10])
    skill_models = [
        Skill(name=skill, category=_classify_skill(skill), evidence_count=max(1, raw_text.lower().count(skill.lower())))
        for skill in extracted_skills
    ]

    return UserProfile(
        name=name,
        headline=headline,
        summary=summary,
        source_files=document.source_files,
        work_experience=work_experience,
        projects=projects,
        education=education,
        skills=skill_models,
        tools=tools,
        programming_languages=programming_languages,
        research_topics=domains,
        domain_strengths=domains,
        leadership_experience=leadership,
        publications=[link for link in links if "publication" in link.lower()],
        portfolio_links=links,
        role_families=role_families,
        industries=industries,
        locations=[],
        search_keywords=unique_preserve_order(extracted_skills + domains + role_families + summary_terms),
        seniority_hint=_infer_seniority(raw_text),
        raw_text=raw_text,
        sections=document.sections,
    )
