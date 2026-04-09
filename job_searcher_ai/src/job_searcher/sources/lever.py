"""Lever job source connector."""

from __future__ import annotations

from job_searcher.parsing.jobs import parse_lever_job
from job_searcher.schemas import SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


class LeverSource(BaseJobSource):
    name = "lever"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.lever_boards:
            result.notes.append("no Lever boards were configured")
            return result

        for board in context.config.sources.lever_boards:
            url = f"https://api.lever.co/v0/postings/{board}?mode=json"
            payload = context.get_json(url)
            jobs = payload if isinstance(payload, list) else []
            result.raw_jobs += len(jobs)
            for item in jobs:
                item.setdefault("company", board.replace("-", " ").title())
                job = parse_lever_job(item)
                if self.matches_queries(job, queries):
                    result.jobs.append(job)
                    result.matched_jobs += 1

        result.diagnostics = context.take_diagnostics()
        return result
