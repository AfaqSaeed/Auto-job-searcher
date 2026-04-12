# Profile Keyword Artifact Backfill

- Saved at: 2026-04-12T22:17:26.477946Z

## Request
Investigate why the profile keyword files were not present in outputs and fix the pipeline so they are generated reliably.

## Cause
The keyword artifacts were only written during ingest-profile. Later commands such as generate-queries, search-jobs, rank-jobs, or report load the structured profile from disk but did not recreate the keyword files if they were missing.

## Change
Updated src\\job_searcher\\pipeline.py so load_profile() ensures profile_keywords.json and profile_keywords.md exist and backfills them from the saved structured profile when necessary.

## Result
The pipeline now regenerates the keyword artifacts automatically whenever an existing profile is loaded and the files are missing.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\pipeline.py and executed a minimal profile-load backfill to recreate outputs\\profile_keywords.json and outputs\\profile_keywords.md.
