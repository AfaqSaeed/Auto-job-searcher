"""Discover likely target companies and public ATS boards from the user's real profile."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_searcher.config import AppConfig, load_config, resolve_project_root
from job_searcher.llm.ollama_client import OllamaClient
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.profile.summarize import apply_insights, summarize_profile
from job_searcher.schemas import UserProfile
from job_searcher.utils.text import unique_preserve_order

try:
    from ddgs import DDGS
except ImportError as exc:  # pragma: no cover - import guard for direct script use
    raise SystemExit("Please install dependencies first: pip install ddgs requests pandas") from exc


LOGGER = logging.getLogger("job_board_finder")

DEFAULT_QUERY_TEMPLATES = (
    "{keyword} companies {region}",
    "{keyword} jobs {region}",
    "{keyword} company careers {region}",
    "{keyword} robotics company {region}",
    "{keyword} ai company {region}",
)

DISCOVERY_QUERIES = (
    "site:boards.greenhouse.io computer vision Germany",
    "site:job-boards.eu.greenhouse.io robotics Germany",
    "site:boards.greenhouse.io multimodal ai Europe",
    "site:jobs.lever.co computer vision Germany",
    "site:jobs.ashbyhq.com robotics Germany",
    "top robotics startups Germany",
    "top computer vision companies Germany",
    "slam companies Europe",
)

COMMON_NON_COMPANY_WORDS = {
    "jobs",
    "careers",
    "career",
    "hiring",
    "linkedin",
    "indeed",
    "glassdoor",
    "germany",
    "europe",
    "remote",
    "team",
    "page",
    "blog",
    "news",
    "startup",
    "startups",
    "company",
    "companies",
    "vision",
    "robotics",
    "ai",
    "driving",
    "munich",
    "berlin",
    "hamburg",
    "stuttgart",
    "job",
    "boards",
    "greenhouse",
    "lever",
}

DEFAULT_MANUAL_SEEDS = (
    "NavVis",
    "Agile Robots",
    "NEURA Robotics",
    "Franka Robotics",
    "KUKA",
    "Bosch",
    "Continental",
    "Cariad",
    "Aptiv",
    "Innoviz",
    "Wayve",
    "Applied Intuition",
    "Tesla",
    "NVIDIA",
    "Intrinsic",
    "ANYbotics",
)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_board_finder",
        description="Discover relevant companies and public ATS boards from the user's profile.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root containing config/settings.yaml and data/profile_master.md",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to settings.yaml",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("data/profile_master.md"),
        help="Main profile markdown file relative to project root unless absolute",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        nargs="*",
        default=[],
        help="Optional supplemental resume files",
    )
    parser.add_argument(
        "--max-search-results",
        type=int,
        default=15,
        help="Max DDGS results per query",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Parallel workers for ATS checks",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Output directory relative to project root unless absolute",
    )
    return parser


def resolve_input_path(project_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else (project_root / value)


def derive_profile_keywords_and_regions(profile: UserProfile, config: AppConfig) -> tuple[list[str], list[str]]:
    """Build keyword and region lists from an already-structured profile."""

    keyword_candidates = (
        profile.role_families
        + profile.domain_strengths
        + profile.search_keywords
        + [skill.name for skill in profile.skills]
        + profile.tools
        + profile.programming_languages
        + profile.industries
    )
    keywords = [item for item in unique_preserve_order(keyword_candidates) if len(item.strip()) >= 3][:14]

    regions = unique_preserve_order(
        config.search.target_countries
        + config.search.locations
        + config.criteria.locations
    )
    if not regions:
        regions = ["Germany", "Europe"]
    return keywords, regions


def load_profile_keywords(
    project_root: Path,
    profile_path: Path,
    supplemental_files: list[Path],
    config_path: Path | None,
) -> tuple[UserProfile, AppConfig, list[str], list[str]]:
    config = load_config(config_path=config_path, project_root=project_root)
    document = read_profile_document(
        resolve_input_path(project_root, profile_path),
        [resolve_input_path(project_root, path) for path in supplemental_files],
    )
    extracted = extract_profile(document)
    client = OllamaClient(config.ollama) if config.ollama.enabled else None
    profile = apply_insights(extracted, summarize_profile(extracted, client))
    keywords, regions = derive_profile_keywords_and_regions(profile, config)
    return profile, config, keywords, regions


def build_search_queries(keywords: list[str], regions: list[str], query_limit: int) -> list[str]:
    queries: list[str] = []
    for keyword in keywords:
        for region in regions:
            for template in DEFAULT_QUERY_TEMPLATES:
                queries.append(template.format(keyword=keyword, region=region))
    queries.extend(DISCOVERY_QUERIES)
    return unique_preserve_order(queries)[:query_limit]


def search_web(queries: list[str], max_results_per_query: int) -> tuple[list[dict[str, str]], list[str]]:
    results: list[dict[str, str]] = []
    warnings: list[str] = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                hits = ddgs.text(query, max_results=max_results_per_query)
                for hit in hits:
                    results.append(
                        {
                            "query": query,
                            "title": hit.get("title", ""),
                            "href": hit.get("href", ""),
                            "body": hit.get("body", ""),
                        }
                    )
            except Exception as exc:  # pragma: no cover - network dependent
                message = f"Web search failed for query '{query}': {exc}"
                LOGGER.warning(message)
                warnings.append(message)
            time.sleep(0.15)

    return results, warnings


def clean_company_candidate(name: str) -> str | None:
    if not name:
        return None

    cleaned = re.sub(r"\s+", " ", name).strip(" -|–—:,.")
    if len(cleaned) < 2 or len(cleaned) > 80:
        return None
    if re.fullmatch(r"[0-9\W_]+", cleaned):
        return None

    lowered = cleaned.lower()
    if lowered in COMMON_NON_COMPANY_WORDS:
        return None
    if lowered.endswith(("jobs", "careers", "career")):
        return None
    return cleaned


def should_consider_domain_root(domain_root: str) -> bool:
    if domain_root in COMMON_NON_COMPANY_WORDS:
        return False
    if len(domain_root) < 2:
        return False
    if domain_root.isdigit():
        return False
    return True


def extract_company_names_from_result(result: dict[str, str]) -> set[str]:
    candidates: set[str] = set()

    title = result.get("title", "")
    href = result.get("href", "")
    body = result.get("body", "")

    for part in re.split(r"[|\-–—:•/]", title):
        candidate = clean_company_candidate(part)
        if candidate:
            candidates.add(candidate)

    if href:
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
            domain_root = host.split(".")[0]
            if should_consider_domain_root(domain_root):
                candidates.add(domain_root)
        except Exception:
            LOGGER.debug("Failed to parse host for search result: %s", href)

    capitalized_phrase_re = r"\b([A-Z][A-Za-z0-9&\-.]+(?:\s+[A-Z][A-Za-z0-9&\-.]+){0,3})\b"
    for match in re.findall(capitalized_phrase_re, body):
        candidate = clean_company_candidate(match)
        if candidate:
            candidates.add(candidate)

    return candidates


def normalize_company_name(name: str) -> str:
    normalized = name.strip()
    normalized = re.sub(
        r"\b(GmbH|Inc|Ltd|LLC|AG|SE|PLC|Technologies|Technology|Systems|Group|Corp|Company)\b",
        "",
        normalized,
        flags=re.I,
    )
    normalized = re.sub(r"[^A-Za-z0-9\s\-&]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def generate_slug_variants(company_name: str) -> list[str]:
    base = normalize_company_name(company_name).lower()
    if not base:
        return []

    variants = [
        base.replace(" ", "-"),
        base.replace(" ", ""),
        base.replace("&", "and").replace(" ", "-"),
        base.replace("&", "and").replace(" ", ""),
    ]
    stripped = re.sub(r"[^a-z0-9]", "", base)
    if stripped:
        variants.append(stripped)
    return unique_preserve_order([variant for variant in variants if variant])


def safe_get(url: str, timeout_seconds: int) -> requests.Response | None:
    try:
        return requests.get(url, timeout=timeout_seconds, allow_redirects=True)
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        LOGGER.debug("GET failed for %s: %s", url, exc)
        return None


def test_greenhouse_slug(slug: str, timeout_seconds: int, sleep_between_requests: float) -> dict[str, Any]:
    page_urls = [
        f"https://boards.greenhouse.io/{slug}",
        f"https://job-boards.greenhouse.io/{slug}",
        f"https://job-boards.eu.greenhouse.io/{slug}",
    ]
    found_url: str | None = None
    page_status: int | None = None

    for page_url in page_urls:
        response = safe_get(page_url, timeout_seconds)
        time.sleep(sleep_between_requests)
        if response is None:
            continue
        page_status = response.status_code
        if response.status_code == 200 and "greenhouse" in response.url.lower():
            found_url = response.url
            break

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    api_response = safe_get(api_url, timeout_seconds)
    time.sleep(sleep_between_requests)

    api_ok = False
    api_jobs_count: int | None = None
    api_status = api_response.status_code if api_response is not None else None

    if api_response is not None and api_response.status_code == 200:
        api_ok = True
        try:
            data = api_response.json()
            api_jobs_count = len(data.get("jobs", []))
        except Exception as exc:  # pragma: no cover - malformed remote payload
            LOGGER.debug("Failed to decode Greenhouse API response for %s: %s", slug, exc)

    return {
        "slug": slug,
        "greenhouse_url": found_url,
        "greenhouse_status": page_status,
        "api_url": api_url,
        "api_status": api_status,
        "api_ok": api_ok,
        "api_jobs_count": api_jobs_count,
    }


def test_lever_slug(slug: str, timeout_seconds: int, sleep_between_requests: float) -> dict[str, Any]:
    page_urls = [
        f"https://jobs.lever.co/{slug}",
        f"https://jobs.eu.lever.co/{slug}",
    ]
    found_url: str | None = None
    page_status: int | None = None

    for page_url in page_urls:
        response = safe_get(page_url, timeout_seconds)
        time.sleep(sleep_between_requests)
        if response is None:
            continue
        page_status = response.status_code
        if response.status_code == 200 and "lever.co" in response.url.lower():
            found_url = response.url
            break

    api_urls = [
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
        f"https://api.eu.lever.co/v0/postings/{slug}?mode=json",
    ]
    api_ok = False
    api_status: int | None = None
    api_jobs_count: int | None = None
    api_url_used: str | None = None

    for api_url in api_urls:
        api_response = safe_get(api_url, timeout_seconds)
        time.sleep(sleep_between_requests)
        if api_response is None:
            continue
        api_status = api_response.status_code
        api_url_used = api_url
        if api_response.status_code == 200:
            api_ok = True
            try:
                data = api_response.json()
                api_jobs_count = len(data) if isinstance(data, list) else None
            except Exception as exc:  # pragma: no cover - malformed remote payload
                LOGGER.debug("Failed to decode Lever API response for %s: %s", slug, exc)
            break

    return {
        "slug": slug,
        "lever_url": found_url,
        "lever_status": page_status,
        "api_url": api_url_used,
        "api_status": api_status,
        "api_ok": api_ok,
        "api_jobs_count": api_jobs_count,
    }


def test_ashby_slug(slug: str, timeout_seconds: int, sleep_between_requests: float) -> dict[str, Any]:
    page_urls = [
        f"https://jobs.ashbyhq.com/{slug}",
    ]
    found_url: str | None = None
    page_status: int | None = None

    for page_url in page_urls:
        response = safe_get(page_url, timeout_seconds)
        time.sleep(sleep_between_requests)
        if response is None:
            continue
        page_status = response.status_code
        if response.status_code == 200 and "ashbyhq.com" in response.url.lower():
            found_url = response.url
            break

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    api_response = safe_get(api_url, timeout_seconds)
    time.sleep(sleep_between_requests)

    api_ok = False
    api_jobs_count: int | None = None
    api_status = api_response.status_code if api_response is not None else None

    if api_response is not None and api_response.status_code == 200:
        api_ok = True
        try:
            data = api_response.json()
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            api_jobs_count = len(jobs)
        except Exception as exc:  # pragma: no cover - malformed remote payload
            LOGGER.debug("Failed to decode Ashby API response for %s: %s", slug, exc)

    return {
        "slug": slug,
        "ashby_url": found_url,
        "ashby_status": page_status,
        "api_url": api_url,
        "api_status": api_status,
        "api_ok": api_ok,
        "api_jobs_count": api_jobs_count,
    }


def _best_ats_hit(
    slug_variants: list[str],
    timeout_seconds: int,
    sleep_between_requests: float,
    tester,
    url_key: str,
) -> dict[str, Any] | None:
    for slug in slug_variants[:5]:
        hit = tester(slug, timeout_seconds, sleep_between_requests)
        if hit.get(url_key) or hit.get("api_ok"):
            return hit
    return None


def check_company_ats(
    company: str,
    timeout_seconds: int,
    sleep_between_requests: float,
) -> dict[str, Any]:
    start = time.time()
    slug_variants = generate_slug_variants(company)
    greenhouse_hit = _best_ats_hit(
        slug_variants, timeout_seconds, sleep_between_requests, test_greenhouse_slug, "greenhouse_url"
    )
    lever_hit = _best_ats_hit(
        slug_variants, timeout_seconds, sleep_between_requests, test_lever_slug, "lever_url"
    )
    ashby_hit = _best_ats_hit(
        slug_variants, timeout_seconds, sleep_between_requests, test_ashby_slug, "ashby_url"
    )

    elapsed = time.time() - start
    return {
        "company": company,
        "slug_variants": json.dumps(slug_variants, ensure_ascii=False),
        "greenhouse_slug": greenhouse_hit["slug"] if greenhouse_hit else None,
        "greenhouse_url": greenhouse_hit["greenhouse_url"] if greenhouse_hit else None,
        "greenhouse_status": greenhouse_hit["greenhouse_status"] if greenhouse_hit else None,
        "greenhouse_api_status": greenhouse_hit["api_status"] if greenhouse_hit else None,
        "greenhouse_api_ok": greenhouse_hit["api_ok"] if greenhouse_hit else False,
        "greenhouse_jobs_count": greenhouse_hit["api_jobs_count"] if greenhouse_hit else None,
        "lever_slug": lever_hit["slug"] if lever_hit else None,
        "lever_url": lever_hit["lever_url"] if lever_hit else None,
        "lever_status": lever_hit["lever_status"] if lever_hit else None,
        "lever_api_status": lever_hit["api_status"] if lever_hit else None,
        "lever_api_ok": lever_hit["api_ok"] if lever_hit else False,
        "lever_jobs_count": lever_hit["api_jobs_count"] if lever_hit else None,
        "ashby_slug": ashby_hit["slug"] if ashby_hit else None,
        "ashby_url": ashby_hit["ashby_url"] if ashby_hit else None,
        "ashby_status": ashby_hit["ashby_status"] if ashby_hit else None,
        "ashby_api_status": ashby_hit["api_status"] if ashby_hit else None,
        "ashby_api_ok": ashby_hit["api_ok"] if ashby_hit else False,
        "ashby_jobs_count": ashby_hit["api_jobs_count"] if ashby_hit else None,
        "elapsed_seconds": round(elapsed, 2),
    }


def enrich_companies_parallel(
    company_names: set[str],
    timeout_seconds: int,
    sleep_between_requests: float,
    max_workers: int,
) -> list[dict[str, Any]]:
    companies = sorted(company_names)
    rows: list[dict[str, Any]] = []
    start_all = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_company_ats, company, timeout_seconds, sleep_between_requests): company for company in companies
        }
        for future in as_completed(futures):
            company = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("ATS check failed for %s: %s", company, exc)
                rows.append(
                    {
                        "company": company,
                        "slug_variants": "[]",
                        "greenhouse_slug": None,
                        "greenhouse_url": None,
                        "greenhouse_status": None,
                        "greenhouse_api_status": None,
                        "greenhouse_api_ok": False,
                        "greenhouse_jobs_count": None,
                        "lever_slug": None,
                        "lever_url": None,
                        "lever_status": None,
                        "lever_api_status": None,
                        "lever_api_ok": False,
                        "lever_jobs_count": None,
                        "ashby_slug": None,
                        "ashby_url": None,
                        "ashby_status": None,
                        "ashby_api_status": None,
                        "ashby_api_ok": False,
                        "ashby_jobs_count": None,
                        "elapsed_seconds": None,
                    }
                )

    total_elapsed = time.time() - start_all
    avg_time = total_elapsed / max(len(companies), 1)
    LOGGER.info("Finished ATS checks in %.1fs", total_elapsed)
    LOGGER.info("Average wall-clock time per company: %.2fs using %s workers", avg_time, max_workers)
    return rows


def score_company(name: str, keywords: list[str]) -> int:
    lowered = name.lower()
    term_hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
    heuristic_hits = sum(
        1 for term in ("robot", "vision", "autonomous", "mapping", "slam", "ai", "lidar", "perception") if term in lowered
    )
    return term_hits + heuristic_hits


def discover_companies(
    profile: UserProfile,
    config: AppConfig,
    keywords: list[str],
    regions: list[str],
    max_search_results_per_query: int,
    max_workers: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    queries = build_search_queries(keywords, regions, config.search.query_limit)
    LOGGER.info("Using %s profile-derived keywords", len(keywords))
    LOGGER.info("Running %s search queries", len(queries))

    search_results, search_warnings = search_web(queries, max_search_results_per_query)
    LOGGER.info("Search results collected: %s", len(search_results))

    company_names: set[str] = set()
    for result in search_results:
        extracted = extract_company_names_from_result(result)
        for company in extracted:
            normalized = normalize_company_name(company)
            if len(normalized) >= 2:
                company_names.add(normalized)

    for seed in DEFAULT_MANUAL_SEEDS:
        company_names.add(normalize_company_name(seed))

    LOGGER.info("Candidate companies found: %s", len(company_names))

    rows = enrich_companies_parallel(
        company_names,
        timeout_seconds=config.scraping.request_timeout_seconds,
        sleep_between_requests=config.scraping.rate_limit_seconds,
        max_workers=max_workers,
    )

    dataframe = pd.DataFrame(rows)
    dataframe["relevance_score"] = dataframe["company"].apply(lambda company: score_company(company, keywords))
    dataframe["has_greenhouse"] = dataframe["greenhouse_url"].notna() | dataframe["greenhouse_api_ok"].fillna(False)
    dataframe["has_lever"] = dataframe["lever_url"].notna() | dataframe["lever_api_ok"].fillna(False)
    dataframe["has_ashby"] = dataframe["ashby_url"].notna() | dataframe["ashby_api_ok"].fillna(False)
    dataframe["has_any_ats"] = dataframe["has_greenhouse"] | dataframe["has_lever"] | dataframe["has_ashby"]
    dataframe["total_jobs_count"] = (
        dataframe["greenhouse_jobs_count"].fillna(0)
        + dataframe["lever_jobs_count"].fillna(0)
        + dataframe["ashby_jobs_count"].fillna(0)
    )
    dataframe = dataframe.sort_values(
        by=["has_any_ats", "total_jobs_count", "relevance_score", "company"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    metadata = {
        "profile_summary": profile.llm_summary or profile.summary,
        "keywords_used": keywords,
        "regions_used": regions,
        "queries_used": queries,
        "search_warning_count": len(search_warnings),
        "search_warnings": search_warnings,
        "candidate_company_count": len(company_names),
        "search_result_count": len(search_results),
        "greenhouse_hits": int(dataframe["has_greenhouse"].sum()),
        "lever_hits": int(dataframe["has_lever"].sum()),
        "ashby_hits": int(dataframe["has_ashby"].sum()),
    }
    return dataframe, metadata


def save_outputs(df: pd.DataFrame, metadata: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    discovery_csv = output_dir / "job_board_company_discovery_results.csv"
    greenhouse_csv = output_dir / "job_board_confirmed_greenhouse_companies.csv"
    lever_csv = output_dir / "job_board_confirmed_lever_companies.csv"
    ashby_csv = output_dir / "job_board_confirmed_ashby_companies.csv"
    ats_csv = output_dir / "job_board_confirmed_any_ats_companies.csv"
    metadata_json = output_dir / "job_board_discovery_metadata.json"

    df.to_csv(discovery_csv, index=False, encoding="utf-8")
    LOGGER.info("Saved %s", discovery_csv)

    confirmed_greenhouse = df[df["has_greenhouse"] == True].copy()
    confirmed_greenhouse.to_csv(greenhouse_csv, index=False, encoding="utf-8")
    LOGGER.info("Saved %s", greenhouse_csv)

    confirmed_lever = df[df["has_lever"] == True].copy()
    confirmed_lever.to_csv(lever_csv, index=False, encoding="utf-8")
    LOGGER.info("Saved %s", lever_csv)

    confirmed_ashby = df[df["has_ashby"] == True].copy()
    confirmed_ashby.to_csv(ashby_csv, index=False, encoding="utf-8")
    LOGGER.info("Saved %s", ashby_csv)

    confirmed_any_ats = df[df["has_any_ats"] == True].copy()
    confirmed_any_ats.to_csv(ats_csv, index=False, encoding="utf-8")
    LOGGER.info("Saved %s", ats_csv)

    metadata_json.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Saved %s", metadata_json)


def run_board_discovery(
    project_root: Path,
    profile: UserProfile,
    config: AppConfig,
    output_dir: Path,
    *,
    max_search_results_per_query: int = 15,
    max_workers: int = 10,
) -> dict[str, Any]:
    """Run board discovery from an already-loaded profile and save outputs."""

    keywords, regions = derive_profile_keywords_and_regions(profile, config)
    dataframe, metadata = discover_companies(
        profile=profile,
        config=config,
        keywords=keywords,
        regions=regions,
        max_search_results_per_query=max_search_results_per_query,
        max_workers=max_workers,
    )
    save_outputs(dataframe, metadata, output_dir if output_dir.is_absolute() else (project_root / output_dir))
    return metadata


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    output_dir = resolve_input_path(project_root, args.output_dir)

    start = time.time()
    profile, config, keywords, regions = load_profile_keywords(
        project_root=project_root,
        profile_path=args.profile,
        supplemental_files=args.resume,
        config_path=args.config,
    )
    dataframe, metadata = discover_companies(
        profile=profile,
        config=config,
        keywords=keywords,
        regions=regions,
        max_search_results_per_query=args.max_search_results,
        max_workers=args.max_workers,
    )
    save_outputs(dataframe, metadata, output_dir)
    LOGGER.info("Pipeline finished in %.1fs", time.time() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
