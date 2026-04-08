"""Lever job source connector."""

from __future__ import annotations

from job_searcher.parsing.jobs import parse_lever_job
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext


class LeverSource(BaseJobSource):
    name = "lever"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> list[JobListing]:
        jobs: list[JobListing] = []
        for board in context.config.sources.lever_boards:
            url = f"https://api.lever.co/v0/postings/{board}?mode=json"
            payload = context._request(url, expect_json=True)
            for item in payload if isinstance(payload, list) else []:
                item.setdefault("company", board.replace("-", " ").title())
                job = parse_lever_job(item)
                if self.matches_queries(job, queries):
                    jobs.append(job)
        return jobs
