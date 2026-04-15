"""Greenhouse job source connector."""

from __future__ import annotations

import logging

from job_searcher.parsing.jobs import parse_greenhouse_job
from job_searcher.logging_utils import ProgressLogger
from job_searcher.schemas import SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


LOGGER = logging.getLogger(__name__)


class GreenhouseSource(BaseJobSource):
    name = "greenhouse"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.greenhouse_boards:
            result.notes.append("no Greenhouse boards were configured")
            return result

        board_progress = ProgressLogger(
            LOGGER,
            "Greenhouse boards",
            len(context.config.sources.greenhouse_boards),
            min_interval_seconds=3.0,
        )
        for board in context.config.sources.greenhouse_boards:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            payload = context.get_json(url)
            jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
            result.raw_jobs += len(jobs)
            job_progress = ProgressLogger(
                LOGGER,
                f"Greenhouse board {board}",
                len(jobs),
                min_interval_seconds=3.0,
            )
            for item in jobs:
                item.setdefault("board_token", board)
                item.setdefault("company_name", board.replace("-", " ").title())
                job = parse_greenhouse_job(item)
                self.apply_query_filter(result, job, queries)
                context.maybe_checkpoint(result)
                job_progress.advance()
            job_progress.finish()
            board_progress.advance()
            context.maybe_checkpoint(result, force=True)
        board_progress.finish()

        result.diagnostics = context.take_diagnostics()
        return result
