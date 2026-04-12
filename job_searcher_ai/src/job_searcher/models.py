"""Shared taxonomies and pipeline artifact models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


ROLE_FAMILY_SYNONYMS: dict[str, list[str]] = {
    "computer_vision": [
        "computer vision engineer",
        "vision engineer",
        "computer vision scientist",
        "vision scientist",
        "ml engineer vision",
        "ai engineer vision",
    ],
    "perception": [
        "perception engineer",
        "perception scientist",
        "autonomy perception engineer",
        "multimodal perception engineer",
        "visual perception engineer",
    ],
    "multimodal_ai": [
        "multimodal ai engineer",
        "multimodal research engineer",
        "research engineer multimodal ai",
        "foundation model engineer",
        "applied ai engineer",
    ],
    "mapping_localization": [
        "mapping and localization engineer",
        "localization engineer",
        "slam engineer",
        "mapping engineer",
        "state estimation engineer",
    ],
    "three_d_vision": [
        "3d vision engineer",
        "geometry engineer",
        "reconstruction engineer",
        "depth perception engineer",
    ],
    "robotics_ai": [
        "robotics engineer",
        "robot perception engineer",
        "robot learning engineer",
    ],
}

DOMAIN_SYNONYMS: dict[str, list[str]] = {
    "computer vision": ["image understanding", "visual ai", "vision models"],
    "multimodal perception": ["sensor fusion", "camera lidar radar", "perception stack"],
    "3d vision": ["3d perception", "geometry", "reconstruction", "depth estimation"],
    "slam": ["visual slam", "mapping", "localization", "odometry"],
    "robotics": ["autonomy", "robot perception", "robotics ai"],
    "edge deployment": ["real-time inference", "embedded ai", "on-device inference"],
    "generative ai": ["foundation models", "vision-language models", "multimodal llms"],
}

INDUSTRY_SYNONYMS: dict[str, list[str]] = {
    "autonomous driving": ["self-driving", "autonomy", "av"],
    "robotics": ["warehouse robotics", "industrial robotics", "robot systems"],
    "automotive": ["vehicle systems", "mobility"],
    "industrial ai": ["manufacturing ai", "inspection ai"],
    "mapping": ["geospatial", "hd maps", "navigation"],
}

SKILL_CATEGORIES: dict[str, list[str]] = {
    "programming_languages": ["python", "c++", "c", "rust", "java", "sql"],
    "frameworks": ["pytorch", "tensorflow", "opencv", "onnx", "ros", "cuda", "triton"],
    "cloud": ["aws", "gcp", "azure", "docker", "kubernetes"],
    "ml_topics": [
        "deep learning",
        "computer vision",
        "multimodal ai",
        "3d vision",
        "slam",
        "sensor fusion",
        "tracking",
        "detection",
        "segmentation",
        "classification",
    ],
    "leadership": ["leadership", "mentoring", "hiring", "tech lead", "roadmap"],
}

SENIORITY_HINTS: dict[str, int] = {
    "intern": 10,
    "junior": 25,
    "associate": 35,
    "mid": 50,
    "engineer": 60,
    "senior": 78,
    "staff": 88,
    "principal": 95,
    "lead": 85,
    "manager": 72,
    "director": 98,
}


class PipelineArtifacts(BaseModel):
    """Resolved file paths for intermediate and final outputs."""

    output_dir: Path
    cache_dir: Path
    profile_document_json: Path
    profile_structured_json: Path
    profile_keywords_json: Path
    profile_keywords_md: Path
    search_queries_json: Path
    discovered_jobs_json: Path
    filtered_jobs_debug_json: Path
    custom_career_pages_debug_json: Path
    custom_career_page_filters_json: Path
    site_filtered_jobs_json: Path
    site_filtered_jobs_md: Path
    jobs_ranked_json: Path
    jobs_ranked_csv: Path
    top_matches_md: Path
    search_report_md: Path
    search_report_json: Path

    @classmethod
    def from_root(cls, root: Path, output_dir: str, cache_dir: str) -> "PipelineArtifacts":
        output_path = root / output_dir
        cache_path = root / cache_dir
        return cls(
            output_dir=output_path,
            cache_dir=cache_path,
            profile_document_json=output_path / "profile_document.json",
            profile_structured_json=output_path / "profile_structured.json",
            profile_keywords_json=output_path / "profile_keywords.json",
            profile_keywords_md=output_path / "profile_keywords.md",
            search_queries_json=output_path / "search_queries.json",
            discovered_jobs_json=output_path / "discovered_jobs.json",
            filtered_jobs_debug_json=output_path / "filtered_jobs_debug.json",
            custom_career_pages_debug_json=output_path / "custom_career_pages_debug.json",
            custom_career_page_filters_json=output_path / "custom_career_page_filters.json",
            site_filtered_jobs_json=output_path / "site_filtered_jobs.json",
            site_filtered_jobs_md=output_path / "site_filtered_jobs.md",
            jobs_ranked_json=output_path / "jobs_ranked.json",
            jobs_ranked_csv=output_path / "jobs_ranked.csv",
            top_matches_md=output_path / "top_matches.md",
            search_report_md=output_path / "search_report.md",
            search_report_json=output_path / "search_report.json",
        )
