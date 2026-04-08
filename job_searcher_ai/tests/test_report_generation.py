from datetime import datetime
from pathlib import Path

from job_searcher.reporting.csv_export import export_ranked_jobs_csv
from job_searcher.reporting.markdown_report import build_search_report_markdown, build_top_matches_markdown
from job_searcher.schemas import Disposition, JobListing, JobScore, RankedJob, SearchReport, WorkMode


def test_report_generation_writes_expected_content(tmp_path: Path) -> None:
    ranked_job = RankedJob(
        listing=JobListing(
            id="job-1",
            source="manual_import",
            source_url="https://example.com/job-1",
            title="Perception Engineer",
            company="Example Robotics",
            location="Berlin",
            work_mode=WorkMode.HYBRID,
            description="Build perception systems.",
            required_skills=["python"],
            preferred_skills=[],
            responsibilities=[],
            minimum_qualifications=[],
            domain_signals=["robotics"],
            application_url="https://example.com/job-1/apply",
        ),
        score=JobScore(
            job_id="job-1",
            overall_score=88,
            rules_based_score=84,
            embedding_similarity_score=70,
            why_match="strong adjacent-title match",
            disposition=Disposition.APPLY,
            recommended_resume_emphasis="Emphasize robotics perception delivery.",
            recommended_cover_letter_angle="Connect prior impact to robotics perception.",
        ),
    )
    report = SearchReport(
        generated_at=datetime(2026, 4, 9, 12, 0, 0),
        profile_summary="Applied AI and perception engineer.",
        sources_searched=["manual_import"],
        total_jobs_discovered=1,
        total_jobs_ranked=1,
        top_jobs=[ranked_job],
    )

    top_matches = build_top_matches_markdown([ranked_job], top_n=5)
    search_report = build_search_report_markdown(report)
    csv_path = tmp_path / "ranked.csv"
    export_ranked_jobs_csv([ranked_job], csv_path)

    assert "Perception Engineer @ Example Robotics" in top_matches
    assert "Sources searched: manual_import" in search_report
    assert csv_path.read_text(encoding="utf-8")
