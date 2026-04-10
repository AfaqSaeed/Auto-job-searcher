"""Source abstractions and shared HTTP helpers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import requests

from job_searcher.config import AppConfig
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.utils.cache import JsonCache
from job_searcher.utils.text import jaccard_similarity, normalize_text
from job_searcher.utils.urls import is_allowed_by_robots


LOGGER = logging.getLogger(__name__)


@dataclass
class RequestDiagnostic:
    url: str
    status_code: int | None = None
    message: str = ""
    kind: str = "request_error"


@dataclass
class SourceRunResult:
    source_name: str
    jobs: list[JobListing] = field(default_factory=list)
    filtered_out_jobs: list[JobListing] = field(default_factory=list)
    discovered_jobs: list[JobListing] = field(default_factory=list)
    raw_jobs: int = 0
    matched_jobs: int = 0
    diagnostics: list[RequestDiagnostic] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    debug_data: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Build a concise source result summary for logs and reports."""

        if self.matched_jobs > 0:
            filtered_out = len(self.filtered_out_jobs)
            if filtered_out > 0:
                return (
                    f"Fetched {self.matched_jobs} jobs from {self.source_name} "
                    f"({self.raw_jobs} raw jobs, filtered out {filtered_out} by queries)"
                )
            return f"Fetched {self.matched_jobs} jobs from {self.source_name}"

        if self.raw_jobs > 0 and self.matched_jobs == 0:
            return (
                f"Fetched 0 jobs from {self.source_name}: got {self.raw_jobs} raw jobs, "
                "but all were filtered out by the generated queries"
            )

        if self.diagnostics:
            primary = self.diagnostics[0]
            if primary.status_code == 404:
                if self.source_name == "custom_career_pages":
                    return (
                        f"Fetched 0 jobs from {self.source_name}: an optional discovery URL returned 404 "
                        "(commonly a sitemap path or auxiliary page), so rendered or in-page discovery may be needed"
                    )
                return (
                    f"Fetched 0 jobs from {self.source_name}: endpoint returned 404, "
                    "which usually means a wrong board slug or the company is not using that ATS"
                )
            if primary.status_code == 403:
                return f"Fetched 0 jobs from {self.source_name}: endpoint returned 403 and blocked access"
            if primary.status_code == 429:
                return f"Fetched 0 jobs from {self.source_name}: endpoint rate-limited the requests with 429"
            if primary.kind == "robots_blocked":
                return f"Fetched 0 jobs from {self.source_name}: robots.txt disallowed fetching this source"
            if primary.kind == "request_error":
                return f"Fetched 0 jobs from {self.source_name}: request failed ({primary.message})"

        if self.notes:
            return f"Fetched 0 jobs from {self.source_name}: {self.notes[0]}"

        return f"Fetched 0 jobs from {self.source_name}: source returned no jobs or no source entries were configured"

    def filtered_debug_payload(self) -> dict:
        """Return a compact debug payload for filtered-out jobs."""

        return {
            "source_name": self.source_name,
            "raw_jobs": self.raw_jobs,
            "matched_jobs": self.matched_jobs,
            "filtered_out_count": len(self.filtered_out_jobs),
            "summary": self.summary(),
            "filtered_out_jobs": [job.model_dump(mode="json") for job in self.filtered_out_jobs],
        }

    def discovered_debug_payload(self) -> dict:
        """Return a compact debug payload for jobs discovered before query filtering."""

        return {
            "source_name": self.source_name,
            "raw_jobs": self.raw_jobs,
            "matched_jobs": self.matched_jobs,
            "filtered_out_count": len(self.filtered_out_jobs),
            "summary": self.summary(),
            "discovered_jobs": [job.model_dump(mode="json") for job in self.discovered_jobs],
        }


@dataclass
class SourceContext:
    config: AppConfig
    cache: JsonCache
    session: requests.Session = field(default_factory=requests.Session)
    _last_request_at: float = 0.0
    active_source: str = "unknown"
    request_diagnostics: list[RequestDiagnostic] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": self.config.scraping.user_agent})

    def set_active_source(self, source_name: str) -> None:
        self.active_source = source_name
        self.request_diagnostics = []

    def take_diagnostics(self) -> list[RequestDiagnostic]:
        diagnostics = list(self.request_diagnostics)
        self.request_diagnostics = []
        return diagnostics

    def add_note_diagnostic(self, *, url: str, message: str, kind: str, status_code: int | None = None) -> None:
        self.request_diagnostics.append(
            RequestDiagnostic(url=url, status_code=status_code, message=message, kind=kind)
        )

    def get_json(self, url: str) -> dict | list:
        payload = self._request(url, expect_json=True)
        if isinstance(payload, (dict, list)):
            return payload
        return {}

    def get_text(self, url: str) -> str:
        payload = self._request(url, expect_json=False)
        return payload if isinstance(payload, str) else ""

    def _request(self, url: str, expect_json: bool) -> dict | list | str:
        cache_key = f"{'json' if expect_json else 'text'}::{url}"
        cached = self.cache.get(cache_key, ttl_hours=self.config.scraping.cache_ttl_hours)
        if cached is not None:
            return cached

        if self.config.scraping.respect_robots and url.startswith("http"):
            if not is_allowed_by_robots(url, self.config.scraping.user_agent, timeout=self.config.scraping.request_timeout_seconds):
                message = "robots.txt disallows this fetch"
                LOGGER.warning("Skipping %s because robots.txt disallows it", url)
                self.add_note_diagnostic(url=url, message=message, kind="robots_blocked")
                return {} if expect_json else ""

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.config.scraping.rate_limit_seconds:
            time.sleep(self.config.scraping.rate_limit_seconds - elapsed)

        last_error: Exception | None = None
        for attempt in range(self.config.scraping.max_retries):
            try:
                response = self.session.get(url, timeout=self.config.scraping.request_timeout_seconds)
                response.raise_for_status()
                self._last_request_at = time.monotonic()
                data = response.json() if expect_json else response.text
                self.cache.set(cache_key, data)
                return data
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                self.add_note_diagnostic(url=url, status_code=status_code, message=str(exc), kind="http_error")
                sleep_seconds = min(2 ** attempt, 5)
                time.sleep(sleep_seconds)
            except requests.RequestException as exc:
                last_error = exc
                self.add_note_diagnostic(url=url, message=str(exc), kind="request_error")
                sleep_seconds = min(2 ** attempt, 5)
                time.sleep(sleep_seconds)
        LOGGER.warning("Failed to fetch %s: %s", url, last_error)
        return {} if expect_json else ""


class BaseJobSource(ABC):
    name: str

    @abstractmethod
    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        """Fetch jobs for this source."""

    @staticmethod
    def matches_queries(job: JobListing, queries: list[SearchQuery]) -> bool:
        """Filter source results using generated search queries."""

        if not queries:
            return True
        job_text = normalize_text(" ".join([job.title, job.company, job.location or "", job.description]))
        return any(
            normalize_text(query.text) in job_text or jaccard_similarity(query.text, job_text) >= 0.18
            for query in queries
        )
