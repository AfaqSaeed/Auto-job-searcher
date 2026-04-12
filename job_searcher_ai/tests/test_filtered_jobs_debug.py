from pathlib import Path

from job_searcher.config import load_config
from job_searcher.models import PipelineArtifacts
from job_searcher.schemas import JobListing
from job_searcher.sources.base import SourceRunResult


def test_pipeline_artifacts_include_filtered_jobs_debug() -> None:
    config = load_config(Path('config/settings.yaml'), project_root=Path.cwd())
    artifacts = PipelineArtifacts.from_root(Path.cwd(), config.outputs.directory, config.outputs.cache_directory)

    assert artifacts.filtered_jobs_debug_json.name == 'filtered_jobs_debug.json'
    assert artifacts.custom_career_pages_debug_json.name == 'custom_career_pages_debug.json'
    assert artifacts.custom_career_page_filters_json.name == 'custom_career_page_filters.json'
    assert artifacts.profile_keywords_json.name == 'profile_keywords.json'
    assert artifacts.profile_keywords_md.name == 'profile_keywords.md'
    assert artifacts.site_filtered_jobs_json.name == 'site_filtered_jobs.json'
    assert artifacts.site_filtered_jobs_md.name == 'site_filtered_jobs.md'


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
