# Filtered Jobs Debug Session

- Saved at: 2026-04-09T12:18:36.265805Z

## User Request
Save filtered-out jobs for debugging purposes so raw jobs rejected by query matching can be inspected.

## Work Completed
- Added `filtered_jobs_debug.json` as a pipeline artifact.
- Extended source run results to keep `filtered_out_jobs` in addition to matched jobs.
- Updated Greenhouse, Lever, manual-import, RSS, and static-page connectors to retain filtered jobs.
- Updated the pipeline to write `outputs\filtered_jobs_debug.json` after `search-jobs`.
- Added tests covering the new debug artifact path and payload structure.

## Validation
- `C:\Users\afaqs\anaconda3\python.exe -m compileall .\job_searcher_ai\src .\job_searcher_ai\tests`
- Manual execution of the lightweight test harness
- CLI smoke test: `python -m job_searcher search-jobs`

## Notes
- The generated debug file can become large because it stores full normalized job payloads for every filtered job.
- In the current run, `outputs\filtered_jobs_debug.json` was created and contains 113 filtered Wayve Greenhouse jobs.
