"""LLM-assisted profile summarization and keyword expansion."""

from __future__ import annotations

import logging

from job_searcher.llm.ollama_client import OllamaClient, OllamaClientError
from job_searcher.llm.prompts import PROFILE_SUMMARY_SYSTEM, build_profile_summary_prompt
from job_searcher.schemas import ProfileInsights, UserProfile
from job_searcher.utils.text import unique_preserve_order


LOGGER = logging.getLogger(__name__)


def summarize_profile(profile: UserProfile, client: OllamaClient | None) -> ProfileInsights:
    """Use Ollama when available, otherwise return a deterministic fallback."""

    if client is None:
        return _fallback_insights(profile)

    try:
        payload = client.generate_json(
            build_profile_summary_prompt(profile.raw_text[:8000]),
            system=PROFILE_SUMMARY_SYSTEM,
        )
    except OllamaClientError as exc:
        LOGGER.warning("Falling back to heuristic profile insights: %s", exc)
        return _fallback_insights(profile)

    return ProfileInsights.model_validate(
        {
            "summary": payload.get("summary", profile.summary),
            "role_families": unique_preserve_order(payload.get("role_families", profile.role_families)),
            "search_keywords": unique_preserve_order(payload.get("search_keywords", profile.search_keywords)),
            "domain_strengths": unique_preserve_order(payload.get("domain_strengths", profile.domain_strengths)),
            "industries": unique_preserve_order(payload.get("industries", profile.industries)),
            "seniority_hint": payload.get("seniority_hint", profile.seniority_hint),
        }
    )


def apply_insights(profile: UserProfile, insights: ProfileInsights) -> UserProfile:
    """Merge LLM insights into the extracted profile."""

    updated = profile.model_copy(deep=True)
    updated.llm_summary = insights.summary
    updated.summary = insights.summary or profile.summary
    updated.role_families = unique_preserve_order(profile.role_families + insights.role_families)
    updated.search_keywords = unique_preserve_order(profile.search_keywords + insights.search_keywords)
    updated.domain_strengths = unique_preserve_order(profile.domain_strengths + insights.domain_strengths)
    updated.industries = unique_preserve_order(profile.industries + insights.industries)
    updated.seniority_hint = insights.seniority_hint or profile.seniority_hint
    return updated


def _fallback_insights(profile: UserProfile) -> ProfileInsights:
    return ProfileInsights(
        summary=profile.summary,
        role_families=profile.role_families,
        search_keywords=profile.search_keywords,
        domain_strengths=profile.domain_strengths,
        industries=profile.industries,
        seniority_hint=profile.seniority_hint,
    )
