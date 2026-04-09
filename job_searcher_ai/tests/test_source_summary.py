from job_searcher.sources.base import RequestDiagnostic, SourceRunResult


def test_source_summary_explains_404() -> None:
    run = SourceRunResult(
        source_name='greenhouse',
        diagnostics=[RequestDiagnostic(url='https://example.com', status_code=404, kind='http_error', message='404')],
    )
    summary = run.summary()
    assert 'wrong board slug' in summary or 'not using that ATS' in summary


def test_source_summary_explains_filtering() -> None:
    run = SourceRunResult(source_name='manual_import', raw_jobs=5, matched_jobs=0)
    summary = run.summary()
    assert 'filtered out by the generated queries' in summary
