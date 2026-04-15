# Conversation Search Checkpointing

- Saved at: 2026-04-15T14:58:24.380798Z

Requested change: add checkpointing behavior for long-running job searches so partial search outputs are persisted during crawling instead of only at the end of the search stage.\n\nImplemented:\n- partial checkpoint artifacts for discovered jobs, filtered jobs, custom career page debug data, custom career page filter snapshots, and site-filtered jobs\n- shared checkpoint callback support in SourceContext\n- periodic checkpoint writes during Greenhouse, Lever, Ashby, and custom career page crawling\n- deeper custom career page checkpointing during candidate page parsing so long Fraunhofer-style runs persist progress mid-source\n- cleanup of partial checkpoint files after a successful full search write\n- tests for new artifact paths and partial SourceRunResult merging\n\nValidation:\n- py_compile passed for updated source and test files\n- targeted test harness passed for checkpoint-related tests
