# Run-All Board Discovery Integration

- Saved at: 2026-04-13T02:50:39.509800Z

## Request
Make the standalone board discovery helper part of the main run-all pipeline.

## Change
Integrated board discovery into src\\job_searcher\\pipeline.py by adding a discover_job_boards() stage that reuses the already-ingested profile and existing config, then calls the board finder directly. Updated src\\job_searcher\\cli.py to expose a dedicated discover-boards command as well. Added a reusable run_board_discovery() entrypoint in src\\find_job_borads\\jobs_board_find_multi.py so the pipeline can call it without redoing profile ingestion from scratch.

## Result
python -m job_searcher run-all now includes board discovery automatically, and python -m job_searcher discover-boards can run that stage independently.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\pipeline.py, src\\job_searcher\\cli.py, and src\\find_job_borads\\jobs_board_find_multi.py. Also ran C:\\Users\\afaqs\\anaconda3\\python.exe -m job_searcher --project-root d:\\Autojobapply\\job_searcher_ai discover-boards --help as a CLI smoke test.
