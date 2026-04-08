"""Generate search queries from a structured user profile."""

from __future__ import annotations

from job_searcher.config import AppConfig
from job_searcher.queries.dedupe import dedupe_queries
from job_searcher.queries.expansion import expand_domain_terms, expand_role_titles, german_variants
from job_searcher.schemas import SearchQuery, UserProfile
from job_searcher.utils.text import tokenise, unique_preserve_order


def generate_search_queries(profile: UserProfile, config: AppConfig) -> list[SearchQuery]:
    """Create high-signal job search queries from the profile and user preferences."""

    titles = expand_role_titles(
        unique_preserve_order(config.criteria.target_titles + config.search.job_titles + profile.role_families),
        profile.role_families,
    )
    domains = expand_domain_terms(profile.domain_strengths, config.search.include_keywords)
    skills = unique_preserve_order([skill.name for skill in profile.skills] + profile.tools + profile.programming_languages)
    locations = unique_preserve_order(config.criteria.locations + config.search.locations)

    queries: list[SearchQuery] = []

    for title in titles[:15]:
        queries.append(_query(text=title, title=title, rationale="exact title"))
        for domain in domains[:8]:
            queries.append(_query(text=f"{title} {domain}", title=title, rationale="title + domain"))
        for skill in skills[:6]:
            queries.append(_query(text=f"{title} {skill}", title=title, rationale="title + skill"))
        for location in locations[:6]:
            queries.append(_query(text=f"{title} {location}", title=title, location=location, rationale="title + location"))

    for title in titles[:10]:
        for domain in domains[:6]:
            for location in locations[:4]:
                queries.append(
                    _query(
                        text=f"{title} {domain} {location}",
                        title=title,
                        location=location,
                        rationale="title + domain + location",
                    )
                )

    broader = [
        "computer vision engineer autonomous driving germany",
        "multimodal perception engineer robotics",
        "3d vision engineer mapping slam",
        "ai engineer generative perception automotive",
        "ml engineer edge deployment computer vision",
        "research engineer visual perception",
    ]
    queries.extend(_query(text=item, rationale="broader concept combination") for item in broader)

    if config.search.include_german_variants:
        german_queries: list[SearchQuery] = []
        for title in titles[:10]:
            for variant in german_variants(title):
                if variant != title:
                    german_queries.append(_query(text=variant, title=title, language="de", rationale="german title variant"))
        queries.extend(german_queries)

    deduped = dedupe_queries(queries)
    return deduped[: config.search.query_limit]


def _query(
    text: str,
    title: str | None = None,
    location: str | None = None,
    language: str = "en",
    rationale: str | None = None,
) -> SearchQuery:
    return SearchQuery(
        text=" ".join(text.split()),
        title=title,
        location=location,
        language=language,
        rationale=rationale,
        terms=tokenise(text),
    )
