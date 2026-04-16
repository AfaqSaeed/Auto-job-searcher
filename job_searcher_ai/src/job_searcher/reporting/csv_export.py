"""CSV export helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from job_searcher.schemas import RankedJob


FIELDNAMES = [
    "overall_score",
    "disposition",
    "title",
    "company",
    "location",
    "work_mode",
    "source",
    "application_url",
    "rules_based_score",
    "embedding_similarity_score",
    "llm_latency_seconds",
    "title_match_score",
    "skills_overlap_score",
    "domain_match_score",
    "seniority_fit_score",
    "location_fit_score",
    "constraints_fit_score",
    "why_match",
    "missing_skills",
    "recommended_resume_emphasis",
    "recommended_cover_letter_angle",
]


def export_ranked_jobs_csv(ranked_jobs: list[RankedJob], output_path: Path) -> None:
    """Write ranked jobs to CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for item in ranked_jobs:
            writer.writerow(
                {
                    "overall_score": item.score.overall_score,
                    "disposition": item.score.disposition.value,
                    "title": item.listing.title,
                    "company": item.listing.company,
                    "location": item.listing.location,
                    "work_mode": item.listing.work_mode.value,
                    "source": item.listing.source,
                    "application_url": item.listing.application_url,
                    "rules_based_score": item.score.rules_based_score,
                    "embedding_similarity_score": item.score.embedding_similarity_score,
                    "llm_latency_seconds": item.score.llm_latency_seconds,
                    "title_match_score": item.score.title_match_score,
                    "skills_overlap_score": item.score.skills_overlap_score,
                    "domain_match_score": item.score.domain_match_score,
                    "seniority_fit_score": item.score.seniority_fit_score,
                    "location_fit_score": item.score.location_fit_score,
                    "constraints_fit_score": item.score.constraints_fit_score,
                    "why_match": item.score.why_match,
                    "missing_skills": " | ".join(item.score.missing_skills),
                    "recommended_resume_emphasis": item.score.recommended_resume_emphasis,
                    "recommended_cover_letter_angle": item.score.recommended_cover_letter_angle,
                }
            )
