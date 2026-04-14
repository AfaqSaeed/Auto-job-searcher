"""Source payload to JobListing parsers."""

from __future__ import annotations

from bs4 import BeautifulSoup

from job_searcher.parsing.normalization import (
    extract_domain_signals,
    extract_language_requirements,
    extract_skill_mentions,
    infer_work_mode,
    normalize_job_listing,
)
from job_searcher.schemas import JobListing, WorkMode
from job_searcher.utils.text import extract_bullets
from job_searcher.utils.urls import join_url


SECTION_KEYWORDS = {
    "responsibilities": ["responsibilities", "what you will do", "what you'll do"],
    "minimum_qualifications": ["minimum qualifications", "requirements", "must have", "basic qualifications"],
    "preferred_qualifications": ["preferred qualifications", "nice to have", "preferred skills"],
}


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text("\n", strip=True)


def parse_html_sections(html: str) -> dict[str, list[str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    sections = {"responsibilities": [], "minimum_qualifications": [], "preferred_qualifications": []}
    for heading in soup.find_all(["h2", "h3", "strong", "b"]):
        heading_text = heading.get_text(" ", strip=True).lower()
        sibling_texts: list[str] = []
        for sibling in heading.find_all_next(limit=8):
            if sibling.name in {"h2", "h3"} and sibling != heading:
                break
            text = sibling.get_text(" ", strip=True)
            if text:
                sibling_texts.append(text)
        for key, keywords in SECTION_KEYWORDS.items():
            if any(keyword in heading_text for keyword in keywords):
                sections[key].extend(sibling_texts)
    return sections


def parse_greenhouse_job(payload: dict) -> JobListing:
    description_html = payload.get("content", "")
    description_text = html_to_text(description_html)
    sections = parse_html_sections(description_html)
    combined_skills = extract_skill_mentions(description_text)
    return normalize_job_listing(
        JobListing(
            id=str(payload.get("id")),
            source="greenhouse",
            source_url=payload.get("absolute_url") or payload.get("url") or "",
            title=payload.get("title", "Unknown title"),
            company=payload.get("company_name") or payload.get("company") or payload.get("board_token", "Unknown company"),
            location=(payload.get("location") or {}).get("name") if isinstance(payload.get("location"), dict) else payload.get("location"),
            work_mode=infer_work_mode(description_text),
            description=description_text,
            required_skills=combined_skills,
            preferred_skills=sections["preferred_qualifications"],
            responsibilities=sections["responsibilities"] or extract_bullets(description_text)[:6],
            minimum_qualifications=sections["minimum_qualifications"],
            domain_signals=extract_domain_signals(description_text),
            application_url=payload.get("absolute_url") or payload.get("url"),
            date_posted=payload.get("updated_at") or payload.get("created_at"),
            language_requirements=extract_language_requirements(description_text),
            raw_payload=payload,
        )
    )


def parse_lever_job(payload: dict) -> JobListing:
    description_parts = [payload.get("description", ""), payload.get("descriptionPlain", ""), payload.get("additional", "")]
    for item in payload.get("lists", []):
        description_parts.append(item.get("text", ""))
        description_parts.append(item.get("content", ""))
    description_html = "\n".join(part for part in description_parts if part)
    description_text = html_to_text(description_html)
    responsibilities = [item.get("content", "") for item in payload.get("lists", []) if "respons" in item.get("text", "").lower()]
    minimum = [item.get("content", "") for item in payload.get("lists", []) if item.get("text", "").lower() in {"requirements", "basic qualifications"}]
    preferred = [item.get("content", "") for item in payload.get("lists", []) if "preferred" in item.get("text", "").lower()]
    return normalize_job_listing(
        JobListing(
            id=str(payload.get("id")),
            source="lever",
            source_url=payload.get("hostedUrl") or payload.get("applyUrl") or "",
            title=payload.get("text", "Unknown title"),
            company=payload.get("company") or payload.get("categories", {}).get("team", "Unknown company"),
            location=payload.get("categories", {}).get("location"),
            work_mode=infer_work_mode(payload.get("categories", {}).get("location", ""), description_text),
            description=description_text,
            required_skills=extract_skill_mentions(description_text),
            preferred_skills=preferred,
            responsibilities=responsibilities or extract_bullets(description_text)[:6],
            minimum_qualifications=minimum,
            domain_signals=extract_domain_signals(description_text),
            application_url=payload.get("applyUrl") or payload.get("hostedUrl"),
            date_posted=payload.get("createdAt") or payload.get("updatedAt"),
            language_requirements=extract_language_requirements(description_text),
            raw_payload=payload,
        )
    )


def parse_ashby_job(payload: dict, board_name: str | None = None) -> JobListing:
    job_url = payload.get("jobUrl") or payload.get("applyUrl") or payload.get("url") or ""
    description_parts = [
        payload.get("description") or "",
        payload.get("descriptionHtml") or "",
        payload.get("content") or "",
        payload.get("jobDescription") or "",
    ]
    for section in payload.get("jobPostSections", []) or []:
        description_parts.append(section.get("content") or "")
    description_html = "\n".join(part for part in description_parts if part)
    description_text = html_to_text(description_html)
    location = (
        payload.get("location")
        or payload.get("jobLocation")
        or payload.get("secondaryLocation")
        or (payload.get("locationName") if isinstance(payload.get("locationName"), str) else None)
    )
    return normalize_job_listing(
        JobListing(
            id=str(payload.get("id") or payload.get("jobId") or job_url),
            source="ashby",
            source_url=job_url,
            title=payload.get("title") or payload.get("jobTitle") or "Unknown title",
            company=payload.get("companyName") or board_name or "Unknown company",
            location=location,
            work_mode=infer_work_mode(location or "", description_text),
            description=description_text,
            required_skills=extract_skill_mentions(description_text),
            preferred_skills=[],
            responsibilities=extract_bullets(description_text)[:6],
            minimum_qualifications=[],
            domain_signals=extract_domain_signals(description_text),
            application_url=payload.get("applyUrl") or job_url,
            date_posted=payload.get("postedDate") or payload.get("publishedAt") or payload.get("updatedAt"),
            language_requirements=extract_language_requirements(description_text),
            raw_payload=payload,
        )
    )


def parse_static_job_page(url: str, html: str, company: str | None = None, source: str = "static_company_pages") -> JobListing:
    soup = BeautifulSoup(html or "", "html.parser")
    title = (soup.find("h1") or soup.find("title") or soup.find("h2"))
    title_text = title.get_text(" ", strip=True) if title else "Unknown title"
    location_meta = soup.find(attrs={"class": lambda value: value and "location" in str(value).lower()})
    location = location_meta.get_text(" ", strip=True) if location_meta else None
    description_text = soup.get_text("\n", strip=True)
    apply_link = soup.find("a", href=True, string=lambda value: value and "apply" in value.lower())
    return normalize_job_listing(
        JobListing(
            id=url,
            source=source,
            source_url=url,
            title=title_text,
            company=company or join_url(url, "/").split("//")[-1].split("/")[0],
            location=location,
            work_mode=infer_work_mode(location or "", description_text),
            description=description_text,
            required_skills=extract_skill_mentions(description_text),
            preferred_skills=[],
            responsibilities=extract_bullets(description_text)[:6],
            minimum_qualifications=[],
            domain_signals=extract_domain_signals(description_text),
            application_url=join_url(url, apply_link.get("href")) if apply_link else url,
            language_requirements=extract_language_requirements(description_text),
            raw_payload={"html_length": len(html)},
        )
    )
