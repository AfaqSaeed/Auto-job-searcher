"""High-level explainable matching service."""

from __future__ import annotations

import hashlib
import re

from job_searcher.config import AppConfig
from job_searcher.matching.assessment import assess_requirement
from job_searcher.matching.claim_checker import check_claim
from job_searcher.matching.evidence import build_candidate_evidence, retrieve_evidence
from job_searcher.matching.requirements import extract_requirements
from job_searcher.matching.schemas import CandidateMatchReport, MatchStatus
from job_searcher.parsing.normalization import (
    extract_domain_signals,
    extract_language_requirements,
    extract_skill_mentions,
    infer_work_mode,
    normalize_job_listing,
)
from job_searcher.ranking.embeddings import EmbeddingBackend
from job_searcher.ranking.rules import score_job_rules
from job_searcher.schemas import JobListing, UserProfile
from job_searcher.utils.text import extract_bullets, unique_preserve_order
from job_searcher.llm.ollama_client import OllamaClient


STATUS_SCORES = {
    MatchStatus.STRONG_MATCH: 1.0,
    MatchStatus.PARTIAL_MATCH: 0.6,
    MatchStatus.UNCERTAIN: 0.3,
    MatchStatus.MISSING: 0.0,
}


def build_candidate_match_report(
    profile: UserProfile,
    job: JobListing,
    config: AppConfig,
    client: OllamaClient | None = None,
    raw_profile_text: str | None = None,
    claims: list[str] | None = None,
) -> CandidateMatchReport:
    """Build an evidence-backed candidate match report for one job."""

    llm_client = client if config.matching.use_llm else None
    requirements = extract_requirements(job, llm_client)[: config.matching.max_requirements]
    evidence_items = build_candidate_evidence(profile, raw_profile_text=raw_profile_text)
    backend = EmbeddingBackend(config.embeddings.model_name, enabled=config.embeddings.enabled)

    assessments = []
    for requirement in requirements:
        retrieved = retrieve_evidence(requirement, evidence_items, backend, top_k=config.matching.evidence_top_k)
        assessments.append(
            assess_requirement(
                requirement,
                retrieved,
                llm_client,
                strong_threshold=config.matching.strong_threshold,
                partial_threshold=config.matching.partial_threshold,
                uncertain_threshold=config.matching.uncertain_threshold,
            )
        )

    claim_assessments = [
        check_claim(claim, evidence_items, backend, llm_client)
        for claim in unique_preserve_order([claim for claim in claims or [] if claim.strip()])
    ]
    unsupported_claims = [assessment for assessment in claim_assessments if not assessment.supported]
    overall_score = _overall_score(assessments)
    ranking_score = score_job_rules(profile, job, config)
    strengths = _build_strengths(assessments)
    gaps = _build_gaps(assessments, ranking_score.missing_skills)

    return CandidateMatchReport(
        candidate_name=profile.name,
        job_title=job.title,
        company=job.company,
        overall_score=overall_score,
        assessments=assessments,
        strengths=strengths,
        gaps=gaps,
        unsupported_claims=unsupported_claims,
        recommendation=_recommendation(overall_score),
    )


def build_manual_job_listing(
    text: str,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    source: str = "manual_text",
    source_url: str = "manual_text",
) -> JobListing:
    """Create a normalized JobListing from a manual text or Markdown job description."""

    fields = _parse_labeled_job_text(text)
    resolved_title = title or fields.get("title") or _first_markdown_heading(text) or "Selected role"
    resolved_company = company or fields.get("company") or "Unknown company"
    resolved_location = location or fields.get("location")
    description = fields.get("description") or _strip_known_labels(text)
    digest = hashlib.sha256(f"{resolved_title}\n{resolved_company}\n{description}".encode("utf-8")).hexdigest()[:16]

    return normalize_job_listing(
        JobListing(
            id=f"manual-{digest}",
            source=source,
            source_url=source_url,
            title=resolved_title,
            company=resolved_company,
            location=resolved_location,
            work_mode=infer_work_mode(resolved_location or "", description),
            description=description,
            required_skills=extract_skill_mentions(description),
            preferred_skills=[],
            responsibilities=extract_bullets(description)[:8],
            minimum_qualifications=[],
            domain_signals=extract_domain_signals(description),
            language_requirements=extract_language_requirements(description),
            raw_payload={"input_format": "manual_text"},
        )
    )


def _overall_score(assessments: list) -> float:
    if not assessments:
        return 0.0
    score = sum(STATUS_SCORES[item.status] for item in assessments) / len(assessments)
    return round(score * 100.0, 2)


def _build_strengths(assessments: list) -> list[str]:
    strengths: list[str] = []
    for assessment in assessments:
        if assessment.status == MatchStatus.STRONG_MATCH:
            strengths.append(f"Strong evidence for: {assessment.requirement}")
        elif assessment.status == MatchStatus.PARTIAL_MATCH:
            strengths.append(f"Related or transferable evidence for: {assessment.requirement}")
        if len(strengths) >= 8:
            break
    return strengths


def _build_gaps(assessments: list, ranking_missing_skills: list[str]) -> list[str]:
    gaps: list[str] = []
    for assessment in assessments:
        if assessment.status == MatchStatus.MISSING:
            gaps.append(f"No clear evidence for: {assessment.requirement}")
        elif assessment.status == MatchStatus.UNCERTAIN:
            gaps.append(f"Needs manual review: {assessment.requirement}")
    for skill in ranking_missing_skills:
        gaps.append(f"Rules-based skill gap: {skill}")
    return unique_preserve_order(gaps)[:10]


def _recommendation(overall_score: float) -> str:
    if overall_score >= 75.0:
        return "Strong candidate based on supplied evidence; still review requirement details before applying."
    if overall_score >= 55.0:
        return "Plausible candidate with gaps; tailor application materials to the strongest evidence."
    return "Weak match based on supplied evidence; consider applying only with a clear strategy for the gaps."


def _parse_labeled_job_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    buffers: dict[str, list[str]] = {"description": []}
    label_re = re.compile(r"^(title|company|location|description)\s*:\s*(.*)$", re.IGNORECASE)

    for line in text.splitlines():
        match = label_re.match(line.strip())
        if match:
            current_key = match.group(1).lower()
            value = match.group(2).strip()
            if current_key == "description":
                buffers.setdefault("description", [])
                if value:
                    buffers["description"].append(value)
            else:
                fields[current_key] = value
            continue
        if current_key == "description":
            buffers.setdefault("description", []).append(line)

    description = "\n".join(buffers.get("description", [])).strip()
    if description:
        fields["description"] = description
    return fields


def _first_markdown_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _strip_known_labels(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if re.match(r"^(title|company|location)\s*:", line.strip(), re.IGNORECASE):
            continue
        lines.append(re.sub(r"^description\s*:\s*", "", line, flags=re.IGNORECASE))
    return "\n".join(lines).strip()
