# AGENTS.md

## Repository Defaults

- Use `C:\Users\afaqs\anaconda3\python.exe` for Python commands unless the user explicitly requests a different interpreter.
- After each requested code change, create a local git commit unless the user says not to.
- Do not push commits to any remote unless the user explicitly asks.
- Use plain Windows file paths in responses rather than clickable markdown file links.
- Prefer concise, direct communication.
- Save all the conversation into a markdown file at the end of each code change maybe create a seperate script for this and run it before start commiting changes

## Git Safety

- Commit only the files relevant to the requested change.
- Do not include unrelated user changes in a commit.
- Do not amend existing commits unless the user explicitly asks.
- Do not use destructive git commands such as `git reset --hard` unless the user explicitly asks.

## Validation

- Run relevant tests or checks before committing when practical.
- If something cannot be validated, state that clearly in the final response.
