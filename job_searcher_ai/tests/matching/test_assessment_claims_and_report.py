from job_searcher.config import AppConfig
from job_searcher.llm.ollama_client import OllamaClientError
from job_searcher.matching.assessment import assess_requirement
from job_searcher.matching.claim_checker import check_claim
from job_searcher.matching.schemas import EvidenceItem, MatchStatus
from job_searcher.matching.service import build_candidate_match_report
from job_searcher.reporting.markdown_report import build_candidate_match_markdown
from job_searcher.schemas import JobListing, Skill, UserProfile


class StaticBackend:
    def __init__(self, score: float) -> None:
        self.score = score

    def similarity(self, left: str, right: str) -> float:
        return self.score


class FailingClient:
    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        raise OllamaClientError("offline")


def test_heuristic_requirement_classification() -> None:
    strong = assess_requirement(
        "Python engineering",
        [EvidenceItem(text="Built Python services.", source_section="work_history", similarity=0.80)],
        None,
    )
    partial = assess_requirement(
        "Docker deployment",
        [EvidenceItem(text="Packaged models for deployment.", source_section="work_history", similarity=0.55)],
        None,
    )
    missing = assess_requirement("Rust programming", [], None)

    assert strong.status == MatchStatus.STRONG_MATCH
    assert partial.status == MatchStatus.PARTIAL_MATCH
    assert missing.status == MatchStatus.MISSING


def test_assessment_falls_back_when_ollama_fails() -> None:
    assessment = assess_requirement(
        "Python engineering",
        [EvidenceItem(text="Built Python services.", source_section="work_history", similarity=0.80)],
        FailingClient(),
    )

    assert assessment.status == MatchStatus.STRONG_MATCH


def test_claim_checker_fallback_flags_unsupported_claim() -> None:
    assessment = check_claim(
        "I have built production RAG systems using FastAPI.",
        [EvidenceItem(text="Built and deployed Python AI workflows.", source_section="work_history")],
        StaticBackend(0.52),
        None,
    )

    assert assessment.supported is False
    assert assessment.safer_wording
    assert "FastAPI" not in assessment.explanation


def test_report_score_calculation_from_requirement_statuses() -> None:
    config = AppConfig()
    config.matching.use_llm = False
    config.embeddings.enabled = False
    profile = UserProfile(skills=[Skill(name="Python")])
    job = JobListing(
        id="job-1",
        source="manual",
        source_url="https://example.com/job",
        title="Backend Engineer",
        company="Example Co",
        description="",
        required_skills=["Python", "Rust"],
    )

    report = build_candidate_match_report(profile, job, config)

    assert report.overall_score == 30.0
    assert [item.status for item in report.assessments] == [MatchStatus.PARTIAL_MATCH, MatchStatus.MISSING]


def test_no_evidence_case_is_missing() -> None:
    config = AppConfig()
    config.matching.use_llm = False
    profile = UserProfile()
    job = JobListing(
        id="job-2",
        source="manual",
        source_url="https://example.com/job",
        title="ML Engineer",
        company="Example Co",
        description="",
        required_skills=["Python"],
    )

    report = build_candidate_match_report(profile, job, config)

    assert report.overall_score == 0.0
    assert report.assessments[0].status == MatchStatus.MISSING
    assert report.gaps


def test_markdown_export_contains_requirements_and_claims() -> None:
    config = AppConfig()
    config.matching.use_llm = False
    config.embeddings.enabled = False
    profile = UserProfile(skills=[Skill(name="Python")])
    job = JobListing(
        id="job-3",
        source="manual",
        source_url="https://example.com/job",
        title="AI Engineer",
        company="Example Co",
        description="",
        required_skills=["Python"],
    )
    report = build_candidate_match_report(
        profile,
        job,
        config,
        claims=["I have built production RAG systems using FastAPI."],
    )

    markdown = build_candidate_match_markdown(report)

    assert "# Explainable Match Report: AI Engineer @ Example Co" in markdown
    assert "## Requirement Assessments" in markdown
    assert "## Unsupported Claims" in markdown
    assert "Safer wording:" in markdown
