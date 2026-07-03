"""Prompt builders for local LLM tasks."""

from __future__ import annotations

from job_searcher.schemas import JobListing, UserProfile


PROFILE_SUMMARY_SYSTEM = (
    "You are a careful career analysis assistant. Respond with compact JSON only. "
    "Do not invent employers, locations, or degrees."
)

JOB_FIT_SYSTEM = (
    "You are a hiring-side evaluator. Respond with compact JSON only. "
    "Prefer concrete evidence from the profile and job description."
)

REQUIREMENT_EXTRACTION_SYSTEM = (
    "You extract job requirements for an evidence-based match report. "
    "Respond with compact JSON only. Use atomic, reviewable requirements. "
    "Do not invent requirements. Avoid vague soft skills unless explicitly emphasized."
)

REQUIREMENT_MATCH_SYSTEM = (
    "You assess one candidate requirement using only supplied evidence. "
    "Respond with compact JSON only. Do not invent experience. "
    "Distinguish direct from transferable experience. Avoid inflated confidence. "
    "Do not infer years of experience unless explicitly present."
)

CLAIM_CHECK_SYSTEM = (
    "You verify application claims using only supplied candidate evidence. "
    "Respond with compact JSON only. Do not invent experience. "
    "Flag unsupported or exaggerated claims and propose safer wording when needed. "
    "Distinguish direct from transferable experience. Avoid inflated confidence. "
    "Do not infer years of experience unless explicitly present."
)


def build_profile_summary_prompt(profile_text: str) -> str:
    return f"""
Analyze the user profile below and return JSON with keys:
- summary
- role_families
- search_keywords
- domain_strengths
- industries
- seniority_hint

Profile:
{profile_text}
""".strip()


def build_job_fit_prompt(profile: UserProfile, job: JobListing, rules_score: float) -> str:
    skills = ", ".join(skill.name for skill in profile.skills[:20])
    domains = ", ".join(profile.domain_strengths[:12])
    return f"""
Return JSON with keys:
- fit_label
- why_match
- missing_requirements
- recommended_resume_emphasis
- recommended_cover_letter_angle

Profile summary: {profile.summary or profile.llm_summary or "n/a"}
Profile role families: {", ".join(profile.role_families)}
Profile skills: {skills}
Profile domains: {domains}

Job title: {job.title}
Company: {job.company}
Location: {job.location}
Work mode: {job.work_mode.value}
Required skills: {", ".join(job.required_skills)}
Preferred skills: {", ".join(job.preferred_skills)}
Domain signals: {", ".join(job.domain_signals)}
Description:
{job.description[:3500]}

Rules score: {rules_score}
""".strip()


def build_requirement_extraction_prompt(job: JobListing, max_requirements: int = 15) -> str:
    return f"""
Return JSON with key "requirements" containing up to {max_requirements} concise, atomic requirements.
Prefer explicit required skills, preferred skills, responsibilities, and minimum qualifications.
Exclude vague items unless the job explicitly emphasizes them.

Job title: {job.title}
Company: {job.company}
Required skills: {", ".join(job.required_skills)}
Preferred skills: {", ".join(job.preferred_skills)}
Responsibilities: {", ".join(job.responsibilities)}
Minimum qualifications: {", ".join(job.minimum_qualifications)}
Domain signals: {", ".join(job.domain_signals)}
Description:
{job.description[:5000]}
""".strip()


def build_requirement_match_prompt(requirement: str, evidence: list[dict[str, object]]) -> str:
    return f"""
Return JSON with keys:
- status: one of strong_match, partial_match, missing, uncertain
- explanation: short conservative explanation
- transferable_skills: list of skills or domains that transfer, empty if none
- confidence: number from 0 to 1
- selected_evidence_indices: zero-based list of supplied evidence indices used

Requirement:
{requirement}

Evidence:
{evidence}
""".strip()


def build_claim_check_prompt(claim: str, evidence: list[dict[str, object]]) -> str:
    return f"""
Return JSON with keys:
- supported: true only when the claim is fully supported by the supplied evidence
- explanation: short conservative explanation
- safer_wording: null when supported, otherwise a safer alternative that preserves the core meaning
- confidence: number from 0 to 1
- selected_evidence_indices: zero-based list of supplied evidence indices used

Claim:
{claim}

Evidence:
{evidence}
""".strip()
