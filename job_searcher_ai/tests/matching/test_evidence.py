from job_searcher.matching.evidence import build_candidate_evidence, retrieve_evidence
from job_searcher.schemas import Project, Skill, UserProfile, WorkExperience


class FakeBackend:
    def similarity(self, left: str, right: str) -> float:
        if "PyTorch" in right:
            return 0.91
        if "Docker" in right:
            return 0.44
        return 0.10


def test_candidate_evidence_builder_creates_labeled_chunks() -> None:
    profile = UserProfile(
        summary="Computer vision engineer with Python deployment experience.",
        skills=[Skill(name="Python"), Skill(name="PyTorch")],
        domain_strengths=["computer vision"],
        role_families=["perception engineer"],
        work_experience=[
            WorkExperience(
                title="ML Engineer",
                company="Example Robotics",
                highlights=["Built Docker inference services for vision models."],
            )
        ],
        projects=[
            Project(
                name="Vision Demo",
                description="PyTorch object detection prototype.",
            )
        ],
    )

    evidence = build_candidate_evidence(profile)
    sections = {item.source_section for item in evidence}

    assert {"summary", "skills", "domains", "roles", "work_history", "projects"} <= sections
    assert len({item.text for item in evidence}) == len(evidence)


def test_retrieve_evidence_ranks_by_backend_similarity() -> None:
    profile = UserProfile(
        summary="Computer vision engineer.",
        skills=[Skill(name="Docker"), Skill(name="PyTorch")],
    )
    evidence = build_candidate_evidence(profile)

    ranked = retrieve_evidence("PyTorch model development", evidence, FakeBackend(), top_k=2)

    assert ranked[0].similarity == 0.91
    assert "PyTorch" in ranked[0].text
    assert len(ranked) == 2
