# Feed Discovered ATS Boards Into Job Search

- Saved at: 2026-04-14T13:05:26.157372Z

## Request
Feed the discovered Greenhouse, Lever, and Ashby boards directly into the main job_searcher pipeline instead of keeping board discovery separate.

## Change
Added Ashby board support to the main config and source registry, implemented src\\job_searcher\\sources\\ashby.py, added parse_ashby_job() in src\\job_searcher\\parsing\\jobs.py, and updated src\\job_searcher\\pipeline.py so search_jobs() automatically merges discovered Greenhouse, Lever, and Ashby slugs from outputs\\job_board_company_discovery_results.csv into the active source configuration. This means run-all now discovers boards first and then searches those discovered ATS boards directly.

## Result
The main job_searcher pipeline can now ingest jobs from discovered Greenhouse, Lever, and Ashby boards without manually copying slugs into settings.yaml.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on the updated config, parser, source, registry, and pipeline files. Also ran C:\\Users\\afaqs\\anaconda3\\python.exe -m job_searcher --project-root d:\\Autojobapply\\job_searcher_ai search-jobs --help as a CLI smoke test.
