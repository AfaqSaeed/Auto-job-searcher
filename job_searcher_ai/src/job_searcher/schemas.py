"""Pydantic schemas used across the application."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class Disposition(str, Enum):
    APPLY = "apply"
    MAYBE = "maybe"
    SKIP = "skip"


class DocumentSection(BaseModel):
    heading: str
    level: int = 1
    content: str = ""


class ProfileDocument(BaseModel):
    source_files: list[str] = Field(default_factory=list)
    raw_text: str = ""
    sections: list[DocumentSection] = Field(default_factory=list)


class Skill(BaseModel):
    name: str
    category: str = "general"
    evidence_count: int = 1


class WorkExperience(BaseModel):
    title: str
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    leadership_signals: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    role: str | None = None
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str | None = None
    date_range: str | None = None
    notes: list[str] = Field(default_factory=list)


class ProfileInsights(BaseModel):
    summary: str = ""
    role_families: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    domain_strengths: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    seniority_hint: str | None = None


class UserProfile(BaseModel):
    name: str | None = None
    headline: str | None = None
    summary: str = ""
    source_files: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    research_topics: list[str] = Field(default_factory=list)
    domain_strengths: list[str] = Field(default_factory=list)
    leadership_experience: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    portfolio_links: list[str] = Field(default_factory=list)
    role_families: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    seniority_hint: str | None = None
    raw_text: str = ""
    sections: list[DocumentSection] = Field(default_factory=list)
    llm_summary: str | None = None
    model_config = ConfigDict(extra="ignore")


class SearchQuery(BaseModel):
    text: str
    title: str | None = None
    location: str | None = None
    language: str = "en"
    rationale: str | None = None
    terms: list[str] = Field(default_factory=list)


class SalaryRange(BaseModel):
    currency: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    interval: str | None = None


class JobListing(BaseModel):
    id: str
    source: str
    source_url: str
    title: str
    company: str
    location: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    salary: SalaryRange | None = None
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    minimum_qualifications: list[str] = Field(default_factory=list)
    domain_signals: list[str] = Field(default_factory=list)
    application_url: str | None = None
    date_posted: str | None = None
    language_requirements: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LLMAssessment(BaseModel):
    fit_label: str = "unknown"
    why_match: str = ""
    missing_requirements: list[str] = Field(default_factory=list)
    recommended_resume_emphasis: str = ""
    recommended_cover_letter_angle: str = ""


class JobScore(BaseModel):
    job_id: str
    title_match_score: float = 0.0
    skills_overlap_score: float = 0.0
    domain_match_score: float = 0.0
    seniority_fit_score: float = 0.0
    location_fit_score: float = 0.0
    constraints_fit_score: float = 0.0
    preferred_sector_bonus: float = 0.0
    mismatch_penalty: float = 0.0
    rules_based_score: float = 0.0
    embedding_similarity_score: float = 0.0
    llm_latency_seconds: float = 0.0
    llm_assessment: LLMAssessment = Field(default_factory=LLMAssessment)
    overall_score: float = 0.0
    why_match: str = ""
    missing_skills: list[str] = Field(default_factory=list)
    recommended_resume_emphasis: str = ""
    recommended_cover_letter_angle: str = ""
    disposition: Disposition = Disposition.MAYBE


class RankedJob(BaseModel):
    listing: JobListing
    score: JobScore


class SearchSourceStats(BaseModel):
    source_name: str
    raw_jobs_discovered: int = 0
    jobs_matched: int = 0
    jobs_filtered_out: int = 0


class SearchReport(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    profile_summary: str = ""
    sources_searched: list[str] = Field(default_factory=list)
    queries: list[SearchQuery] = Field(default_factory=list)
    total_jobs_raw_discovered: int = 0
    total_jobs_filtered_out: int = 0
    total_jobs_discovered: int = 0
    total_jobs_ranked: int = 0
    source_stats: list[SearchSourceStats] = Field(default_factory=list)
    top_jobs: list[RankedJob] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
