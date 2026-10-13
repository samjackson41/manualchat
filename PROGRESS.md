# Progress

## What works

- Backend: FastAPI with `/health`, `/models`, and `/chat`. The chat reply goes
  through the LangGraph graph.
- Tool calling: the graph runs a `chat -> tools -> chat` loop. One tool, a
  `calculator` in `backend/tools.py`, proves the loop end to end. RAG tools land
  there next (IMPLEMENTATION Task 4).
- Frontend: Next.js chat box with a model selector.
- Docker Compose runs the backend and the frontend in two terminals.
- Git workflow: Conventional Commits, feature branches, squash merges.
- Repo hygiene: the spike experiments moved out of the repo to
  `/home/sam/dev/spikes/fj40ocr`, and `/spike/` is now git-ignored.
  `SPIKE_FINDINGS.md` stays tracked.
- The dev coding assistant is VS Code Copilot Chat with OpenRouter models
  (the OpenRouter Maestro extension, model `deepseek/deepseek-v4-pro-0813`).
  Repo rules live in `AGENTS.md`. The other agent files live in the workspace
  `.github/` folder one level above this repo: `copilot-instructions.md`,
  `instructions/`, and `skills/` with the `simple-english` and `open-pr`
  skills. The `open-pr` skill opens one PR per branch with the `gh` CLI. The
  workspace agent files are local only.
  `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` stay tracked
  in this repo.

## What is left

- The system prompt in `backend/agent/graph.py`.
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