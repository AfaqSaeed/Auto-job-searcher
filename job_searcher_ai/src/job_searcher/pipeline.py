"""Pipeline orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from job_searcher.config import AppConfig, ensure_runtime_directories, load_config, resolve_project_root
from job_searcher.llm.ollama_client import OllamaClient
from job_searcher.logging_utils import setup_logging
from job_searcher.models import PipelineArtifacts
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.profile.summarize import apply_insights, summarize_profile
from job_searcher.queries.generator import generate_search_queries
from job_searcher.ranking.fusion import rank_jobs as fuse_ranked_jobs
from job_searcher.reporting.csv_export import export_ranked_jobs_csv
from job_searcher.reporting.json_export import write_json_output
from job_searcher.reporting.markdown_report import build_search_report_markdown, build_top_matches_markdown
from job_searcher.schemas import JobListing, RankedJob, SearchQuery, SearchReport, UserProfile
from job_searcher.sources import build_enabled_sources
from job_searcher.sources.base import SourceContext, SourceRunResult
from job_searcher.utils.cache import JsonCache


LOGGER = logging.getLogger(__name__)


class JobSearcherPipeline:
    """High-level orchestration for the local job-search workflow."""

    def __init__(self, project_root: Path | None = None, config_path: Path | None = None) -> None:
        self.project_root = resolve_project_root(project_root)
        self.config: AppConfig = load_config(config_path=config_path, project_root=self.project_root)
        ensure_runtime_directories(self.project_root, self.config)
        self.artifacts = PipelineArtifacts.from_root(
            self.project_root,
            self.config.outputs.directory,
            self.config.outputs.cache_directory,
        )
        self.logger = setup_logging(log_file=self.artifacts.output_dir / 'job_searcher.log')
        self.cache = JsonCache(self.artifacts.cache_dir)
        self.llm_client = OllamaClient(self.config.ollama) if self.config.ollama.enabled else None
        self.last_source_runs: list[SourceRunResult] = []

    def ingest_profile(self, input_path: Path, supplemental_files: list[Path] | None = None) -> UserProfile:
        document = read_profile_document(self._resolve_path(input_path), [self._resolve_path(path) for path in supplemental_files or []])
        extracted = extract_profile(document)
        profile = apply_insights(extracted, summarize_profile(extracted, self.llm_client))
        write_json_output(document.model_dump(mode='json'), self.artifacts.profile_document_json)
        write_json_output(profile.model_dump(mode='json'), self.artifacts.profile_structured_json)
        self.logger.info('Profile ingested: %s experiences, %s projects', len(profile.work_experience), len(profile.projects))
        return profile

    def load_profile(self) -> UserProfile:
        return UserProfile.model_validate_json(self.artifacts.profile_structured_json.read_text(encoding='utf-8'))

    def generate_queries(self, profile: UserProfile | None = None) -> list[SearchQuery]:
        active_profile = profile or self.load_profile()
        queries = generate_search_queries(active_profile, self.config)
        write_json_output([query.model_dump(mode='json') for query in queries], self.artifacts.search_queries_json)
        self.logger.info('Generated %s search queries', len(queries))
        return queries

    def load_queries(self) -> list[SearchQuery]:
        payload = self.cache.read_json(self.artifacts.search_queries_json)
        return [SearchQuery.model_validate(item) for item in payload]

    def search_jobs(self, queries: list[SearchQuery] | None = None) -> list[JobListing]:
        active_queries = queries or self.load_queries()
        context = SourceContext(config=self.config, cache=self.cache)
        jobs: list[JobListing] = []
        self.last_source_runs = []
        for source in build_enabled_sources(self.config, self.project_root):
            run = source.fetch_jobs(active_queries, context)
            self.last_source_runs.append(run)
            self.logger.info(run.summary())
            jobs.extend(run.jobs)
        deduped = self._dedupe_jobs(jobs)
        write_json_output([job.model_dump(mode='json') for job in deduped], self.artifacts.discovered_jobs_json)
        self._write_filtered_jobs_debug()
        self._write_custom_career_pages_debug()
        return deduped

    def load_jobs(self) -> list[JobListing]:
        payload = self.cache.read_json(self.artifacts.discovered_jobs_json)
        return [JobListing.model_validate(item) for item in payload]

    def rank_jobs(self, profile: UserProfile | None = None, jobs: list[JobListing] | None = None) -> list[RankedJob]:
        active_profile = profile or self.load_profile()
        active_jobs = jobs or self.load_jobs()
        ranked_jobs = fuse_ranked_jobs(active_profile, active_jobs, self.config, client=self.llm_client)
        write_json_output([item.model_dump(mode='json') for item in ranked_jobs], self.artifacts.jobs_ranked_json)
        export_ranked_jobs_csv(ranked_jobs, self.artifacts.jobs_ranked_csv)
        self.artifacts.top_matches_md.write_text(
            build_top_matches_markdown(ranked_jobs, self.config.outputs.top_n_markdown),
            encoding='utf-8',
        )
        self.logger.info('Ranked %s jobs', len(ranked_jobs))
        return ranked_jobs

    def load_ranked_jobs(self) -> list[RankedJob]:
        payload = self.cache.read_json(self.artifacts.jobs_ranked_json)
        return [RankedJob.model_validate(item) for item in payload]

    def report(
        self,
        profile: UserProfile | None = None,
        queries: list[SearchQuery] | None = None,
        ranked_jobs: list[RankedJob] | None = None,
    ) -> SearchReport:
        active_profile = profile or self.load_profile()
        active_queries = queries or self.load_queries()
        active_ranked_jobs = ranked_jobs or self.load_ranked_jobs()
        source_notes = [run.summary() for run in self.last_source_runs] if self.last_source_runs else []
        report = SearchReport(
            profile_summary=active_profile.summary or active_profile.llm_summary or '',
            sources_searched=[source.name for source in build_enabled_sources(self.config, self.project_root)],
            queries=active_queries,
            total_jobs_discovered=len(self.load_jobs()) if self.artifacts.discovered_jobs_json.exists() else len(active_ranked_jobs),
            total_jobs_ranked=len(active_ranked_jobs),
            top_jobs=active_ranked_jobs[: self.config.outputs.top_n_markdown],
            notes=source_notes + [
                f'Filtered-out jobs debug file: {self.artifacts.filtered_jobs_debug_json.name}',
                f'Custom career page debug file: {self.artifacts.custom_career_pages_debug_json.name}',
                'LLM reasoning is optional and falls back to heuristics when Ollama is unavailable.',
                'Embeddings are disabled by default and require the embeddings extra.',
            ],
        )
        write_json_output(report.model_dump(mode='json'), self.artifacts.search_report_json)
        self.artifacts.search_report_md.write_text(build_search_report_markdown(report), encoding='utf-8')
        self.logger.info('Report written to %s', self.artifacts.search_report_md)
        return report

    def run_all(self, input_path: Path, supplemental_files: list[Path] | None = None) -> SearchReport:
        profile = self.ingest_profile(input_path, supplemental_files=supplemental_files)
        queries = self.generate_queries(profile)
        jobs = self.search_jobs(queries)
        ranked = self.rank_jobs(profile, jobs)
        return self.report(profile, queries, ranked)

    def _resolve_path(self, value: Path) -> Path:
        return value if value.is_absolute() else (self.project_root / value)

    def _write_filtered_jobs_debug(self) -> None:
        payload = [run.filtered_debug_payload() for run in self.last_source_runs if run.filtered_out_jobs]
        write_json_output(payload, self.artifacts.filtered_jobs_debug_json)

    def _write_custom_career_pages_debug(self) -> None:
        payload = [
            run.discovered_debug_payload()
            for run in self.last_source_runs
            if run.source_name == 'custom_career_pages' and run.discovered_jobs
        ]
        write_json_output(payload, self.artifacts.custom_career_pages_debug_json)

    @staticmethod
    def _dedupe_jobs(jobs: list[JobListing]) -> list[JobListing]:
        seen: set[str] = set()
        unique: list[JobListing] = []
        for job in jobs:
            key = f"{job.source}:{job.id}:{job.application_url or job.source_url}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(job)
        return unique
