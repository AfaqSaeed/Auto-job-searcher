# Conversation Start From Stage

- Saved at: 2026-04-15T16:20:10.050820Z

Requested change: add an option to start after a particular step instead of always running the full pipeline from the beginning.\n\nImplemented:\n- added PIPELINE_STAGES constant\n- added JobSearcherPipeline.run_from(start_from, input_path, supplemental_files)\n- run-all now accepts --start-from with these choices: ingest-profile, discover-boards, generate-queries, search-jobs, rank-jobs, report\n- stages before the selected start point are loaded from existing artifacts instead of being rerun\n- added a CLI parser test for --start-from\n\nValidation:\n- py_compile passed for updated files\n- targeted CLI parser test passed\n- run-all --help shows the new --start-from option and choices
