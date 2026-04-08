"""Source abstractions and shared HTTP helpers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

from job_searcher.config import AppConfig
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.utils.cache import JsonCache
from job_searcher.utils.text import jaccard_similarity, normalize_text
from job_searcher.utils.urls import is_allowed_by_robots


LOGGER = logging.getLogger(__name__)


@dataclass
class SourceContext:
    config: AppConfig
    cache: JsonCache
    session: requests.Session = field(default_factory=requests.Session)
    _last_request_at: float = 0.0

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": self.config.scraping.user_agent})

    def get_json(self, url: str) -> dict:
        payload = self._request(url, expect_json=True)
        return payload if isinstance(payload, dict) else {}

    def get_text(self, url: str) -> str:
        payload = self._request(url, expect_json=False)
        return payload if isinstance(payload, str) else ""

    def _request(self, url: str, expect_json: bool) -> dict | str:
        cache_key = f"{'json' if expect_json else 'text'}::{url}"
        cached = self.cache.get(cache_key, ttl_hours=self.config.scraping.cache_ttl_hours)
        if cached is not None:
            return cached

        if self.config.scraping.respect_robots and url.startswith("http"):
            if not is_allowed_by_robots(url, self.config.scraping.user_agent, timeout=self.config.scraping.request_timeout_seconds):
                LOGGER.warning("Skipping %s because robots.txt disallows it", url)
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
            except requests.RequestException as exc:
                last_error = exc
                sleep_seconds = min(2 ** attempt, 5)
                time.sleep(sleep_seconds)
        LOGGER.warning("Failed to fetch %s: %s", url, last_error)
        return {} if expect_json else ""


class BaseJobSource(ABC):
    name: str

    @abstractmethod
    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> list[JobListing]:
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
