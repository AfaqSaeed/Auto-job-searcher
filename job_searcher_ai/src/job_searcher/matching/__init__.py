"""Explainable candidate-to-job matching."""

from job_searcher.matching.schemas import (
    CandidateMatchReport,
    ClaimAssessment,
    EvidenceItem,
    MatchStatus,
    RequirementAssessment,
)
from job_searcher.matching.service import build_candidate_match_report

__all__ = [
    "CandidateMatchReport",
    "ClaimAssessment",
    "EvidenceItem",
    "MatchStatus",
    "RequirementAssessment",
    "build_candidate_match_report",
]
