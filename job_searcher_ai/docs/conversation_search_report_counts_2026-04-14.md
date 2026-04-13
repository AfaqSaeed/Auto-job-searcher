# Search Report Discovery Counts

- Saved at: 2026-04-13T22:46:11.949794Z

## Request
Make the report show clear statistics for how many jobs were discovered and how many were filtered out after running the whole pipeline.

## Change
Updated src\\job_searcher\\schemas.py, src\\job_searcher\\pipeline.py, and src\\job_searcher\\reporting\\markdown_report.py so the report now includes raw discovered count, filtered-out count, matched count, and per-source breakdowns. The pipeline can also rebuild those source stats from saved debug artifacts when report() is run in a fresh process.

## Result
outputs\\search_report.md and outputs\\search_report.json now explicitly show raw discovered jobs, filtered-out jobs, matched jobs, and source-level counts instead of only the matched count.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on the updated files and regenerated outputs\\search_report.md from the existing artifacts.
