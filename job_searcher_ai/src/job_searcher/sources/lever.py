"""Lever job source connector."""

from __future__ import annotations

import logging

from job_searcher.parsing.jobs import parse_lever_job
from job_searcher.logging_utils import ProgressLogger
from job_searcher.schemas import SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


LOGGER = logging.getLogger(__name__)


class LeverSource(BaseJobSource):
    name = "lever"

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.lever_boards:
            result.notes.append("no Lever boards were configured")
            return result

        board_progress = ProgressLogger(
            LOGGER,
            "Lever boards",
            len(context.config.sources.lever_boards),
            min_interval_seconds=3.0,
        )
        for board in context.config.sources.lever_boards:
            url = f"https://api.lever.co/v0/postings/{board}?mode=json"
            payload = context.get_json(url)
            jobs = payload if isinstance(payload, list) else []
            result.raw_jobs += len(jobs)
            job_progress = ProgressLogger(
                LOGGER,
                f"Lever board {board}",
                len(jobs),
                min_interval_seconds=3.0,
            )
            for item in jobs:
                item.setdefault("company", board.replace("-", " ").title())
                job = parse_lever_job(item)
                self.apply_query_filter(result, job, queries)
                context.maybe_checkpoint(result)
                job_progress.advance()
            job_progress.finish()
            board_progress.advance()
            context.maybe_checkpoint(result, force=True)
        board_progress.finish()

        result.diagnostics = context.take_diagnostics()
        return result
