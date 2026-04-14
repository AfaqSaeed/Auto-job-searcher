# Query Filter Scoring And Filtered-Job Diagnostics

- Saved at: 2026-04-14T04:01:34.113403Z

## Request
Improve the weak source-level matching filter and include scoring statistics for filtered-out jobs, including how similar each filtered job was to the generated queries.

## Change
Updated src\\job_searcher\\sources\\base.py to replace the old substring-or-Jaccard gate with a field-aware query-match evaluator that scores title, domain, location, token overlap, and overall text similarity per query. Wired all source connectors to use the shared apply_query_filter() path so filtered jobs carry structured query-match diagnostics. Existing filtered_jobs_debug.json was backfilled offline from the saved jobs and queries so the new fields are available immediately.

## Result
The filter is now less crude, and filtered_jobs_debug.json contains per-job query_match statistics such as best_query, best_query_score, best_query_similarity, title score, domain score, location score, and term overlap.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on the updated source modules and backfilled outputs\\filtered_jobs_debug.json from the saved queries and filtered jobs. Verified that the JSON now contains query_match, best_query_score, and best_query_similarity fields.
