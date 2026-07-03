"""Application claim support checking."""

from __future__ import annotations

from pydantic import ValidationError

from job_searcher.llm.ollama_client import OllamaClient, OllamaClientError
from job_searcher.llm.prompts import CLAIM_CHECK_SYSTEM, build_claim_check_prompt
from job_searcher.matching.evidence import retrieve_evidence
from job_searcher.matching.schemas import ClaimAssessment, EvidenceItem
from job_searcher.ranking.embeddings import EmbeddingBackend
from job_searcher.utils.text import tokenise


SUPPORTED_THRESHOLD = 0.70
PARTIAL_THRESHOLD = 0.45


def check_claim(
    claim: str,
    evidence_items: list[EvidenceItem],
    backend: EmbeddingBackend,
    client: OllamaClient | None,
) -> ClaimAssessment:
    """Check whether an application claim is supported by candidate evidence."""

    strongest_evidence = retrieve_evidence(claim, evidence_items, backend, top_k=3)
    if client is not None:
        llm_assessment = _check_with_llm(claim, strongest_evidence, client)
        if llm_assessment is not None:
            return llm_assessment
    return _heuristic_claim_check(claim, strongest_evidence)


def _check_with_llm(
    claim: str,
    evidence: list[EvidenceItem],
    client: OllamaClient,
) -> ClaimAssessment | None:
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
            build_claim_check_prompt(claim, evidence_payload),
            system=CLAIM_CHECK_SYSTEM,
        )
        selected_evidence = _select_evidence(evidence, payload.get("selected_evidence_indices"))
        supported = bool(payload.get("supported", False))
        safer_wording = _coerce_optional_string(payload.get("safer_wording"))
        if not supported and not safer_wording:
            safer_wording = _build_safer_wording(claim, selected_evidence)
        return ClaimAssessment.model_validate(
            {
                "claim": claim,
                "supported": supported,
                "explanation": _coerce_string(payload.get("explanation"))
                or _fallback_explanation(claim, supported, selected_evidence),
                "evidence": [item.model_dump(mode="json") for item in selected_evidence],
                "safer_wording": None if supported else safer_wording,
                "confidence": _coerce_confidence(payload.get("confidence"), selected_evidence),
            }
        )
    except (OllamaClientError, ValidationError, ValueError, TypeError):
        return None


def _heuristic_claim_check(claim: str, evidence: list[EvidenceItem]) -> ClaimAssessment:
    best = evidence[0] if evidence else None
    if best is None:
        return ClaimAssessment(
            claim=claim,
            supported=False,
            explanation="No candidate evidence was available to support this claim.",
            evidence=[],
            safer_wording=_build_safer_wording(claim, []),
            confidence=0.70,
        )

    key_terms = _claim_terms(claim)
    evidence_terms = {token for item in evidence for token in tokenise(item.text)}
    covered_terms = key_terms & evidence_terms
    coverage = len(covered_terms) / len(key_terms) if key_terms else 0.0
    supported = best.similarity >= SUPPORTED_THRESHOLD and coverage >= 0.60

    if supported:
        explanation = (
            f"The claim is supported by direct evidence "
            f"(best similarity {best.similarity:.2f}, key-term coverage {coverage:.2f})."
        )
        safer_wording = None
        confidence = min(0.92, max(0.72, best.similarity))
    elif best.similarity >= PARTIAL_THRESHOLD or coverage > 0:
        missing_terms = sorted(key_terms - covered_terms)[:6]
        missing_text = ", ".join(missing_terms) if missing_terms else "some specific details"
        explanation = (
            f"Related evidence exists, but the claim is not fully supported. "
            f"Missing direct evidence for: {missing_text}."
        )
        safer_wording = _build_safer_wording(claim, evidence)
        confidence = min(0.82, max(0.50, best.similarity))
    else:
        explanation = (
            f"No supplied evidence clearly supports the claim "
            f"(best similarity {best.similarity:.2f})."
        )
        safer_wording = _build_safer_wording(claim, evidence)
        confidence = 0.72

    return ClaimAssessment(
        claim=claim,
        supported=supported,
        explanation=explanation,
        evidence=evidence,
        safer_wording=safer_wording,
        confidence=confidence,
    )


def _claim_terms(claim: str) -> set[str]:
    ignored = {
        "have",
        "with",
        "using",
        "built",
        "build",
        "developed",
        "worked",
        "experience",
        "systems",
        "system",
        "role",
        "work",
        "and",
        "the",
        "for",
    }
    return {token for token in tokenise(claim) if len(token) > 2 and token not in ignored}


def _build_safer_wording(claim: str, evidence: list[EvidenceItem]) -> str:
    claim_focus = _claim_focus(claim)
    if evidence:
        strongest = evidence[0].text.rstrip(".")
        return (
            f"My background includes {strongest}, which provides a foundation for work related to {claim_focus}."
        )
    return f"I am interested in applying my documented background to work related to {claim_focus}."


def _claim_focus(claim: str) -> str:
    terms = sorted(_claim_terms(claim))
    if not terms:
        return "this area"
    return ", ".join(terms[:6])


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


def _coerce_optional_string(value: object) -> str | None:
    cleaned = _coerce_string(value)
    return cleaned or None


def _coerce_confidence(value: object, evidence: list[EvidenceItem]) -> float:
    fallback = evidence[0].similarity if evidence else 0.5
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(0.0, min(1.0, numeric))


def _fallback_explanation(claim: str, supported: bool, evidence: list[EvidenceItem]) -> str:
    if supported:
        return f"The claim '{claim}' is supported by the selected evidence."
    if evidence:
        return f"The selected evidence does not fully support the claim '{claim}'."
    return f"No evidence was selected for the claim '{claim}'."
