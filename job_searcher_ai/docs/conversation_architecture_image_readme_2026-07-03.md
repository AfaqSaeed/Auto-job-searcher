# Architecture Image README Update

- Saved at: 2026-07-03

## Request
Add the generated architecture diagram at `job_searcher_ai\docs\assets\explainable_talent_matching_architecture.png` to the repository and update `job_searcher_ai\README.md` with a new section near the top before Features.

## Change
Added an Architecture section to `job_searcher_ai\README.md` that embeds `docs\assets\explainable_talent_matching_architecture.png` and briefly explains the pipeline separation.

## Validation
Checked that the referenced PNG exists locally before editing. The existing `scripts\save_conversation.py` archive helper was attempted first, but Python raised `PermissionError` while writing the new markdown file, so this note was saved directly.
