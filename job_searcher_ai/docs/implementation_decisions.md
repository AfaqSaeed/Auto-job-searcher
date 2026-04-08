# Implementation Decisions

## Scope and safety

- The repository is command-line first. That keeps the v1 workflow inspectable and easy to automate later.
- v1 does not auto-apply. The system stops at reviewable ranking outputs.
- Source connectors only target public endpoints, RSS, static pages, and manual imports. There is no login automation, anti-bot bypass, or CAPTCHA handling.

## Architecture

- The package uses a `src/job_searcher` layout so installation and imports behave cleanly.
- Pydantic models define the shared contracts for profile, queries, jobs, scores, and reports.
- The pipeline is split into profile, queries, sources, parsing, ranking, reporting, and llm modules so each stage can be extended without rewriting the rest.
- Intermediate artifacts are persisted as JSON in `outputs` to make debugging and review straightforward.

## Local AI choices

- Ollama is the default LLM backend because it satisfies the local-first requirement and does not require a paid API.
- LLM usage is constrained to summarization and qualitative reasoning. Deterministic extraction and normalization stay rule-based.
- Embeddings are optional. The code supports sentence-transformers when installed and falls back to lexical similarity when it is not.

## Discovery choices

- Greenhouse and Lever connectors use public board endpoints because they are more stable and structured than scraping rendered pages.
- Static company pages remain configurable because HTML varies heavily by site.
- Manual imports are included in v1 so the pipeline remains useful even when network access is unavailable or a source lacks a good public interface.

## Ranking choices

- The scoring model is intentionally interpretable: title, skills, domain, seniority, location, constraints, sector bonus, and mismatch penalty are all surfaced.
- Adjacent title families are treated as related. This is important for applied AI, perception, 3D vision, SLAM, and multimodal roles that often use different titles for similar work.
- The final score fuses symbolic scoring, optional embeddings, and local-LLM fit labels rather than delegating the whole decision to the LLM.

## Conversation archive helper

- The repo instructions asked for saving the conversation to Markdown after code changes.
- Codex sessions do not expose a raw transcript file directly inside the workspace, so the helper script writes a Markdown archive from provided text input or a content file.
- For this change, the conversation summary log is saved under `docs/conversations/` using that helper.
