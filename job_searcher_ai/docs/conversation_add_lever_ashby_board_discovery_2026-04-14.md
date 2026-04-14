# Add Lever And Ashby Board Discovery

- Saved at: 2026-04-14T13:01:03.052069Z

## Request
Extend the standalone board discovery helper so it checks Lever and Ashby in addition to Greenhouse.

## Change
Updated src\\find_job_borads\\jobs_board_find_multi.py to probe public Lever and Ashby board URLs and APIs alongside Greenhouse, add discovery queries for those ATS providers, store per-ATS slug/url/status/job-count fields, compute has_lever, has_ashby, and has_any_ats flags, and write separate confirmed ATS CSV outputs.

## Result
The board finder now searches for Greenhouse, Lever, and Ashby boards in the same pass and exports combined as well as ATS-specific company lists.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\find_job_borads\\jobs_board_find_multi.py and src\\find_job_borads\\job_borad_find.py, then ran the compatibility entrypoint with --help.
