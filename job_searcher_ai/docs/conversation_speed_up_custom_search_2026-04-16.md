# Conversation Speed Up Custom Search

- Saved at: 2026-04-16T18:11:25.797800Z

Requested change: speed up the searching part, especially the expensive custom career page path.\n\nImplemented:\n- added custom career page config knobs:\n  - candidate_parse_workers\n  - max_site_filter_plans\n  - max_site_filter_candidate_urls\n  - discovery_strategy\n- custom career page candidate page parsing is now parallelized with a thread pool\n- site-filter plan generation now respects max_site_filter_plans\n- site-filter URL collection now stops once max_site_filter_candidate_urls is reached\n- config tuned for the current heavy sources:\n  - KUKA uses site_filters_only, fewer plans, fewer candidate URLs, fewer workers\n  - Fraunhofer uses site_filters_only, capped plans, capped candidate URLs, more workers\n- added regression coverage for max_site_filter_plans\n\nValidation:\n- py_compile passed for updated files\n- custom-career-page test harness passed
