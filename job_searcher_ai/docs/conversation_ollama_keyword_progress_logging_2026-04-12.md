# Ollama Keyword Progress Logging

- Saved at: 2026-04-12T17:33:52.389585Z

## Request
Add visible output while profile keywords are being extracted with Ollama so the user can tell the system is working.

## Change
Added info-level logging in src/job_searcher/profile/summarize.py before and after the Ollama profile-insights request.

## Result
The log now shows when profile keyword extraction starts, which Ollama model is being used, and when the response completes with counts for role families, search keywords, and domain strengths.

## Validation
Ran a targeted syntax check with C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\profile\\summarize.py.
