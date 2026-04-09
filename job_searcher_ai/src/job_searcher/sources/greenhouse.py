"""Greenhouse job source connector."""

from __future__ import annotations

from job_searcher.parsing.jobs import parse_greenhouse_job
from job_searcher.schemas import SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


class GreenhouseSource(BaseJobSource):
    name = "greenhouse"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.greenhouse_boards:
            result.notes.append("no Greenhouse boards were configured")
            return result

        for board in context.config.sources.greenhouse_boards:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            payload = context.get_json(url)
            jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
            result.raw_jobs += len(jobs)
            for item in jobs:
                item.setdefault("board_token", board)
                item.setdefault("company_name", board.replace("-", " ").title())
                job = parse_greenhouse_job(item)
                if self.matches_queries(job, queries):
                    result.jobs.append(job)
                    result.matched_jobs += 1

        result.diagnostics = context.take_diagnostics()
        return result
