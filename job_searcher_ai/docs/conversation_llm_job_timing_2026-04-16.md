# Conversation LLM Job Timing

- Saved at: 2026-04-16T13:18:14.551197Z

Requested change: expose how long the LLM call takes per ranked job for debugging before changing the ranking strategy.\n\nImplemented:\n- added llm_latency_seconds to JobScore\n- added llm_latency_seconds to ranked CSV export\n- ranking now measures the elapsed time around assess_job_with_llm for each job\n- per-job LLM timing is logged to job_searcher.log as an INFO line in the format: LLM reasoning for <title> @ <company> took X.XXXs\n\nValidation:\n- py_compile passed for updated files\n- targeted scoring test harness passed
