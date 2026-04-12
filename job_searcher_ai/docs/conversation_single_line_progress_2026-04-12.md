# Single-Line Progress Output

- Saved at: 2026-04-12T19:35:16.315869Z

## Request
Make the live terminal output dynamic so progress updates reuse one line instead of printing many separate lines.

## Change
Updated src\\job_searcher\\logging_utils.py to render progress and timed-operation status on a single in-place console line for interactive terminals. Added a progress-aware stream handler that clears the in-place status before normal log records are printed. Non-interactive terminals still fall back to regular log lines.

## Result
During local runs in an interactive terminal, progress now updates in place rather than spamming many lines. The file log remains available for persistent output, while the live console stays much quieter.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\logging_utils.py.
