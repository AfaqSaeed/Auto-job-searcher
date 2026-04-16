"""Fuse rules, embeddings, and LLM reasoning into ranked jobs."""

from __future__ import annotations

import logging

from job_searcher.config import AppConfig
from job_searcher.llm.ollama_client import OllamaClient
from job_searcher.logging_utils import ProgressLogger
from job_searcher.ranking.embeddings import compute_profile_job_similarity
from job_searcher.ranking.llm_reasoning import assess_job_with_llm
from job_searcher.ranking.rules import score_job_rules
from job_searcher.schemas import Disposition, JobListing, RankedJob, UserProfile


LOGGER = logging.getLogger(__name__)


LLM_LABEL_SCORES = {
    "realistic": 90.0,
    "stretch": 65.0,
    "poor_fit": 25.0,
    "unknown": 50.0,
}


def rank_jobs(
    profile: UserProfile,
    jobs: list[JobListing],
    config: AppConfig,
    client: OllamaClient | None = None,
) -> list[RankedJob]:
    """Rank jobs by fusing symbolic, embedding, and LLM signals."""

    ranked: list[RankedJob] = []
    progress = ProgressLogger(LOGGER, "Rank jobs", len(jobs), min_interval_seconds=3.0)
    for job in jobs:
        score = score_job_rules(profile, job, config)
        embedding_score = compute_profile_job_similarity(profile, job, config) if config.embeddings.enabled else 0.0
        llm_assessment = assess_job_with_llm(profile, job, score.rules_based_score, client, score.missing_skills)
        llm_numeric = LLM_LABEL_SCORES.get(llm_assessment.fit_label, 50.0)
        overall = round(score.rules_based_score * 0.65 + embedding_score * 0.20 + llm_numeric * 0.15, 2)
        score.embedding_similarity_score = embedding_score
        score.llm_assessment = llm_assessment
        score.overall_score = max(0.0, min(100.0, overall))
        score.why_match = llm_assessment.why_match or score.why_match
        score.recommended_resume_emphasis = llm_assessment.recommended_resume_emphasis or score.recommended_resume_emphasis
        score.recommended_cover_letter_angle = llm_assessment.recommended_cover_letter_angle or score.recommended_cover_letter_angle
        score.disposition = _final_disposition(score.overall_score, score.disposition)
        ranked.append(RankedJob(listing=job, score=score))
        progress.advance()
    progress.finish()
    return sorted(ranked, key=lambda item: item.score.overall_score, reverse=True)


def _final_disposition(overall_score: float, fallback: Disposition) -> Disposition:
    if overall_score >= 80:
        return Disposition.APPLY
    if overall_score >= 55:
        return Disposition.MAYBE
    return fallback if fallback == Disposition.SKIP else Disposition.SKIP
