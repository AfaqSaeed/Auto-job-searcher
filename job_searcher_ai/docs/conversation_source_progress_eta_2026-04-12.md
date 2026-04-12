# Source Progress And ETA Logging

- Saved at: 2026-04-12T19:14:20.220652Z

## Request
Show progress while a source is being processed, including how many work items are done out of the total and a rough time-left estimate, instead of only timing start and finish.

## Change
Added a shared ProgressLogger in src\\job_searcher\\logging_utils.py and wired it into src\\job_searcher\\pipeline.py plus the Greenhouse, Lever, and custom career-page sources. The runtime log now reports progress for source count, board count, candidate-page parsing, rendered URL processing, and site-filter plan execution with elapsed time and rough ETA.

## Result
The terminal can now show progress lines such as done/total with a rough remaining time while sources are still running, which makes long search phases easier to judge in real time.

## Validation
Ran C:\\Users\\afaqs\\anaconda3\\python.exe -m py_compile on src\\job_searcher\\logging_utils.py, src\\job_searcher\\pipeline.py, src\\job_searcher\\sources\\greenhouse.py, src\\job_searcher\\sources\\lever.py, and src\\job_searcher\\sources\\custom_career_pages.py.
