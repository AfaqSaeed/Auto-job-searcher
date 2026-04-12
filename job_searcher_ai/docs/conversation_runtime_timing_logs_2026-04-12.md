# Runtime Timing Logs

- Saved at: 2026-04-12T18:25:32.544680Z

## Request
Change the runtime logging so the terminal shows elapsed time for long operations rather than job-count summaries, with particular focus on the Ollama keyword-extraction step and the search phase.

## Change
Added a reusable timed-operation logger with periodic heartbeat messages in src\\job_searcher\\logging_utils.py. Wired it into src\\job_searcher\\profile\\summarize.py for the Ollama keyword-extraction step and into src\\job_searcher\\pipeline.py for the overall search phase and each enabled source. The per-source job-count summary was demoted out of the INFO terminal path.

## Result
The terminal now shows start, periodic elapsed-time updates, and finish time for the LLM keyword extraction and source-search operations. Search result counts remain available in the saved artifacts instead of being printed during the run.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\logging_utils.py, src\\job_searcher\\profile\\summarize.py, and src\\job_searcher\\pipeline.py.
