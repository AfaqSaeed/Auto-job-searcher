"""Fuse rules, embeddings, and LLM reasoning into ranked jobs."""

from __future__ import annotations

import logging
import time
from typing import Callable

from job_searcher.config import AppConfig
from job_searcher.llm.ollama_client import OllamaClient
from job_searcher.logging_utils import ProgressLogger
from job_searcher.ranking.embeddings import compute_profile_job_similarity
from job_searcher.ranking.llm_reasoning import assess_job_with_llm
from job_searcher.ranking.rules import score_job_rules
from job_searcher.schemas import Disposition, JobListing, JobScore, RankedJob, UserProfile


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
    checkpoint_callback: Callable[[list[RankedJob]], None] | None = None,
    checkpoint_interval_seconds: float = 30.0,
) -> list[RankedJob]:
    """Rank jobs by fusing symbolic, embedding, and LLM signals."""

    prelim_ranked: list[RankedJob] = []
    llm_shortlist_progress = ProgressLogger(LOGGER, "Prep ranking shortlist", len(jobs), min_interval_seconds=3.0)
    for job in jobs:
        score = score_job_rules(profile, job, config)
        embedding_score = compute_profile_job_similarity(profile, job, config) if config.embeddings.enabled else 0.0
        score.embedding_similarity_score = embedding_score
        score.llm_latency_seconds = 0.0
        prelim_overall = round(score.rules_based_score * 0.80 + embedding_score * 0.20, 2)
        score.overall_score = max(0.0, min(100.0, prelim_overall))
        prelim_ranked.append(RankedJob(listing=job, score=score))
        llm_shortlist_progress.advance()
    llm_shortlist_progress.finish()

    prelim_ranked.sort(key=lambda item: item.score.overall_score, reverse=True)
    llm_shortlist = _llm_shortlist_job_ids(prelim_ranked, config)
    LOGGER.info(
        "LLM ranking shortlist contains %s/%s jobs (top_n=%s, min_rules_score=%.1f, llm_enabled=%s)",
        len(llm_shortlist),
        len(prelim_ranked),
        config.ranking.llm_top_n,
        config.ranking.llm_min_rules_score,
        config.ranking.llm_enabled and client is not None,
    )

    ranked: list[RankedJob] = []
    progress = ProgressLogger(LOGGER, "Rank jobs", len(jobs), min_interval_seconds=3.0)
    last_checkpoint_at = 0.0
    effective_client = client if config.ranking.llm_enabled else None
    for ranked_job in prelim_ranked:
        job = ranked_job.listing
        score = ranked_job.score
        llm_client = effective_client if job.id in llm_shortlist else None
        llm_elapsed = 0.0
        if llm_client is not None:
            llm_started_at = time.perf_counter()
            llm_assessment = assess_job_with_llm(profile, job, score.rules_based_score, llm_client, score.missing_skills)
            llm_elapsed = round(time.perf_counter() - llm_started_at, 3)
        else:
            llm_assessment = assess_job_with_llm(profile, job, score.rules_based_score, None, score.missing_skills)
        llm_numeric = LLM_LABEL_SCORES.get(llm_assessment.fit_label, 50.0)
        overall = round(score.rules_based_score * 0.65 + score.embedding_similarity_score * 0.20 + llm_numeric * 0.15, 2)
        score.llm_latency_seconds = llm_elapsed
        score.llm_assessment = llm_assessment
        score.overall_score = max(0.0, min(100.0, overall))
        score.why_match = llm_assessment.why_match or score.why_match
        score.recommended_resume_emphasis = llm_assessment.recommended_resume_emphasis or score.recommended_resume_emphasis
        score.recommended_cover_letter_angle = llm_assessment.recommended_cover_letter_angle or score.recommended_cover_letter_angle
        score.disposition = _final_disposition(score.overall_score, score.disposition)
        ranked.append(RankedJob(listing=job, score=score))
        if llm_client is not None:
            LOGGER.info(
                "LLM reasoning for %s @ %s took %.3fs",
                job.title,
                job.company,
                llm_elapsed,
            )
        if checkpoint_callback is not None:
            now = time.monotonic()
            if last_checkpoint_at == 0.0 or (now - last_checkpoint_at) >= checkpoint_interval_seconds:
                checkpoint_callback(list(ranked))
                last_checkpoint_at = now
        progress.advance()
    progress.finish()
    if checkpoint_callback is not None:
        checkpoint_callback(list(ranked))
    return sorted(ranked, key=lambda item: item.score.overall_score, reverse=True)


def _final_disposition(overall_score: float, fallback: Disposition) -> Disposition:
    if overall_score >= 80:
        return Disposition.APPLY
    if overall_score >= 55:
        return Disposition.MAYBE
    return fallback if fallback == Disposition.SKIP else Disposition.SKIP


def _llm_shortlist_job_ids(ranked_jobs: list[RankedJob], config: AppConfig) -> set[str]:
    if not config.ranking.llm_enabled or config.ranking.llm_top_n <= 0:
        return set()

    shortlisted: set[str] = set()
    for ranked_job in ranked_jobs:
        if len(shortlisted) >= config.ranking.llm_top_n:
            break
        if ranked_job.score.rules_based_score < config.ranking.llm_min_rules_score:
            continue
        shortlisted.add(ranked_job.listing.id)
    return shortlisted
