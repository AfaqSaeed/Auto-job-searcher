"""Greenhouse job source connector."""

from __future__ import annotations

from job_searcher.parsing.jobs import parse_greenhouse_job
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext


class GreenhouseSource(BaseJobSource):
    name = "greenhouse"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> list[JobListing]:
        jobs: list[JobListing] = []
        for board in context.config.sources.greenhouse_boards:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            payload = context.get_json(url)
            for item in payload.get("jobs", []):
                item.setdefault("board_token", board)
                item.setdefault("company_name", board.replace("-", " ").title())
                job = parse_greenhouse_job(item)
                if self.matches_queries(job, queries):
                    jobs.append(job)
        return jobs
