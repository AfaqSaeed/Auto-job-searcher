# Conversation Limit LLM To Shortlist

- Saved at: 2026-04-16T13:42:13.759329Z

Requested change: avoid calling the LLM for every ranked job because measured Ollama latency was about 45 seconds per job.\n\nImplemented:\n- added ranking config section with:\n  - llm_enabled\n  - llm_top_n\n  - llm_min_rules_score\n- ranking now runs in two passes:\n  1. fast rules/embedding scoring for all jobs to form a preliminary ranking\n  2. Ollama reasoning only for the configured shortlist\n- jobs outside the shortlist still receive heuristic qualitative assessment, but no Ollama call\n- kept per-job LLM timing for shortlisted jobs\n- added regression coverage that only the configured shortlist calls the LLM path\n\nValidation:\n- py_compile passed for updated files\n- updated scoring test harness passed
