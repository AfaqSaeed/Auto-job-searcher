from job_searcher.llm.ollama_client import OllamaClientError
from job_searcher.matching.requirements import extract_requirements
from job_searcher.schemas import JobListing


class FailingClient:
    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        raise OllamaClientError("offline")


def test_requirement_extraction_deduplicates_structured_fields() -> None:
    job = JobListing(
        id="job-1",
        source="manual",
        source_url="https://example.com/job",
        title="Vision Engineer",
        company="Example Co",
        description="Good communication is helpful. Build computer vision classification evaluation pipelines.",
        required_skills=["Python", "Python", "computer vision", "c"],
        preferred_skills=["PyTorch", "PyTorch"],
        responsibilities=["Build computer vision evaluation pipelines"],
    )

    requirements = extract_requirements(job, None)

    assert requirements.count("Python") == 1
    assert "computer vision" in requirements
    assert "PyTorch" in requirements
    assert "c" not in requirements
    assert not any(item.lower() == "good communication" for item in requirements)
    assert len(requirements) <= 15


def test_requirement_extraction_falls_back_when_ollama_fails() -> None:
    job = JobListing(
        id="job-2",
        source="manual",
        source_url="https://example.com/job",
        title="ML Engineer",
        company="Example Co",
        description="Experience developing Python model evaluation workflows.",
        required_skills=["Python"],
    )

    requirements = extract_requirements(job, FailingClient())

    assert requirements[0] == "Python"
    assert any("model evaluation" in item.lower() for item in requirements)
