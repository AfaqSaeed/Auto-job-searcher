# Explainable Talent Matching

- Saved at: 2026-07-03T10:06:41.106174Z

## Request
Implement explainable candidate-to-job matching with requirement extraction, evidence retrieval, requirement assessments, claim checking, CLI, Streamlit UI, exports, config, tests, examples, and README updates on feature/explainable-talent-matching.

## Change
Added job_searcher.matching with schemas, deterministic and optional Ollama-assisted requirement extraction, evidence building, assessment, claim checking, and report service. Added CLI command explain-match, JSON and Markdown exports, Streamlit app, matching config, sample files, and documentation.

## Validation
Ran full tests with plugin autoload and pytest cache disabled: C:\Users\afaqs\anaconda3\python.exe -m pytest -q -p no:cacheprovider. Result: 35 passed in 2.15s. Also smoke-tested the CLI with sample inputs; Ollama returned 404 and the system fell back to heuristics.
