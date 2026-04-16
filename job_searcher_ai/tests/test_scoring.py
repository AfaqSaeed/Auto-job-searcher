from pathlib import Path

from job_searcher.config import load_config
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.ranking import fusion as fusion_module
from job_searcher.ranking.rules import score_job_rules
from job_searcher.schemas import JobListing, JobScore, LLMAssessment, WorkMode


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


def test_rank_jobs_only_calls_llm_for_configured_shortlist() -> None:
    config = load_config(Path("config/settings.yaml"), project_root=Path.cwd())
    config.ranking.llm_enabled = True
    config.ranking.llm_top_n = 1
    config.ranking.llm_min_rules_score = 55.0

    jobs = [
        JobListing(
            id="job-1",
            source="manual_import",
            source_url="https://example.com/jobs/1",
            title="Perception Engineer",
            company="Example Robotics",
            description="role 1",
        ),
        JobListing(
            id="job-2",
            source="manual_import",
            source_url="https://example.com/jobs/2",
            title="Vision Engineer",
            company="Example Robotics",
            description="role 2",
        ),
    ]

    original_score_job_rules = fusion_module.score_job_rules
    original_compute_similarity = fusion_module.compute_profile_job_similarity
    original_assess_job_with_llm = fusion_module.assess_job_with_llm

    llm_calls: list[str] = []

    def fake_score_job_rules(profile, job, config):
        score = JobScore(job_id=job.id)
        score.rules_based_score = 90.0 if job.id == "job-1" else 60.0
        return score

    def fake_compute_similarity(profile, job, config):
        return 0.0

    def fake_assess_job_with_llm(profile, job, rules_score, client, missing_skills):
        if client is not None:
            llm_calls.append(job.id)
        return LLMAssessment(fit_label="realistic", why_match=f"fit for {job.id}")

    fusion_module.score_job_rules = fake_score_job_rules
    fusion_module.compute_profile_job_similarity = fake_compute_similarity
    fusion_module.assess_job_with_llm = fake_assess_job_with_llm
    try:
        profile = extract_profile(read_profile_document(Path("data/profile_master.md")))
        ranked = fusion_module.rank_jobs(profile=profile, jobs=jobs, config=config, client=object())
    finally:
        fusion_module.score_job_rules = original_score_job_rules
        fusion_module.compute_profile_job_similarity = original_compute_similarity
        fusion_module.assess_job_with_llm = original_assess_job_with_llm

    assert len(ranked) == 2
    assert llm_calls == ["job-1"]
