from pathlib import Path

from job_searcher.config import load_config
from job_searcher.models import PipelineArtifacts
from job_searcher.pipeline import JobSearcherPipeline
from job_searcher.schemas import JobListing
from job_searcher.sources.base import SourceRunResult


def test_pipeline_artifacts_include_filtered_jobs_debug() -> None:
    config = load_config(Path('config/settings.yaml'), project_root=Path.cwd())
    artifacts = PipelineArtifacts.from_root(Path.cwd(), config.outputs.directory, config.outputs.cache_directory)

    assert artifacts.filtered_jobs_debug_json.name == 'filtered_jobs_debug.json'
    assert artifacts.filtered_jobs_debug_partial_json.name == 'filtered_jobs_debug.partial.json'
    assert artifacts.custom_career_pages_debug_json.name == 'custom_career_pages_debug.json'
    assert artifacts.custom_career_pages_debug_partial_json.name == 'custom_career_pages_debug.partial.json'
    assert artifacts.custom_career_page_filters_json.name == 'custom_career_page_filters.json'
    assert artifacts.custom_career_page_filters_partial_json.name == 'custom_career_page_filters.partial.json'
    assert artifacts.profile_keywords_json.name == 'profile_keywords.json'
    assert artifacts.profile_keywords_md.name == 'profile_keywords.md'
    assert artifacts.site_filtered_jobs_json.name == 'site_filtered_jobs.json'
    assert artifacts.site_filtered_jobs_partial_json.name == 'site_filtered_jobs.partial.json'
    assert artifacts.site_filtered_jobs_md.name == 'site_filtered_jobs.md'
    assert artifacts.discovered_jobs_partial_json.name == 'discovered_jobs.partial.json'
    assert artifacts.jobs_ranked_partial_json.name == 'jobs_ranked.partial.json'
    assert artifacts.jobs_ranked_partial_csv.name == 'jobs_ranked.partial.csv'
    assert artifacts.top_matches_partial_md.name == 'top_matches.partial.md'
    assert artifacts.pipeline_state_json.name == 'pipeline_state.json'


def test_source_run_result_debug_payload_includes_filtered_jobs() -> None:
    job = JobListing(
        id='job-1',
        source='manual_import',
        source_url='https://example.com/job-1',
        title='Data Scientist',
        company='Example Co',
        description='Irrelevant role',
        required_skills=[],
        preferred_skills=[],
        responsibilities=[],
        minimum_qualifications=[],
        domain_signals=[],
    )
    run = SourceRunResult(source_name='manual_import', raw_jobs=1, matched_jobs=0, filtered_out_jobs=[job], discovered_jobs=[job])

    payload = run.filtered_debug_payload()
    discovered_payload = run.discovered_debug_payload()

    assert payload['filtered_out_count'] == 1
    assert payload['filtered_out_jobs'][0]['title'] == 'Data Scientist'
    assert discovered_payload['discovered_jobs'][0]['title'] == 'Data Scientist'


def test_source_run_result_can_merge_partial_runs() -> None:
    job = JobListing(
        id='job-2',
        source='custom_career_pages',
        source_url='https://example.com/job-2',
        title='Vision Engineer',
        company='Example Co',
        description='Relevant vision role',
        required_skills=[],
        preferred_skills=[],
        responsibilities=[],
        minimum_qualifications=[],
        domain_signals=[],
    )
    aggregate = SourceRunResult(source_name='custom_career_pages')
    partial = SourceRunResult(source_name='custom_career_pages', raw_jobs=1, matched_jobs=1, jobs=[job], discovered_jobs=[job])

    aggregate.merge_from(partial)

    assert aggregate.raw_jobs == 1
    assert aggregate.matched_jobs == 1
    assert aggregate.jobs[0].title == 'Vision Engineer'


def test_pipeline_state_skips_completed_step_when_fingerprint_matches(tmp_path: Path) -> None:
    (tmp_path / 'config').mkdir()
    (tmp_path / 'src').mkdir()
    (tmp_path / 'config' / 'settings.yaml').write_text('{}', encoding='utf-8')

    pipeline = JobSearcherPipeline(project_root=tmp_path)
    artifact = pipeline.artifacts.output_dir / 'dummy.json'
    artifact.write_text('{}', encoding='utf-8')

    pipeline._mark_step_completed('generate_queries', 'abc123', [artifact])

    assert pipeline._should_skip_step('generate_queries', 'abc123', [artifact]) is True
    assert pipeline._should_skip_step('generate_queries', 'different', [artifact]) is False
