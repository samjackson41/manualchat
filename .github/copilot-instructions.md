---
applyTo: "**"
---

# ManualChat — repository instructions for Copilot

This repository is a grounded repair-manual assistant: a FastAPI and LangGraph
backend, a Next.js frontend, and OpenRouter models.

Read the full task checklist and engineering conventions in `AGENTS.md` at the
repository root. The rules that always apply:

- Every tunable value lives in config (`DECISIONS.md` P1). Never hardcode it.
- Never commit or print a secret, key, token, or `.env` file.
- Read `README.md`, `DECISIONS.md`, and `PROGRESS.md` before proposing changes.
- Write docs and pull-request descriptions in plain English per the
  `simple-english` skill in `.github/skills/`.
- Use Conventional Commit messages; make one small change at a time.
- When a change touches `backend/` or `frontend/`, run the checks named in the
  matching `.github/instructions/*.instructions.md` file and report their output.