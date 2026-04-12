# Keyword Pack And Site-Filter Outputs

- Saved at: 2026-04-12T17:05:12.953607Z

Extended the pipeline so profile-derived and LLM-assisted keywords are exported in two formats: outputs/profile_keywords.json for machine use and outputs/profile_keywords.md for review. Also extended the custom career page source and pipeline so jobs found specifically through site-native filter execution are exported in outputs/site_filtered_jobs.json and outputs/site_filtered_jobs.md. This makes the extracted keyword set and the site-filter matches both debuggable and reusable for later automation.
