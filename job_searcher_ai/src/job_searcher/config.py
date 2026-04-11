"""Configuration loading and project path helpers."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SearchSettings(BaseModel):
    locations: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    target_countries: list[str] = Field(default_factory=list)
    remote_preference: str = "hybrid"
    experience_level: str = "mid"
    query_limit: int = 40
    english_first: bool = True
    include_german_variants: bool = False


class PreferredCriteria(BaseModel):
    locations: list[str] = Field(default_factory=list)
    remote_preference: str = "hybrid"
    visa_constraints: list[str] = Field(default_factory=list)
    minimum_salary: float | None = None
    target_titles: list[str] = Field(default_factory=list)
    blacklist_companies: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    seniority_range: list[str] = Field(default_factory=list)


class OllamaSettings(BaseModel):
    enabled: bool = True
    host: str = Field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    temperature: float = 0.2
    timeout_seconds: int = 120


class EmbeddingSettings(BaseModel):
    enabled: bool = False
    model_name: str = "BAAI/bge-small-en-v1.5"
    model_config = ConfigDict(protected_namespaces=())


class ScrapingSettings(BaseModel):
    request_timeout_seconds: int = 20
    rate_limit_seconds: float = 1.0
    max_retries: int = 3
    cache_ttl_hours: int = 24
    respect_robots: bool = True
    user_agent: str = "job_searcher_ai/0.1 (+personal job research)"


class SourceToggles(BaseModel):
    greenhouse: bool = True
    lever: bool = True
    static_pages: bool = False
    rss: bool = False
    manual_import: bool = True
    custom_career_pages: bool = False


class StaticPageConfig(BaseModel):
    name: str
    url: str
    job_card_selector: str | None = None
    title_selector: str | None = None
    location_selector: str | None = None
    link_selector: str | None = None
    company: str | None = None


class CustomCareerPageConfig(BaseModel):
    name: str
    url: str
    company: str | None = None
    include_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(default_factory=list)
    seed_urls: list[str] = Field(default_factory=list)
    max_pages: int = 150
    render_javascript: bool = False
    apply_site_filters: bool = False
    rendered_link_selector: str | None = None
    rendered_wait_selector: str | None = None
    sitemap_paths: list[str] = Field(default_factory=lambda: ["/sitemap.xml", "/sitemap_index.xml"])


class SourcesSettings(BaseModel):
    toggles: SourceToggles = Field(default_factory=SourceToggles)
    greenhouse_boards: list[str] = Field(default_factory=list)
    lever_boards: list[str] = Field(default_factory=list)
    static_pages: list[StaticPageConfig] = Field(default_factory=list)
    custom_career_pages: list[CustomCareerPageConfig] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list)
    manual_files: list[str] = Field(default_factory=list)


class OutputSettings(BaseModel):
    directory: str = "outputs"
    cache_directory: str = ".cache"
    top_n_markdown: int = 20


class AppConfig(BaseModel):
    search: SearchSettings = Field(default_factory=SearchSettings)
    criteria: PreferredCriteria = Field(default_factory=PreferredCriteria)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    sources: SourcesSettings = Field(default_factory=SourcesSettings)
    outputs: OutputSettings = Field(default_factory=OutputSettings)


def resolve_project_root(start: Path | None = None) -> Path:
    """Walk upwards until the project root is found."""

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "settings.yaml").exists() and (candidate / "src").exists():
            return candidate
    return current


def load_config(config_path: Path | None = None, project_root: Path | None = None) -> AppConfig:
    """Load YAML configuration into an AppConfig model."""

    root = resolve_project_root(project_root)
    path = config_path or Path(os.getenv("JOB_SEARCHER_CONFIG", root / "config" / "settings.yaml"))
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(payload)


def ensure_runtime_directories(project_root: Path, config: AppConfig) -> None:
    """Create output and cache directories if needed."""

    (project_root / config.outputs.directory).mkdir(parents=True, exist_ok=True)
    (project_root / config.outputs.cache_directory).mkdir(parents=True, exist_ok=True)
