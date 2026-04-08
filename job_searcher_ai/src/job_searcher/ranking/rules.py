"""Rules-based scoring for profile-job fit."""

from __future__ import annotations

from job_searcher.config import AppConfig
from job_searcher.models import ROLE_FAMILY_SYNONYMS, SENIORITY_HINTS
from job_searcher.schemas import Disposition, JobListing, JobScore, LLMAssessment, UserProfile, WorkMode
from job_searcher.utils.text import keyword_overlap_score, normalize_text, tokenise, unique_preserve_order


def score_job_rules(profile: UserProfile, job: JobListing, config: AppConfig) -> JobScore:
    """Compute interpretable symbolic scores for one job."""

    title_score = _title_match_score(profile, job, config)
    skills_score, missing_skills = _skills_overlap_score(profile, job)
    domain_score = _domain_match_score(profile, job, config)
    seniority_score = _seniority_fit_score(profile, job, config)
    location_score = _location_fit_score(job, config)
    constraints_score = _constraints_fit_score(profile, job, config)
    sector_bonus = _preferred_sector_bonus(job, config)
    mismatch_penalty = _mismatch_penalty(job, config)

    rules_score = round(
        (
            title_score * 0.24
            + skills_score * 0.26
            + domain_score * 0.20
            + seniority_score * 0.10
            + location_score * 0.10
            + constraints_score * 0.10
        )
        + sector_bonus
        - mismatch_penalty,
        2,
    )
    rules_score = max(0.0, min(100.0, rules_score))

    why = _build_why_match(title_score, skills_score, domain_score, location_score, job)
    disposition = _disposition_for_score(rules_score)

    return JobScore(
        job_id=job.id,
        title_match_score=title_score,
        skills_overlap_score=skills_score,
        domain_match_score=domain_score,
        seniority_fit_score=seniority_score,
        location_fit_score=location_score,
        constraints_fit_score=constraints_score,
        preferred_sector_bonus=sector_bonus,
        mismatch_penalty=mismatch_penalty,
        rules_based_score=rules_score,
        llm_assessment=LLMAssessment(),
        overall_score=rules_score,
        why_match=why,
        missing_skills=missing_skills,
        recommended_resume_emphasis=_resume_emphasis(job, profile),
        recommended_cover_letter_angle=_cover_letter_angle(job),
        disposition=disposition,
    )


def _expected_titles(profile: UserProfile, config: AppConfig) -> list[str]:
    titles = unique_preserve_order(config.criteria.target_titles + config.search.job_titles + profile.role_families)
    for family_key, variants in ROLE_FAMILY_SYNONYMS.items():
        label = family_key.replace("_", " ")
        if label in [role.lower() for role in profile.role_families]:
            titles.extend(variants)
    return unique_preserve_order(titles)


def _title_match_score(profile: UserProfile, job: JobListing, config: AppConfig) -> float:
    expected_titles = _expected_titles(profile, config)
    job_title = normalize_text(job.title)
    exact = any(normalize_text(title) == job_title for title in expected_titles)
    if exact:
        return 100.0
    adjacent = any(normalize_text(title) in job_title or job_title in normalize_text(title) for title in expected_titles)
    if adjacent:
        return 88.0
    family_score = 0.0
    for family, variants in ROLE_FAMILY_SYNONYMS.items():
        if any(variant in job_title for variant in variants) and family.replace("_", " ") in [role.lower() for role in profile.role_families]:
            family_score = 84.0
            break
    overlap = keyword_overlap_score(expected_titles, [job.title])
    return max(family_score, overlap)


def _skills_overlap_score(profile: UserProfile, job: JobListing) -> tuple[float, list[str]]:
    profile_skills = unique_preserve_order([skill.name for skill in profile.skills] + profile.tools + profile.programming_languages + profile.domain_strengths)
    job_skills = unique_preserve_order(job.required_skills + job.preferred_skills)
    if not job_skills:
        return 45.0, []
    profile_skill_keys = {normalize_text(skill) for skill in profile_skills}
    job_skill_keys = [normalize_text(skill) for skill in job_skills]
    matched = [skill for skill in job_skill_keys if skill in profile_skill_keys]
    score = round(100.0 * len(matched) / len(job_skill_keys), 2)
    missing = [skill for skill in job.required_skills if normalize_text(skill) not in profile_skill_keys]
    return score, missing[:10]


def _domain_match_score(profile: UserProfile, job: JobListing, config: AppConfig) -> float:
    profile_domains = unique_preserve_order(profile.domain_strengths + profile.industries + config.search.include_keywords + profile.role_families)
    job_domains = unique_preserve_order(job.domain_signals + [job.title])
    if not job_domains:
        return 40.0
    profile_domain_keys = {normalize_text(item) for item in profile_domains}
    matched = [item for item in job_domains if normalize_text(item) in profile_domain_keys]
    return round(100.0 * len(matched) / len(job_domains), 2)


def _seniority_fit_score(profile: UserProfile, job: JobListing, config: AppConfig) -> float:
    target = profile.seniority_hint or config.search.experience_level or "mid"
    target_value = SENIORITY_HINTS.get(target.lower(), 60)
    job_value = 60
    lowered_title = job.title.lower()
    for hint, value in SENIORITY_HINTS.items():
        if hint in lowered_title:
            job_value = value
            break
    gap = abs(target_value - job_value)
    return max(0.0, 100.0 - gap * 1.5)


def _location_fit_score(job: JobListing, config: AppConfig) -> float:
    preferred_locations = [item.lower() for item in unique_preserve_order(config.criteria.locations + config.search.locations)]
    remote_pref = config.criteria.remote_preference.lower()
    job_location = (job.location or "").lower()
    if job.work_mode == WorkMode.REMOTE and remote_pref in {"remote", "hybrid"}:
        return 100.0
    if job.work_mode == WorkMode.HYBRID and remote_pref == "hybrid":
        return 92.0
    if preferred_locations and any(location.lower() in job_location for location in preferred_locations):
        return 90.0
    if not job.location:
        return 55.0
    return 35.0


def _constraints_fit_score(profile: UserProfile, job: JobListing, config: AppConfig) -> float:
    score = 75.0
    description = normalize_text(job.description)
    if "no sponsorship" in description or "must be authorized" in description:
        if config.criteria.visa_constraints:
            score -= 30.0
    if "german" in [language.lower() for language in job.language_requirements] and "german" not in [skill.name.lower() for skill in profile.skills]:
        score -= 15.0
    return max(0.0, score)


def _preferred_sector_bonus(job: JobListing, config: AppConfig) -> float:
    sectors = [item.lower() for item in config.criteria.preferred_industries + config.search.preferred_industries]
    text = normalize_text(" ".join(job.domain_signals + [job.description, job.title]))
    return 10.0 if any(sector in text for sector in sectors) else 0.0


def _mismatch_penalty(job: JobListing, config: AppConfig) -> float:
    penalty = 0.0
    company = normalize_text(job.company)
    title_and_desc = normalize_text(f"{job.title} {job.description}")
    if any(normalize_text(company_name) == company for company_name in config.criteria.blacklist_companies):
        penalty += 50.0
    if any(normalize_text(keyword) in title_and_desc for keyword in config.search.exclude_keywords):
        penalty += 25.0
    unrelated_titles = {"account executive", "recruiter", "sales", "hr", "marketing"}
    if any(term in title_and_desc for term in unrelated_titles):
        penalty += 35.0
    return penalty


def _build_why_match(title_score: float, skills_score: float, domain_score: float, location_score: float, job: JobListing) -> str:
    parts: list[str] = []
    if title_score >= 80:
        parts.append("strong adjacent-title match")
    if skills_score >= 50:
        parts.append("meaningful skill overlap")
    if domain_score >= 50:
        parts.append("clear domain alignment")
    if location_score >= 80:
        parts.append("location or work-mode fit")
    if not parts:
        parts.append(f"some overlap with {job.title}")
    return ", ".join(parts)


def _resume_emphasis(job: JobListing, profile: UserProfile) -> str:
    high_value = unique_preserve_order(job.required_skills[:3] + job.domain_signals[:2])
    if not high_value:
        high_value = profile.domain_strengths[:3]
    return f"Emphasize evidence for {', '.join(high_value)}."


def _cover_letter_angle(job: JobListing) -> str:
    signal = job.domain_signals[0] if job.domain_signals else job.title
    return f"Connect prior delivery experience to {signal} impact at {job.company}."


def _disposition_for_score(score: float) -> Disposition:
    if score >= 78:
        return Disposition.APPLY
    if score >= 55:
        return Disposition.MAYBE
    return Disposition.SKIP
