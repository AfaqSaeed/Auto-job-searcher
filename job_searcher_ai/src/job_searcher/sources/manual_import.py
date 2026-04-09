"""Manual job import connector."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from job_searcher.parsing.normalization import normalize_job_listing
from job_searcher.schemas import JobListing, SearchQuery
from job_searcher.sources.base import BaseJobSource, SourceContext, SourceRunResult


class ManualImportSource(BaseJobSource):
    name = "manual_import"

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def fetch_jobs(self, queries: list[SearchQuery], context: SourceContext) -> SourceRunResult:
        context.set_active_source(self.name)
        result = SourceRunResult(source_name=self.name)
        if not context.config.sources.manual_files:
            result.notes.append("no manual import files were configured")
            return result

        for relative_file in context.config.sources.manual_files:
            path = (self.project_root / relative_file).resolve()
            if not path.exists():
                result.notes.append(f"configured manual file not found: {path.name}")
                continue
            if path.suffix.lower() == ".json":
                loaded = self._load_json(path, queries)
            elif path.suffix.lower() == ".csv":
                loaded = self._load_csv(path, queries)
            else:
                result.notes.append(f"unsupported manual import file type: {path.suffix}")
                continue
            result.raw_jobs += loaded[0]
            result.jobs.extend(loaded[1])
            result.matched_jobs += len(loaded[1])

        result.diagnostics = context.take_diagnostics()
        return result

    def _load_json(self, path: Path, queries: list[SearchQuery]) -> tuple[int, list[JobListing]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else [payload]
        jobs = [normalize_job_listing(JobListing.model_validate(record)) for record in records]
        matched = [job for job in jobs if self.matches_queries(job, queries)]
        return len(jobs), matched

    def _load_csv(self, path: Path, queries: list[SearchQuery]) -> tuple[int, list[JobListing]]:
        jobs: list[JobListing] = []
        raw_count = 0
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_count += 1
                record = {
                    "id": row.get("id") or row.get("source_url") or row.get("application_url") or row.get("title"),
                    "source": row.get("source") or "manual_import",
                    "source_url": row.get("source_url") or row.get("application_url") or "",
                    "title": row.get("title") or "Unknown title",
                    "company": row.get("company") or "Unknown company",
                    "location": row.get("location"),
                    "work_mode": row.get("work_mode") or "unknown",
                    "description": row.get("description") or "",
                    "required_skills": _split_pipe(row.get("required_skills")),
                    "preferred_skills": _split_pipe(row.get("preferred_skills")),
                    "responsibilities": _split_pipe(row.get("responsibilities")),
                    "minimum_qualifications": _split_pipe(row.get("minimum_qualifications")),
                    "domain_signals": _split_pipe(row.get("domain_signals")),
                    "application_url": row.get("application_url") or row.get("source_url"),
                    "date_posted": row.get("date_posted"),
                }
                job = normalize_job_listing(JobListing.model_validate(record))
                if self.matches_queries(job, queries):
                    jobs.append(job)
        return raw_count, jobs


def _split_pipe(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]
