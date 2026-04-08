from pathlib import Path

from job_searcher.config import load_config
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.ranking.rules import score_job_rules
from job_searcher.schemas import JobListing, WorkMode


def test_rules_scoring_prefers_relevant_vision_role() -> None:
    config = load_config(Path("config/settings.yaml"), project_root=Path.cwd())
    profile = extract_profile(read_profile_document(Path("data/profile_master.md")))
    job = JobListing(
        id="job-fit-1",
        source="manual_import",
        source_url="https://example.com/jobs/fit-1",
        title="Perception Engineer",
        company="Example Robotics",
        location="Berlin, Germany",
        work_mode=WorkMode.HYBRID,
        description="Build multimodal perception, 3D vision, computer vision, and SLAM systems for robotics.",
        required_skills=["python", "pytorch", "computer vision", "slam"],
        preferred_skills=["3d vision", "sensor fusion"],
        responsibilities=["ship perception stack"],
        minimum_qualifications=["experience with robotics perception"],
        domain_signals=["robotics", "multimodal perception", "slam"],
    )

    score = score_job_rules(profile, job, config)

    assert score.title_match_score >= 80
    assert score.skills_overlap_score >= 40
    assert score.domain_match_score >= 40
    assert score.rules_based_score >= 70
