# Custom Career Pages Change

- Saved at: 2026-04-09T13:13:13.186736Z

Implemented a new custom career page source for job_searcher_ai. Added configurable custom career page entries with same-domain crawling and sitemap fallback, a dedicated outputs/custom_career_pages_debug.json artifact for review, and integration into the existing search and ranking pipeline. Added tests for custom career page discovery and debug payloads. Live validation against the KUKA vacancies page was not possible in this environment because outbound web requests are blocked here.
