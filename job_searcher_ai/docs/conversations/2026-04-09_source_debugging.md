# Source Debugging Session

- Saved at: 2026-04-09T11:58:46.137533Z

## User Request
Improve source debugging so zero-job results explain whether the cause was a bad board slug, blocked request, or query filtering.

## Work Completed
- Added `RequestDiagnostic` and `SourceRunResult` to the source layer.
- Updated Greenhouse, Lever, RSS, static-page, and manual-import connectors to return raw-job counts, matched-job counts, notes, and request diagnostics.
- Updated the pipeline to log human-readable source summaries and include them in report notes.
- Added tests for zero-job summary explanations.
- Hardened profile ingestion against UTF-8 BOM content and relaxed the sample profile test so it remains valid with updated sample data.

## Validation
- `C:\Users\afaqs\anaconda3\python.exe -m compileall .\job_searcher_ai\src .\job_searcher_ai\tests`
- Manual execution of all test functions through a Python harness
- CLI smoke test: `python -m job_searcher search-jobs`

## Example Outcome
A zero-job result now logs messages like:
- `Fetched 0 jobs from greenhouse: endpoint returned 404, which usually means a wrong board slug or the company is not using that ATS`
- `Fetched 0 jobs from greenhouse: got 113 raw jobs, but all were filtered out by the generated queries`
