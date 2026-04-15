"""Pipeline orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
import json
import csv

from find_job_borads.jobs_board_find_multi import run_board_discovery
from job_searcher.config import AppConfig, ensure_runtime_directories, load_config, resolve_project_root
from job_searcher.llm.ollama_client import OllamaClient
from job_searcher.logging_utils import ProgressLogger, log_timed_operation, setup_logging
from job_searcher.models import PipelineArtifacts
from job_searcher.profile.extract import extract_profile
from job_searcher.profile.ingest import read_profile_document
from job_searcher.profile.summarize import apply_insights, summarize_profile
from job_searcher.queries.generator import generate_search_queries
from job_searcher.ranking.fusion import rank_jobs as fuse_ranked_jobs
from job_searcher.reporting.csv_export import export_ranked_jobs_csv
from job_searcher.reporting.json_export import write_json_output
from job_searcher.reporting.markdown_report import build_search_report_markdown, build_top_matches_markdown
from job_searcher.schemas import JobListing, RankedJob, SearchQuery, SearchReport, SearchSourceStats, UserProfile
from job_searcher.sources import build_enabled_sources
from job_searcher.sources.base import SourceContext, SourceRunResult
from job_searcher.utils.cache import JsonCache
from job_searcher.utils.text import unique_preserve_order


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
        self._write_profile_keyword_artifacts(profile)
        self.logger.info('Profile ingested: %s experiences, %s projects', len(profile.work_experience), len(profile.projects))
        return profile

    def load_profile(self) -> UserProfile:
        profile = UserProfile.model_validate_json(self.artifacts.profile_structured_json.read_text(encoding='utf-8'))
        self._ensure_profile_keyword_artifacts(profile)
        return profile

    def generate_queries(self, profile: UserProfile | None = None) -> list[SearchQuery]:
        active_profile = profile or self.load_profile()
        queries = generate_search_queries(active_profile, self.config)
        write_json_output([query.model_dump(mode='json') for query in queries], self.artifacts.search_queries_json)
        self.logger.info('Generated %s search queries', len(queries))
        return queries

    def discover_job_boards(self, profile: UserProfile | None = None) -> dict:
        active_profile = profile or self.load_profile()
        with log_timed_operation(
            self.logger,
            'Job board discovery',
            heartbeat_seconds=15.0,
        ):
            metadata = run_board_discovery(
                project_root=self.project_root,
                profile=active_profile,
                config=self.config,
                output_dir=self.artifacts.output_dir,
            )
        self.logger.info(
            'Job board discovery completed: %s queries, %s candidate companies',
            len(metadata.get('queries_used', [])),
            metadata.get('candidate_company_count', 0),
        )
        return metadata

    def load_queries(self) -> list[SearchQuery]:
        payload = self.cache.read_json(self.artifacts.search_queries_json)
        return [SearchQuery.model_validate(item) for item in payload]

    def search_jobs(self, queries: list[SearchQuery] | None = None) -> list[JobListing]:
        active_queries = queries or self.load_queries()
        effective_config = self._config_with_discovered_boards()
        context = SourceContext(config=effective_config, cache=self.cache)
        context.checkpoint_callback = self._write_search_checkpoint
        jobs: list[JobListing] = []
        self.last_source_runs = []
        sources = build_enabled_sources(effective_config, self.project_root)
        with log_timed_operation(
            self.logger,
            f"Job search across {len(sources)} enabled sources",
            heartbeat_seconds=15.0,
        ):
            source_progress = ProgressLogger(self.logger, "Source search", len(sources), min_interval_seconds=3.0)
            for source in sources:
                with log_timed_operation(
                    self.logger,
                    f"Searching source {source.name}",
                    heartbeat_seconds=10.0,
                ):
                    run = source.fetch_jobs(active_queries, context)
                self.last_source_runs.append(run)
                self.logger.debug(run.summary())
                jobs.extend(run.jobs)
                self._write_search_artifacts()
                source_progress.advance()
            source_progress.finish()
        deduped = self._dedupe_jobs(jobs)
        self._write_search_artifacts()
        self._clear_search_checkpoint_artifacts()
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
        source_stats = self._build_report_source_stats()
        source_notes = [run.summary() for run in self.last_source_runs] if self.last_source_runs else []
        report = SearchReport(
            profile_summary=active_profile.summary or active_profile.llm_summary or '',
            sources_searched=[source.name for source in build_enabled_sources(self._config_with_discovered_boards(), self.project_root)],
            queries=active_queries,
            total_jobs_raw_discovered=sum(item.raw_jobs_discovered for item in source_stats),
            total_jobs_filtered_out=sum(item.jobs_filtered_out for item in source_stats),
            total_jobs_discovered=len(self.load_jobs()) if self.artifacts.discovered_jobs_json.exists() else len(active_ranked_jobs),
            total_jobs_ranked=len(active_ranked_jobs),
            source_stats=source_stats,
            top_jobs=active_ranked_jobs[: self.config.outputs.top_n_markdown],
            notes=source_notes + [
                f'Filtered-out jobs debug file: {self.artifacts.filtered_jobs_debug_json.name}',
                f'Custom career page debug file: {self.artifacts.custom_career_pages_debug_json.name}',
                f'Custom career page filters file: {self.artifacts.custom_career_page_filters_json.name}',
                f'Profile keyword files: {self.artifacts.profile_keywords_json.name}, {self.artifacts.profile_keywords_md.name}',
                f'Site-filtered job files: {self.artifacts.site_filtered_jobs_json.name}, {self.artifacts.site_filtered_jobs_md.name}',
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
        self.discover_job_boards(profile)
        queries = self.generate_queries(profile)
        jobs = self.search_jobs(queries)
        ranked = self.rank_jobs(profile, jobs)
        return self.report(profile, queries, ranked)

    def _resolve_path(self, value: Path) -> Path:
        return value if value.is_absolute() else (self.project_root / value)

    def _ensure_profile_keyword_artifacts(self, profile: UserProfile) -> None:
        if self.artifacts.profile_keywords_json.exists() and self.artifacts.profile_keywords_md.exists():
            return
        self._write_profile_keyword_artifacts(profile)

    def _write_profile_keyword_artifacts(self, profile: UserProfile) -> None:
        payload = {
            'summary': profile.llm_summary or profile.summary,
            'role_families': profile.role_families,
            'search_keywords': profile.search_keywords,
            'domain_strengths': profile.domain_strengths,
            'industries': profile.industries,
            'skills': [skill.name for skill in profile.skills],
            'tools': profile.tools,
            'programming_languages': profile.programming_languages,
            'research_topics': profile.research_topics,
            'locations': profile.locations,
        }
        write_json_output(payload, self.artifacts.profile_keywords_json)
        sections = [
            ('Summary', [payload['summary']] if payload['summary'] else []),
            ('Role Families', payload['role_families']),
            ('Search Keywords', payload['search_keywords']),
            ('Domain Strengths', payload['domain_strengths']),
            ('Industries', payload['industries']),
            ('Skills', payload['skills']),
            ('Tools', payload['tools']),
            ('Programming Languages', payload['programming_languages']),
            ('Research Topics', payload['research_topics']),
            ('Locations', payload['locations']),
        ]
        lines = ['# Profile Keyword Pack', '']
        for title, values in sections:
            if not values:
                continue
            lines.append(f'## {title}')
            lines.append('')
            for value in values:
                lines.append(f'- {value}')
            lines.append('')
        self.artifacts.profile_keywords_md.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    def _write_filtered_jobs_debug(self) -> None:
        self._write_filtered_jobs_debug_to_path(self.last_source_runs, self.artifacts.filtered_jobs_debug_json)

    def _write_custom_career_pages_debug(self) -> None:
        self._write_custom_career_pages_debug_to_path(
            self.last_source_runs,
            self.artifacts.custom_career_pages_debug_json,
        )

    def _write_custom_career_page_filters_debug(self) -> None:
        self._write_custom_career_page_filters_debug_to_path(
            self.last_source_runs,
            self.artifacts.custom_career_page_filters_json,
        )

    def _write_site_filtered_jobs_artifacts(self) -> None:
        self._write_site_filtered_jobs_artifacts_to_paths(
            self.last_source_runs,
            self.artifacts.site_filtered_jobs_json,
            self.artifacts.site_filtered_jobs_md,
        )

    def _write_search_checkpoint(self, current_run: SourceRunResult) -> None:
        self._write_search_artifacts(current_run=current_run, partial=True)

    def _write_search_artifacts(self, current_run: SourceRunResult | None = None, partial: bool = False) -> None:
        runs = list(self.last_source_runs)
        if current_run is not None:
            runs.append(current_run)

        discovered_path = self.artifacts.discovered_jobs_partial_json if partial else self.artifacts.discovered_jobs_json
        filtered_path = (
            self.artifacts.filtered_jobs_debug_partial_json if partial else self.artifacts.filtered_jobs_debug_json
        )
        custom_debug_path = (
            self.artifacts.custom_career_pages_debug_partial_json
            if partial
            else self.artifacts.custom_career_pages_debug_json
        )
        filter_path = (
            self.artifacts.custom_career_page_filters_partial_json
            if partial
            else self.artifacts.custom_career_page_filters_json
        )
        site_filtered_json = (
            self.artifacts.site_filtered_jobs_partial_json if partial else self.artifacts.site_filtered_jobs_json
        )

        deduped = self._dedupe_jobs([job for run in runs for job in run.jobs])
        write_json_output([job.model_dump(mode='json') for job in deduped], discovered_path)
        self._write_filtered_jobs_debug_to_path(runs, filtered_path)
        self._write_custom_career_pages_debug_to_path(runs, custom_debug_path)
        self._write_custom_career_page_filters_debug_to_path(runs, filter_path)
        self._write_site_filtered_jobs_artifacts_to_paths(runs, site_filtered_json, self.artifacts.site_filtered_jobs_md)

    def _clear_search_checkpoint_artifacts(self) -> None:
        for path in [
            self.artifacts.discovered_jobs_partial_json,
            self.artifacts.filtered_jobs_debug_partial_json,
            self.artifacts.custom_career_pages_debug_partial_json,
            self.artifacts.custom_career_page_filters_partial_json,
            self.artifacts.site_filtered_jobs_partial_json,
        ]:
            if path.exists():
                path.unlink()

    @staticmethod
    def _write_filtered_jobs_debug_to_path(runs: list[SourceRunResult], path: Path) -> None:
        payload = [run.filtered_debug_payload() for run in runs if run.filtered_out_jobs]
        write_json_output(payload, path)

    @staticmethod
    def _write_custom_career_pages_debug_to_path(runs: list[SourceRunResult], path: Path) -> None:
        payload = [
            run.discovered_debug_payload()
            for run in runs
            if run.source_name == 'custom_career_pages' and run.discovered_jobs
        ]
        write_json_output(payload, path)

    @staticmethod
    def _write_custom_career_page_filters_debug_to_path(runs: list[SourceRunResult], path: Path) -> None:
        payload = [
            {
                'source_name': run.source_name,
                'filter_snapshots': run.debug_data.get('filter_snapshots', []),
            }
            for run in runs
            if run.source_name == 'custom_career_pages' and run.debug_data.get('filter_snapshots')
        ]
        write_json_output(payload, path)

    @staticmethod
    def _write_site_filtered_jobs_artifacts_to_paths(
        runs: list[SourceRunResult],
        json_path: Path,
        markdown_path: Path,
    ) -> None:
        jobs_payload: list[dict] = []
        for run in runs:
            if run.source_name != 'custom_career_pages':
                continue
            jobs_payload.extend(run.debug_data.get('site_filter_jobs', []))
        write_json_output(jobs_payload, json_path)

        lines = ['# Site-Filtered Job Matches', '']
        if not jobs_payload:
            lines.append('No site-filtered jobs were captured in this run.')
        else:
            for job in jobs_payload:
                title = job.get('title', 'Unknown title')
                company = job.get('company', 'Unknown company')
                location = job.get('location') or 'Unknown location'
                url = job.get('source_url') or job.get('application_url') or ''
                lines.append(f'## {title} @ {company}')
                lines.append('')
                lines.append(f'- Location: {location}')
                lines.append(f'- Source: {job.get("source", "custom_career_pages")}')
                if url:
                    lines.append(f'- URL: {url}')
                discovery_method = (job.get('raw_payload') or {}).get('discovery_method')
                if discovery_method:
                    lines.append(f'- Discovery method: {discovery_method}')
                lines.append('')
        markdown_path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    def _build_report_source_stats(self) -> list[SearchSourceStats]:
        if self.last_source_runs:
            return [
                SearchSourceStats(
                    source_name=run.source_name,
                    raw_jobs_discovered=run.raw_jobs,
                    jobs_matched=run.matched_jobs,
                    jobs_filtered_out=len(run.filtered_out_jobs),
                )
                for run in self.last_source_runs
            ]

        by_source: dict[str, SearchSourceStats] = {}
        if self.artifacts.filtered_jobs_debug_json.exists():
            payload = self.cache.read_json(self.artifacts.filtered_jobs_debug_json)
            for item in payload:
                source_name = item.get('source_name')
                if not source_name:
                    continue
                by_source[source_name] = SearchSourceStats(
                    source_name=source_name,
                    raw_jobs_discovered=int(item.get('raw_jobs', 0) or 0),
                    jobs_matched=int(item.get('matched_jobs', 0) or 0),
                    jobs_filtered_out=int(item.get('filtered_out_count', 0) or 0),
                )
        if self.artifacts.custom_career_pages_debug_json.exists():
            payload = self.cache.read_json(self.artifacts.custom_career_pages_debug_json)
            for item in payload:
                source_name = item.get('source_name')
                if not source_name:
                    continue
                stats = by_source.get(source_name, SearchSourceStats(source_name=source_name))
                stats.raw_jobs_discovered = max(stats.raw_jobs_discovered, int(item.get('raw_jobs', 0) or 0))
                stats.jobs_matched = max(stats.jobs_matched, int(item.get('matched_jobs', 0) or 0))
                stats.jobs_filtered_out = max(stats.jobs_filtered_out, int(item.get('filtered_out_count', 0) or 0))
                by_source[source_name] = stats
        return list(by_source.values())

    def _config_with_discovered_boards(self) -> AppConfig:
        updated = self.config.model_copy(deep=True)
        discovered = self._load_discovered_board_slugs()
        updated.sources.greenhouse_boards = unique_preserve_order(
            updated.sources.greenhouse_boards + discovered["greenhouse"]
        )
        updated.sources.lever_boards = unique_preserve_order(
            updated.sources.lever_boards + discovered["lever"]
        )
        updated.sources.ashby_boards = unique_preserve_order(
            updated.sources.ashby_boards + discovered["ashby"]
        )
        if updated.sources.ashby_boards:
            updated.sources.toggles.ashby = True
        return updated

    def _load_discovered_board_slugs(self) -> dict[str, list[str]]:
        path = self.artifacts.output_dir / "job_board_company_discovery_results.csv"
        if not path.exists():
            return {"greenhouse": [], "lever": [], "ashby": []}

        found = {"greenhouse": [], "lever": [], "ashby": []}
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                greenhouse_slug = (row.get("greenhouse_slug") or "").strip()
                lever_slug = (row.get("lever_slug") or "").strip()
                ashby_slug = (row.get("ashby_slug") or "").strip()
                if greenhouse_slug:
                    found["greenhouse"].append(greenhouse_slug)
                if lever_slug:
                    found["lever"].append(lever_slug)
                if ashby_slug:
                    found["ashby"].append(ashby_slug)
        return {
            key: unique_preserve_order(values)
            for key, values in found.items()
        }

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
