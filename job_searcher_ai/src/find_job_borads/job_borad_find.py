import re
import time
import json
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse
from tqdm import tqdm
import logging
import time


import requests
import pandas as pd
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:
    raise SystemExit("Please install dependencies first: pip install ddgs requests beautifulsoup4 pandas")

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
# )
# ----------------------------
# Config
# ----------------------------

PROFILE_TEXT = """
AI Engineer focused on computer vision, 3D computer vision, multimodal perception,
SLAM, autonomous driving, robotics, deep learning, PyTorch, LiDAR, NeRF, mapping,
sensor fusion, ADAS, industrial robotics, physical AI.
Worked at Volkswagen, NavVis, Fraunhofer IIS, and RoadGauge AI.
"""

TARGET_REGIONS = [
    "Germany",
    "Munich",
    "Berlin",
    "Stuttgart",
    "Hamburg",
    "Europe",
    "Remote Europe",
]

MAX_SEARCH_RESULTS_PER_QUERY = 15
REQUEST_TIMEOUT = 12
SLEEP_BETWEEN_REQUESTS = 0.8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ----------------------------
# Step 1: Keyword extraction
# ----------------------------

def extract_keywords(profile_text: str) -> List[str]:
    """
    Very simple keyword extraction.
    Replace this later with a local LLM if you want.
    """
    canonical_keywords = [
        "computer vision",
        "3d computer vision",
        "multimodal ai",
        "multimodal perception",
        "robotics",
        "robot perception",
        "slam",
        "mapping",
        "localization",
        "autonomous driving",
        "adas",
        "sensor fusion",
        "lidar",
        "deep learning",
        "pytorch",
        "industrial robotics",
        "physical ai",
        "vision-language-action",
        "nerf",
        "3d reconstruction",
    ]

    text = profile_text.lower()
    found = [k for k in canonical_keywords if k in text]

    # Add a few fallbacks if profile is short
    fallback = ["computer vision", "robotics", "autonomous driving", "slam", "multimodal ai"]
    for f in fallback:
        if f not in found:
            found.append(f)

    return found[:12]


# ----------------------------
# Step 2: Search query generation
# ----------------------------

def build_search_queries(keywords: List[str], regions: List[str]) -> List[str]:
    queries = []

    templates = [
        "{kw} companies {region}",
        "{kw} startup {region}",
        "{kw} jobs {region}",
        "{kw} company careers {region}",
        "{kw} robotics company {region}",
    ]

    for kw in keywords:
        for region in regions:
            for tpl in templates:
                queries.append(tpl.format(kw=kw, region=region))

    # A few high-signal generic discovery queries
    queries += [
        "site:greenhouse.io computer vision Germany",
        "site:job-boards.eu.greenhouse.io robotics Germany",
        "site:boards.greenhouse.io autonomous driving Europe",
        "top robotics startups Germany",
        "top computer vision companies Germany",
        "slam companies Europe",
    ]

    # Deduplicate while preserving order
    deduped = list(dict.fromkeys(queries))
    return deduped


# ----------------------------
# Step 3: Search web
# ----------------------------

def search_web(queries: List[str], max_results_per_query: int = 10) -> List[Dict]:
    results = []

    with DDGS() as ddgs:
        for query in tqdm(queries): 
            try:
                hits = ddgs.text(query, max_results=max_results_per_query)
                for h in hits:
                    results.append({
                        "query": query,
                        "title": h.get("title", ""),
                        "href": h.get("href", ""),
                        "body": h.get("body", ""),
                    })
            except Exception as e:
                print(f"[WARN] Search failed for query='{query}': {e}")
            time.sleep(0.3)

    return results


# ----------------------------
# Step 4: Extract candidate company names
# ----------------------------

COMMON_NON_COMPANY_WORDS = {
    "jobs", "careers", "career", "hiring", "linkedin", "indeed", "glassdoor",
    "germany", "europe", "remote", "team", "page", "blog", "news", "startup",
    "startups", "company", "companies", "vision", "robotics", "ai", "driving"
}


def clean_company_candidate(name: str) -> Optional[str]:
    if not name:
        return None

    name = re.sub(r"\s+", " ", name).strip(" -|–—:,.")
    if len(name) < 2 or len(name) > 80:
        return None

    # Reject obviously bad tokens
    lowered = name.lower()
    if lowered in COMMON_NON_COMPANY_WORDS:
        return None

    if re.fullmatch(r"[a-z0-9\-_/\.]+", lowered):
        # Sometimes a slug is okay, but reject very generic single tokens
        if lowered in COMMON_NON_COMPANY_WORDS:
            return None

    return name


def extract_company_names_from_result(result: Dict) -> Set[str]:
    """
    Heuristic extraction from title, URL host, and snippets.
    """
    candidates = set()

    title = result.get("title", "")
    href = result.get("href", "")
    body = result.get("body", "")

    # 1) Split title on common separators
    for part in re.split(r"[|\-–—:•]", title):
        c = clean_company_candidate(part)
        if c:
            candidates.add(c)

    # 2) Extract first domain token
    if href:
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
            domain_root = host.split(".")[0]
            if domain_root and domain_root not in COMMON_NON_COMPANY_WORDS:
                candidates.add(domain_root)
        except Exception:
            pass

    # 3) Look for company-like capitalized phrases in snippet
    for match in re.findall(r"\b([A-Z][A-Za-z0-9&\-.]+(?:\s+[A-Z][A-Za-z0-9&\-.]+){0,3})\b", body):
        c = clean_company_candidate(match)
        if c:
            candidates.add(c)

    return candidates


def normalize_company_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\b(GmbH|Inc|Ltd|LLC|AG|SE|PLC|Technologies|Technology|Systems|Group)\b", "", name, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9\s\-&]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def generate_slug_variants(company_name: str) -> List[str]:
    """
    Create likely Greenhouse board slugs.
    """
    base = normalize_company_name(company_name).lower()

    variants = set()
    variants.add(base.replace(" ", ""))
    variants.add(base.replace(" ", "-"))
    variants.add(base.replace("&", "and").replace(" ", ""))
    variants.add(base.replace("&", "and").replace(" ", "-"))

    # Remove separators for compact slugs
    stripped = re.sub(r"[^a-z0-9]", "", base)
    if stripped:
        variants.add(stripped)

    return [v for v in variants if v]


# ----------------------------
# Step 5: Test Greenhouse URLs
# ----------------------------

def safe_get(url: str) -> Optional[requests.Response]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp
    except Exception:
        return None


def test_greenhouse_slug(slug: str) -> Dict:
    """
    Check common Greenhouse board URL formats and the Job Board API.
    """
    urls = [
        f"https://boards.greenhouse.io/{slug}",
        f"https://job-boards.greenhouse.io/{slug}",
        f"https://job-boards.eu.greenhouse.io/{slug}",
    ]

    found_url = None
    status_code = None

    for u in urls:
        resp = safe_get(u)
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        if resp is not None:
            status_code = resp.status_code
            if resp.status_code == 200 and "greenhouse" in resp.url:
                found_url = resp.url
                break

    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    api_resp = safe_get(api_url)
    time.sleep(SLEEP_BETWEEN_REQUESTS)

    api_ok = False
    api_jobs_count = None

    if api_resp is not None and api_resp.status_code == 200:
        api_ok = True
        try:
            data = api_resp.json()
            api_jobs_count = len(data.get("jobs", []))
        except Exception:
            api_jobs_count = None

    return {
        "slug": slug,
        "greenhouse_url": found_url,
        "greenhouse_status": status_code,
        "api_url": api_url,
        "api_ok": api_ok,
        "api_jobs_count": api_jobs_count,
    }


# ----------------------------
# Step 6: Enrich company candidates
# ----------------------------

def discover_companies(profile_text: str) -> pd.DataFrame:
    keywords = extract_keywords(profile_text)
    queries = build_search_queries(keywords, TARGET_REGIONS)

    print(f"[INFO] Keywords: {keywords}")
    print(f"[INFO] Running {len(queries)} search queries...")

    search_results = search_web(queries, max_results_per_query=MAX_SEARCH_RESULTS_PER_QUERY)

    company_names = set()
    rows = []

    for r in search_results:
        extracted = extract_company_names_from_result(r)
        for c in extracted:
            c_norm = normalize_company_name(c)
            if len(c_norm) >= 2:
                company_names.add(c_norm)

    # Optional: seed a few high-signal companies manually
    manual_seeds = {
        "NavVis", "Agile Robots", "NEURA Robotics", "Franka Robotics", "KUKA",
        "Bosch", "Continental", "Cariad", "Aptiv", "Innoviz", "Wayve",
        "Applied Intuition", "Tesla", "NVIDIA", "Intrinsic", "ANYbotics"
    }
    for m in manual_seeds:
        company_names.add(normalize_company_name(m))

    print(f"[INFO] Candidate companies found: {len(company_names)}")

    for company in sorted(company_names):
        slug_variants = generate_slug_variants(company)

        best_hit = None
        for slug in slug_variants[:4]:
            hit = test_greenhouse_slug(slug)
            if hit["greenhouse_url"] or hit["api_ok"]:
                best_hit = hit
                break

        rows.append({
            "company": company,
            "slug_variants": json.dumps(slug_variants, ensure_ascii=False),
            "greenhouse_slug": best_hit["slug"] if best_hit else None,
            "greenhouse_url": best_hit["greenhouse_url"] if best_hit else None,
            "greenhouse_status": best_hit["greenhouse_status"] if best_hit else None,
            "greenhouse_api_ok": best_hit["api_ok"] if best_hit else False,
            "greenhouse_jobs_count": best_hit["api_jobs_count"] if best_hit else None,
        })

    df = pd.DataFrame(rows)

    # Simple relevance scoring
    priority_terms = [
        "robot", "vision", "autonomous", "mapping", "slam", "ai", "lidar", "drive", "perception"
    ]

    def score_company(name: str) -> int:
        s = 0
        lname = name.lower()
        for term in priority_terms:
            if term in lname:
                s += 1
        return s

    df["relevance_score"] = df["company"].apply(score_company)

    # Put likely Greenhouse companies on top
    df["has_greenhouse"] = df["greenhouse_url"].notna() | df["greenhouse_api_ok"].fillna(False)
    df = df.sort_values(
        by=["has_greenhouse", "greenhouse_jobs_count", "relevance_score", "company"],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)

    return df


# ----------------------------
# Step 7: Save
# ----------------------------

def main():
    df = discover_companies(PROFILE_TEXT)

    df.to_csv("company_discovery_results.csv", index=False, encoding="utf-8")
    print("[INFO] Saved company_discovery_results.csv")

    # Also save only confirmed / likely Greenhouse targets
    df_greenhouse = df[df["has_greenhouse"] == True].copy()
    df_greenhouse.to_csv("confirmed_greenhouse_companies.csv", index=False, encoding="utf-8")
    print("[INFO] Saved confirmed_greenhouse_companies.csv")

    print("\nTop results:")
    print(df.head(30).to_string(index=False))


if __name__ == "__main__":
    main()