"""LLM-assisted qualitative job reasoning."""

from __future__ import annotations

from job_searcher.llm.ollama_client import OllamaClient, OllamaClientError
from job_searcher.llm.prompts import JOB_FIT_SYSTEM, build_job_fit_prompt
from job_searcher.schemas import JobListing, LLMAssessment, UserProfile


def assess_job_with_llm(
    profile: UserProfile,
    job: JobListing,
    rules_score: float,
    client: OllamaClient | None,
    missing_skills: list[str],
) -> LLMAssessment:
    """Use the local LLM for qualitative fit, with heuristic fallback."""

    if client is None:
        return _heuristic_assessment(job, rules_score, missing_skills)
    try:
        payload = client.generate_json(build_job_fit_prompt(profile, job, rules_score), system=JOB_FIT_SYSTEM)
    except OllamaClientError:
        return _heuristic_assessment(job, rules_score, missing_skills)

    return LLMAssessment.model_validate(
        {
            "fit_label": payload.get("fit_label") or _heuristic_fit_label(rules_score),
            "why_match": payload.get("why_match") or f"Potential fit for {job.title}.",
            "missing_requirements": payload.get("missing_requirements") or missing_skills,
            "recommended_resume_emphasis": payload.get("recommended_resume_emphasis")
            or f"Highlight overlap with {', '.join(job.required_skills[:3]) or job.title}.",
            "recommended_cover_letter_angle": payload.get("recommended_cover_letter_angle")
            or f"Explain why your background maps to {job.company}'s needs.",
        }
    )


def _heuristic_assessment(job: JobListing, rules_score: float, missing_skills: list[str]) -> LLMAssessment:
    return LLMAssessment(
        fit_label=_heuristic_fit_label(rules_score),
        why_match=f"Rules-based scoring indicates a {_heuristic_fit_label(rules_score)} match for {job.title}.",
        missing_requirements=missing_skills,
        recommended_resume_emphasis=f"Stress direct work on {', '.join(job.domain_signals[:2] or [job.title])}.",
        recommended_cover_letter_angle=f"Tie shipped results to {job.company}'s role scope.",
    )


def _heuristic_fit_label(rules_score: float) -> str:
    if rules_score >= 78:
        return "realistic"
    if rules_score >= 55:
        return "stretch"
    return "poor_fit"
