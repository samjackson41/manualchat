# Progress

## What works

- Backend: FastAPI with `/health`, `/models`, and `/chat`. The chat reply goes
  through the LangGraph graph.
- Tool calling: the graph runs a `chat -> tools -> chat` loop. The `calculator`
  and three RAG tools (`search_manual`, `extract_specs`, `get_page_text`) are in
  `backend/tools.py`. The RAG tools are stubs that return sample data. Real
  retrieval is left (IMPLEMENTATION Task 4).
- Frontend: Next.js chat built on assistant-ui. The styled Thread shows
  messages, markdown, streaming, and regeneration. A LocalRuntime adapter in
  `frontend/app/chat-runtime.tsx` calls `POST /chat`. The model selector is a
  shadcn Select. Tailwind is v4.
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

- The RAG pipeline, in phases: dependencies and configuration, storage and
  `POST /manuals`, the ingest stages, chunk and index in Qdrant, then real
  retrieval behind the tools. The ratified values are in `DECISIONS.md`
  (D9 to D15, R3 to R10, A1 to A5, T1 to T3).
- The Supervisor and Synthesizer graph (DECISIONS A1). The graph is a flat
  `chat ↔ tools` loop today.
- The system prompt in `backend/agent/graph.py`.
- Real retrieval behind `search_manual`, `extract_specs`, and `get_page_text`.
  The contracts and stub bodies are in place (IMPLEMENTATION.md Task 4).
- Memory: the summary field, the compaction node, and a checkpointer per
  `MEMORY_DESIGN.md`.
- The scanned-manual OCR path. Deferred past MVP per DECISIONS S1.
- CI linting, formatting, and tests. The current CI checks syntax, types, and the
  build only.

## Known problems

- DeepSeek `-latest` slugs need the `~` prefix, or OpenRouter returns 400. This
  is recorded in the `README.md` "Deviations" section and in `DECISIONS.md`.

## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.