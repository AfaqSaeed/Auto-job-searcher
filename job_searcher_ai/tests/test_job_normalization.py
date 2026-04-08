from job_searcher.parsing.normalization import normalize_job_listing
from job_searcher.schemas import JobListing


def test_job_normalization_extracts_salary_and_work_mode() -> None:
    listing = JobListing(
        id="job-1",
        source="manual_import",
        source_url="https://example.com/job-1",
        title="Computer Vision Engineer",
        company="Example AI",
        location="Remote in Germany",
        description="Remote role. Salary EUR 100000-130000. Requires Python, PyTorch, computer vision, and SLAM.",
        required_skills=["python", "pytorch", "computer vision", "slam"],
        preferred_skills=[],
        responsibilities=[],
        minimum_qualifications=[],
        domain_signals=[],
    )

    normalized = normalize_job_listing(listing)

    assert normalized.work_mode.value == "remote"
    assert normalized.salary is not None
    assert normalized.salary.minimum == 100000
