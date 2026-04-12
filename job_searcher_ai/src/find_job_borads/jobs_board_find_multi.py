import re
import time
import json
import threading
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup  # kept for future extension / HTML parsing if needed

try:
    from ddgs import DDGS
except ImportError:
    raise SystemExit("Please install dependencies first: pip install ddgs requests beautifulsoup4 pandas tqdm")


# ============================================================
# Config
# ============================================================

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
REQUEST_TIMEOUT = 10
SLEEP_BETWEEN_REQUESTS = 0.2
MAX_GREENHOUSE_WORKERS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ============================================================
# Clean console output helpers
# ============================================================

print_lock = threading.Lock()


def safe_print(msg: str) -> None:
    with print_lock:
        tqdm.write(msg)


def timed_stage(label: str, fn, *args, **kwargs):
    start = time.time()
    result = fn(*args, **kwargs)
    elapsed = time.time() - start
    safe_print(f"{label} finished in {elapsed:.1f}s")
    return result


# ============================================================
# Step 1: Keyword extraction
# ============================================================

def extract_keywords(profile_text: str) -> List[str]:
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

    fallback = [
        "computer vision",
        "robotics",
        "autonomous driving",
        "slam",
        "multimodal ai",
    ]
    for f in fallback:
        if f not in found:
            found.append(f)

    return found[:12]


# ============================================================
# Step 2: Build search queries
# ============================================================

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

    queries += [
        "site:greenhouse.io computer vision Germany",
        "site:job-boards.eu.greenhouse.io robotics Germany",
        "site:boards.greenhouse.io autonomous driving Europe",
        "top robotics startups Germany",
        "top computer vision companies Germany",
        "slam companies Europe",
    ]

    return list(dict.fromkeys(queries))


# ============================================================
# Step 3: Web search
# ============================================================

def search_web(queries: List[str], max_results_per_query: int = 10) -> List[Dict]:
    results = []

    with DDGS() as ddgs:
        for query in tqdm(queries, desc="Searching web", unit="query"):
            try:
                hits = ddgs.text(query, max_results=max_results_per_query)
                for h in hits:
                    results.append({
                        "query": query,
                        "title": h.get("title", ""),
                        "href": h.get("href", ""),
                        "body": h.get("body", ""),
                    })
            except Exception:
                pass

            # small pause to avoid hammering search endpoints
            time.sleep(0.15)

    return results


# ============================================================
# Step 4: Extract candidate company names
# ============================================================

COMMON_NON_COMPANY_WORDS = {
    "jobs", "careers", "career", "hiring", "linkedin", "indeed", "glassdoor",
    "germany", "europe", "remote", "team", "page", "blog", "news", "startup",
    "startups", "company", "companies", "vision", "robotics", "ai", "driving",
    "munich", "berlin", "hamburg", "stuttgart"
}


def clean_company_candidate(name: str) -> Optional[str]:
    if not name:
        return None

    name = re.sub(r"\s+", " ", name).strip(" -|–—:,.")
    if len(name) < 2 or len(name) > 80:
        return None

    lowered = name.lower()
    if lowered in COMMON_NON_COMPANY_WORDS:
        return None

    return name


def extract_company_names_from_result(result: Dict) -> Set[str]:
    candidates = set()

    title = result.get("title", "")
    href = result.get("href", "")
    body = result.get("body", "")

    for part in re.split(r"[|\-–—:•/]", title):
        c = clean_company_candidate(part)
        if c:
            candidates.add(c)

    if href:
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
            domain_root = host.split(".")[0]
            if domain_root and domain_root not in COMMON_NON_COMPANY_WORDS:
                candidates.add(domain_root)
        except Exception:
            pass

    for match in re.findall(r"\b([A-Z][A-Za-z0-9&\-.]+(?:\s+[A-Z][A-Za-z0-9&\-.]+){0,3})\b", body):
        c = clean_company_candidate(match)
        if c:
            candidates.add(c)

    return candidates


def normalize_company_name(name: str) -> str:
    name = name.strip()
    name = re.sub(
        r"\b(GmbH|Inc|Ltd|LLC|AG|SE|PLC|Technologies|Technology|Systems|Group|Corp|Company)\b",
        "",
        name,
        flags=re.I,
    )
    name = re.sub(r"[^A-Za-z0-9\s\-&]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def generate_slug_variants(company_name: str) -> List[str]:
    base = normalize_company_name(company_name).lower()

    variants = set()
    variants.add(base.replace(" ", ""))
    variants.add(base.replace(" ", "-"))
    variants.add(base.replace("&", "and").replace(" ", ""))
    variants.add(base.replace("&", "and").replace(" ", "-"))

    stripped = re.sub(r"[^a-z0-9]", "", base)
    if stripped:
        variants.add(stripped)

    return [v for v in variants if v]


# ============================================================
# Step 5: Greenhouse checking
# ============================================================

def safe_get(url: str) -> Optional[requests.Response]:
    try:
        return requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except Exception:
        return None


def test_greenhouse_slug(slug: str) -> Dict:
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


def check_company_greenhouse(company: str) -> Dict:
    start = time.time()

    slug_variants = generate_slug_variants(company)
    best_hit = None

    for slug in slug_variants[:4]:
        hit = test_greenhouse_slug(slug)
        if hit["greenhouse_url"] or hit["api_ok"]:
            best_hit = hit
            break

    elapsed = time.time() - start

    return {
        "company": company,
        "slug_variants": json.dumps(slug_variants, ensure_ascii=False),
        "greenhouse_slug": best_hit["slug"] if best_hit else None,
        "greenhouse_url": best_hit["greenhouse_url"] if best_hit else None,
        "greenhouse_status": best_hit["greenhouse_status"] if best_hit else None,
        "greenhouse_api_ok": best_hit["api_ok"] if best_hit else False,
        "greenhouse_jobs_count": best_hit["api_jobs_count"] if best_hit else None,
        "elapsed_seconds": round(elapsed, 2),
    }


def enrich_companies_parallel(company_names: Set[str], max_workers: int = 10) -> List[Dict]:
    companies = sorted(company_names)
    rows = []

    start_all = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_company_greenhouse, company): company
            for company in companies
        }

        with tqdm(total=len(futures), desc="Checking Greenhouse boards", unit="company") as pbar:
            for future in as_completed(futures):
                company = futures[future]
                try:
                    row = future.result()
                except Exception:
                    row = {
                        "company": company,
                        "slug_variants": "[]",
                        "greenhouse_slug": None,
                        "greenhouse_url": None,
                        "greenhouse_status": None,
                        "greenhouse_api_ok": False,
                        "greenhouse_jobs_count": None,
                        "elapsed_seconds": None,
                    }

                rows.append(row)
                pbar.update(1)

    total_elapsed = time.time() - start_all
    avg_time = total_elapsed / max(len(companies), 1)

    safe_print(f"Finished Greenhouse checks in {total_elapsed:.1f}s")
    safe_print(f"Average wall-clock time per company: {avg_time:.2f}s using {max_workers} workers")

    return rows


# ============================================================
# Step 6: Full discovery pipeline
# ============================================================

def discover_companies(profile_text: str) -> pd.DataFrame:
    keywords = extract_keywords(profile_text)
    queries = build_search_queries(keywords, TARGET_REGIONS)

    safe_print(f"Keywords: {keywords}")
    safe_print(f"Running {len(queries)} search queries")

    search_results = timed_stage(
        "Search",
        search_web,
        queries,
        MAX_SEARCH_RESULTS_PER_QUERY,
    )
    safe_print(f"Search results collected: {len(search_results)}")

    company_names = set()

    start_extract = time.time()
    for r in tqdm(search_results, desc="Extracting companies", unit="result"):
        extracted = extract_company_names_from_result(r)
        for c in extracted:
            c_norm = normalize_company_name(c)
            if len(c_norm) >= 2:
                company_names.add(c_norm)

    manual_seeds = {
        "NavVis", "Agile Robots", "NEURA Robotics", "Franka Robotics", "KUKA",
        "Bosch", "Continental", "Cariad", "Aptiv", "Innoviz", "Wayve",
        "Applied Intuition", "Tesla", "NVIDIA", "Intrinsic", "ANYbotics"
    }
    for m in manual_seeds:
        company_names.add(normalize_company_name(m))

    safe_print(f"Extraction finished in {time.time() - start_extract:.1f}s")
    safe_print(f"Candidate companies found: {len(company_names)}")

    rows = timed_stage(
        "Greenhouse enrichment",
        enrich_companies_parallel,
        company_names,
        MAX_GREENHOUSE_WORKERS,
    )

    df = pd.DataFrame(rows)

    priority_terms = [
        "robot", "vision", "autonomous", "mapping", "slam",
        "ai", "lidar", "drive", "perception"
    ]

    def score_company(name: str) -> int:
        lname = name.lower()
        return sum(1 for term in priority_terms if term in lname)

    df["relevance_score"] = df["company"].apply(score_company)
    df["has_greenhouse"] = df["greenhouse_url"].notna() | df["greenhouse_api_ok"].fillna(False)

    df = df.sort_values(
        by=["has_greenhouse", "greenhouse_jobs_count", "relevance_score", "company"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    return df


# ============================================================
# Step 7: Save outputs
# ============================================================

def save_outputs(df: pd.DataFrame) -> None:
    df.to_csv("company_discovery_results.csv", index=False, encoding="utf-8")
    safe_print("Saved company_discovery_results.csv")

    df_greenhouse = df[df["has_greenhouse"] == True].copy()
    df_greenhouse.to_csv("confirmed_greenhouse_companies.csv", index=False, encoding="utf-8")
    safe_print("Saved confirmed_greenhouse_companies.csv")

    top_cols = [
        "company",
        "greenhouse_slug",
        "greenhouse_url",
        "greenhouse_jobs_count",
        "elapsed_seconds",
        "relevance_score",
    ]

    preview = df[top_cols].head(20)
    safe_print("\nTop results:")
    safe_print(preview.to_string(index=False))


# ============================================================
# Main
# ============================================================

def main():
    total_start = time.time()
    df = discover_companies(PROFILE_TEXT)
    save_outputs(df)
    safe_print(f"\nPipeline finished in {time.time() - total_start:.1f}s")


if __name__ == "__main__":
    main()