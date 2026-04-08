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
