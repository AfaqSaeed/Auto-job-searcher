"""Schemas for explainable candidate-to-role matching."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown fields in matching artifacts."""

    model_config = ConfigDict(extra="forbid")


class MatchStatus(str, Enum):
    STRONG_MATCH = "strong_match"
    PARTIAL_MATCH = "partial_match"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


class EvidenceItem(StrictModel):
    text: str = Field(min_length=1)
    source_section: str = Field(min_length=1)
    similarity: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("text", "source_section")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned


class RequirementAssessment(StrictModel):
    requirement: str = Field(min_length=1)
    status: MatchStatus
    evidence: list[EvidenceItem] = Field(default_factory=list)
    explanation: str = Field(min_length=1)
    transferable_skills: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("requirement", "explanation")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("transferable_skills")
    @classmethod
    def _strip_transferable_skills(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class ClaimAssessment(StrictModel):
    claim: str = Field(min_length=1)
    supported: bool
    explanation: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    safer_wording: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("claim", "explanation")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("safer_wording")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CandidateMatchReport(StrictModel):
    candidate_name: str | None = None
    job_title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    overall_score: float = Field(ge=0.0, le=100.0)
    assessments: list[RequirementAssessment] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    unsupported_claims: list[ClaimAssessment] = Field(default_factory=list)
    recommendation: str = Field(min_length=1)

    @field_validator("candidate_name", mode="before")
    @classmethod
    def _strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("job_title", "company", "recommendation")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("strengths", "gaps")
    @classmethod
    def _strip_text_list(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]
