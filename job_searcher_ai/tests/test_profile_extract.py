from pathlib import Path

from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document


def test_extract_profile_from_sample() -> None:
    document = read_profile_document(Path("data/profile_master.md"))
    profile = extract_profile(document)

    assert profile.source_files
    assert len(profile.work_experience) >= 1
    assert len(profile.projects) >= 1
    assert "python" in [skill.name.lower() for skill in profile.skills]
    assert profile.role_families
