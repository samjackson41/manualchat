# Progress

## What works

- Backend: FastAPI with `/health`, `/models`, and `/chat`. The chat reply goes
  through the LangGraph graph.
- Frontend: Next.js chat box with a model selector.
- Docker Compose runs the backend and the frontend in two terminals.
- Git workflow: Conventional Commits, feature branches, squash merges.
- The dev coding assistant is VS Code Copilot Chat with OpenRouter models
  (the OpenRouter Maestro extension, model `deepseek/deepseek-v4-pro-0813`).
  Repo rules live in `AGENTS.md`, `.github/instructions/`, and
  `.github/copilot-instructions.md`; skills live in `.github/skills/`
  (`simple-english` and `open-pr`). Cline was retired on 2026-10-12 after a
  working validation run. The `open-pr` skill opens one PR per branch with the
  `gh` CLI and replaced `pr-description` on 2026-10-12. It was tested on PR #2
  for branch `chore/copilot-migration`.

## What is left

- The system prompt in `backend/agent/graph.py`.
- Tool calling (the `chat -> tool -> chat` loop).
- RAG tools (`search_manual`, `extract_specs`, `get_page_text`) per
  `IMPLEMENTATION.md` Task 4.
- Memory: the summary field, the compaction node, and a checkpointer per
  `MEMORY_DESIGN.md`.
- The scanned-manual OCR path. Deferred past MVP per DECISIONS S1.
- CI linting, formatting, and tests. The current CI checks syntax, types, and the
  build only.

## Known problems

- DeepSeek `-latest` slugs need the `~` prefix, or OpenRouter returns 400. This
  is recorded in the `README.md` "Deviations" section.
- `DECISIONS.md` pins the model slugs without the `~` prefix. The code and the
  README correct that. Fix the decision log when it is next edited.

## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.