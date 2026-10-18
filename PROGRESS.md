# Progress

## What works

- Backend: FastAPI with `/health`, `/models`, and `/chat`. The chat reply goes
  through the LangGraph graph.
- Manual storage: `POST /manuals` stores an uploaded PDF under
  `manuals/{manual_id}/` (a server-generated UUID dir with `source.pdf` and a
  `manual.json` record), and `GET /manuals` + `GET /manuals/{id}` read it back
  (DECISIONS U1). The directory is the `manuals_dir` config value (env
  `MANUALS_DIR`), bind-mounted into the Docker backend as `/data/manuals`.
- Ingest: uploading a manual sets `status` to `processing` and runs the Docling
  pipeline in the background (IMPLEMENTATION Task 1). The pipeline probes the
  text layer and refuses a manual with no text (DECISIONS D1), strips the
  hidden OCR font (D2), converts with `do_ocr=False` and fast tables,
  normalizes unit and header noise (D3), then writes `page_text/`,
  `tables.json`, and `ingest.json` under the manual's directory and sets
  `status` to `ready` (or `error`). The same pipeline runs by hand with
  `python -m backend.ingest <manual_id>`. The real run on `pl.pdf` produced 56
  pages and 9 tables.
- Retrieval: `backend/retrieval.py` chunks an ingested manual and indexes it
  into a local Qdrant collection (IMPLEMENTATION Task 3). Chunking splits prose
  on section headings and keeps each table as one chunk. Prose chunks target
  512 tokens with 64 tokens of overlap, counted with `cl100k_base` (DECISIONS
  D9-D11, D13). The chunks embed with `multi-qa-mpnet-base-dot-v1` and store in
  an embedded local Qdrant, which needs no server or credentials (R3-R6).
  Search reranks with `cross-encoder/ms-marco-MiniLM-L-6-v2` and returns a
  score from 0 to 1 (R7-R9). `python -m backend.retrieval <manual_id>` indexes
  a manual; adding a query searches it and prints the ranked chunks. Indexing
  the 56-page `pl.pdf` produced 121 chunks.
- Vehicle profiles: `GET/POST /vehicles` and `PATCH/DELETE /vehicles/{id}`
  create, rename, and delete vehicles under `vehicles/{vehicle_id}/` (a
  server-generated UUID), mirroring manual storage (SPECIFICATION §5). The
  directory is the `vehicles_dir` config value (env `VEHICLES_DIR`), mounted
  as `/data/vehicles`. `POST /chat` takes an optional `vehicle_id` that scopes
  the conversation to one vehicle (SPECIFICATION §6).
- Tool calling: the graph runs a `chat -> tools -> chat` loop. The `calculator`
  and three RAG tools (`search_manual`, `extract_specs`, `get_page_text`) are in
  `backend/tools.py`. The RAG tools are stubs that return sample data. Wiring
  them to the retrieval backend is left (IMPLEMENTATION Task 4).
- System prompt: the graph prepends the grounding prompt before the first chat
  call. The prompt demands a `[Page N]` citation on every claim and step,
  answers only from the manual, states plainly when the manual holds no answer,
  and shows both values when the manual conflicts. The text is tunable via
  `AGENT_SYSTEM_PROMPT` (DECISIONS A3).
- Frontend: Next.js chat built on assistant-ui. The styled Thread shows
  messages, markdown, streaming, and regeneration. A thread-list sidebar keeps
  chat history in localStorage across reloads. The chat adapter in
  `frontend/app/chat-runtime.tsx` calls `POST /chat` scoped to the active
  vehicle. A vehicle selector (create, rename, delete) feeds a manual-upload
  button and a manual-viewer toggle (a placeholder until the page-slice viewer
  lands, DECISIONS V1). The upload dialog lists the active vehicle's manuals
  with their ingest status and polls `GET /manuals` until the ingest finishes.
  A typed client in `frontend/lib/api.ts` wraps every backend call. Tailwind is
  v4, themed in red, white, gray, black, and gold.
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

- The RAG pipeline, in phases. The ingest stage (Task 1) and chunking and
  indexing (Task 3) are done. Real retrieval behind the tools (Task 4) and the
  chunk eval are next. The prototype runs against the 56-page `pl.pdf`. The
  graph stays a flat `chat ↔ tools` loop and the answer stays markdown text with
  `[Page N]` citations. The ratified values are in `DECISIONS.md` (D9 to D13,
  R3 to R9, A1 to A3, T1 to T3).
- The chunk eval: about 15 questions with known answer pages from `pl.pdf`, to
  check recall and citation precision and confirm the chunk size and overlap.
- Future work (DECISIONS Deferred): the Supervisor and Synthesizer graph, the
  structured `AgentAnswer`, the spec ledger, the PDF viewer with citation
  badges, the scanned-manual OCR path, and the Docker work.
- Real retrieval behind `search_manual`, `extract_specs`, and `get_page_text`.
  The `backend/retrieval.py` backend is in place (Task 3); the tool stubs still
  return sample data, and Task 4 wires them to it.
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