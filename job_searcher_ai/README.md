# job_searcher_ai

`job_searcher_ai` is a command-line job discovery and ranking assistant built for personal job hunting. It ingests a long-form profile, extracts structured strengths, generates search queries, pulls public jobs from supported sources, scores them with interpretable rules plus optional local AI, and produces reviewable outputs.

The v1 design is intentionally local-first:

- Uses Ollama by default for local LLM reasoning.
- Works without paid APIs.
- Stores intermediate JSON so every stage is inspectable.
- Avoids auto-apply behavior.
- Respects public-source boundaries and does not attempt login bypass or anti-bot evasion.

## Features

- Profile ingestion from Markdown and text files
- Deterministic skill, domain, role, and industry extraction
- Optional Ollama-based summarization and fit explanations
- Search query generation with adjacent-role expansion
- Public source connectors for Greenhouse, Lever, RSS, static pages, and manual imports
- Hybrid ranking with symbolic scoring, optional embeddings, and qualitative reasoning
- CSV, JSON, and Markdown outputs
- Cache layer for repeated fetches

## Repository layout

```text
job_searcher_ai/
  config/
  data/
  docs/
  outputs/
  scripts/
  src/job_searcher/
  tests/
```

## Setup

1. Create and activate a Python 3.11+ environment.
2. Install the package in editable mode.

```powershell
cd d:\Autojobapply\job_searcher_ai
C:\Users\afaqs\anaconda3\python.exe -m pip install -e .[dev]
```

Optional extras:

- Embeddings: `C:\Users\afaqs\anaconda3\python.exe -m pip install -e .[dev,embeddings]`
- Streamlit UI experiments: `C:\Users\afaqs\anaconda3\python.exe -m pip install -e .[ui]`
- Browser automation for future dynamic pages: `C:\Users\afaqs\anaconda3\python.exe -m pip install -e .[browser]`

## Ollama

Install Ollama from the official project site, then pull a local model:

```powershell
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull qwen2.5:7b
```

Default config points at:

- Host: `http://localhost:11434`
- Model: `llama3.1:8b`

You can change both in `config/settings.yaml` or by environment variable.

## Inputs

- Main profile: `data/profile_master.md`
- Optional additional resume files: Markdown or text
- Optional preferences in `config/settings.yaml`
- Optional manual job imports: JSON or CSV files

## Commands

After installation, either use `python -m job_searcher ...` or the `job-searcher` entrypoint.

### Ingest profile

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher ingest-profile --input data/profile_master.md
```

### Generate search queries

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher generate-queries
```

### Search jobs

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher search-jobs
```

### Rank jobs

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher rank-jobs
```

### Build reports

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher report
```

### Run the whole pipeline

```powershell
C:\Users\afaqs\anaconda3\python.exe -m job_searcher run-all --input data/profile_master.md
```

## Outputs

The pipeline writes:

- `outputs/profile_document.json`
- `outputs/profile_structured.json`
- `outputs/search_queries.json`
- `outputs/discovered_jobs.json`
- `outputs/jobs_ranked.json`
- `outputs/jobs_ranked.csv`
- `outputs/top_matches.md`
- `outputs/search_report.md`

Each ranked result includes:

- Overall score
- Interpretable subscores
- Why it matches
- Missing skills
- Resume emphasis angle
- Cover-letter angle
- `apply`, `maybe`, or `skip` label

## Supported job sources

- Greenhouse board API
- Lever postings API
- RSS feeds
- Static company pages with configurable selectors
- Manual imports from local JSON and CSV

The connectors are pluggable and can be extended without touching the ranking pipeline.

## Limitations

- Source coverage depends on configured boards, feeds, and manual inputs.
- Generic static-page parsing is best-effort and may need page-specific selectors.
- Ollama reasoning degrades gracefully when a local model is unavailable, but explanations become heuristic.
- Embedding similarity is optional and requires a local sentence-transformers install.
- v1 does not auto-submit applications.

## Testing

```powershell
C:\Users\afaqs\anaconda3\python.exe -m pytest
```

## Extension ideas

- Streamlit review UI
- More source connectors and company-board discovery helpers
- Duplicate job clustering across sources
- Email digests
- Tailored resume bullet exports
- Human-in-the-loop application material drafting
