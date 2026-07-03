"""Requirement-level candidate assessment."""

from __future__ import annotations

from pydantic import ValidationError

from job_searcher.llm.ollama_client import OllamaClient, OllamaClientError
from job_searcher.llm.prompts import REQUIREMENT_MATCH_SYSTEM, build_requirement_match_prompt
from job_searcher.matching.schemas import EvidenceItem, MatchStatus, RequirementAssessment
from job_searcher.utils.text import tokenise, unique_preserve_order


DEFAULT_STRONG_THRESHOLD = 0.72
DEFAULT_PARTIAL_THRESHOLD = 0.50
DEFAULT_UNCERTAIN_THRESHOLD = 0.30


def assess_requirement(
    requirement: str,
    evidence: list[EvidenceItem],
    client: OllamaClient | None,
    strong_threshold: float = DEFAULT_STRONG_THRESHOLD,
    partial_threshold: float = DEFAULT_PARTIAL_THRESHOLD,
    uncertain_threshold: float = DEFAULT_UNCERTAIN_THRESHOLD,
) -> RequirementAssessment:
    """Assess one requirement using supplied evidence and optional Ollama reasoning."""

    if client is not None:
        llm_assessment = _assess_with_llm(requirement, evidence, client)
        if llm_assessment is not None:
            return llm_assessment
    return _heuristic_assessment(
        requirement,
        evidence,
        strong_threshold=strong_threshold,
        partial_threshold=partial_threshold,
        uncertain_threshold=uncertain_threshold,
    )


def _assess_with_llm(
    requirement: str,
    evidence: list[EvidenceItem],
    client: OllamaClient,
) -> RequirementAssessment | None:
    evidence_payload = [
        {
            "index": index,
            "source_section": item.source_section,
            "similarity": round(item.similarity, 4),
            "text": item.text,
        }
        for index, item in enumerate(evidence)
    ]
    try:
        payload = client.generate_json(
            build_requirement_match_prompt(requirement, evidence_payload),
            system=REQUIREMENT_MATCH_SYSTEM,
        )
        status = _coerce_status(payload.get("status"))
        if status is None:
            return None
        selected_evidence = _select_evidence(evidence, payload.get("selected_evidence_indices"))
        if status in {MatchStatus.MISSING, MatchStatus.UNCERTAIN} and not selected_evidence:
            selected_evidence = evidence[:1]
        return RequirementAssessment.model_validate(
            {
                "requirement": requirement,
                "status": status,
                "evidence": [item.model_dump(mode="json") for item in selected_evidence],
                "explanation": _coerce_string(payload.get("explanation"))
                or _fallback_explanation(requirement, status, selected_evidence),
                "transferable_skills": _coerce_list(payload.get("transferable_skills")),
                "confidence": _coerce_confidence(payload.get("confidence"), selected_evidence),
            }
        )
    except (OllamaClientError, ValidationError, ValueError, TypeError):
        return None


def _heuristic_assessment(
    requirement: str,
    evidence: list[EvidenceItem],
    strong_threshold: float,
    partial_threshold: float,
    uncertain_threshold: float,
) -> RequirementAssessment:
    best = evidence[0] if evidence else None
    best_score = best.similarity if best is not None else 0.0

    if best is None:
        return RequirementAssessment(
            requirement=requirement,
            status=MatchStatus.MISSING,
            evidence=[],
            explanation="No candidate evidence was available for this requirement.",
            transferable_skills=[],
            confidence=0.65,
        )

    if best_score >= strong_threshold:
        status = MatchStatus.STRONG_MATCH
        explanation = (
            f"The strongest evidence directly overlaps with this requirement "
            f"(similarity {best_score:.2f})."
        )
        transferable: list[str] = []
        confidence = min(0.95, max(0.72, best_score))
    elif best_score >= partial_threshold:
        status = MatchStatus.PARTIAL_MATCH
        transferable = _overlap_terms(requirement, evidence)
        explanation = (
            f"The candidate has related evidence, but it does not fully establish the requirement "
            f"(best similarity {best_score:.2f})."
        )
        confidence = min(0.85, max(0.55, best_score))
    elif best_score >= uncertain_threshold:
        status = MatchStatus.UNCERTAIN
        transferable = _overlap_terms(requirement, evidence)
        explanation = (
            f"Evidence is weak or indirect, so this requirement should be reviewed manually "
            f"(best similarity {best_score:.2f})."
        )
        confidence = min(0.65, max(0.35, best_score))
    else:
        status = MatchStatus.MISSING
        transferable = []
        explanation = (
            f"No supplied evidence clearly supports this requirement "
            f"(best similarity {best_score:.2f})."
        )
        confidence = 0.70

    return RequirementAssessment(
        requirement=requirement,
        status=status,
        evidence=evidence,
        explanation=explanation,
        transferable_skills=transferable,
        confidence=confidence,
    )


def _coerce_status(value: object) -> MatchStatus | None:
    if isinstance(value, MatchStatus):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    aliases = {
        "strong": MatchStatus.STRONG_MATCH,
        "strong match": MatchStatus.STRONG_MATCH,
        "strong_match": MatchStatus.STRONG_MATCH,
        "partial": MatchStatus.PARTIAL_MATCH,
        "partial match": MatchStatus.PARTIAL_MATCH,
        "partial_match": MatchStatus.PARTIAL_MATCH,
        "missing": MatchStatus.MISSING,
        "uncertain": MatchStatus.UNCERTAIN,
        "unknown": MatchStatus.UNCERTAIN,
    }
    return aliases.get(normalized)


def _select_evidence(evidence: list[EvidenceItem], raw_indices: object) -> list[EvidenceItem]:
    if not isinstance(raw_indices, list):
        return evidence[:3]
    selected: list[EvidenceItem] = []
    for raw_index in raw_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(evidence):
            selected.append(evidence[index])
        elif 1 <= index <= len(evidence):
            selected.append(evidence[index - 1])
    return selected[:3]


def _coerce_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _coerce_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return unique_preserve_order([str(item).strip() for item in value if str(item).strip()])
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()] if str(value).strip() else []


def _coerce_confidence(value: object, evidence: list[EvidenceItem]) -> float:
    fallback = evidence[0].similarity if evidence else 0.5
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(0.0, min(1.0, numeric))


def _fallback_explanation(requirement: str, status: MatchStatus, evidence: list[EvidenceItem]) -> str:
    if evidence:
        return f"Assessment for '{requirement}' is {status.value} based on supplied evidence only."
    return f"Assessment for '{requirement}' is {status.value}; no supporting evidence was selected."


def _overlap_terms(requirement: str, evidence: list[EvidenceItem]) -> list[str]:
    ignored = {"with", "from", "that", "this", "have", "using", "build", "built", "role", "work"}
    requirement_tokens = {token for token in tokenise(requirement) if len(token) > 2 and token not in ignored}
    evidence_tokens = {
        token
        for item in evidence
        for token in tokenise(item.text)
        if len(token) > 2 and token not in ignored
    }
    return sorted(requirement_tokens & evidence_tokens)[:8]
