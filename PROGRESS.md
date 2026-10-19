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
  `status` to `ready` (or `error`). On upload, once the pipeline reaches
  `ready` the manual is chunked and indexed (`retrieval.index_manual`) and the
  `chunk_count` is written back, so a fresh upload is searchable at once. The
  same pipeline runs by hand with `python -m backend.ingest <manual_id>`. The
  real run on `pl.pdf` produced 56 pages and 9 tables.
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
- Manual management: `PATCH /manuals/{id}` enables or disables a manual, and
  `DELETE /manuals/{id}` removes it. A disabled manual keeps its stored files
  and index, but the search skips its chunks (DECISIONS M1). Deletion purges
  the manual's chunks from Qdrant first, then removes the record and its
  directory; it is permanent (DECISIONS M2). The vehicle dialog in the
  frontend shows the vehicle's details, lists its manuals with their optional
  description, status,
  page and chunk counts, and offers enable/disable switches plus a two-step
  delete for each manual. Chunk point ids are derived from the manual id, so
  point ids stay unique across manuals indexed into one collection.
- Tool calling: the graph runs a `chat -> tools -> chat` loop. The `calculator`
  and three RAG tools (`search_manual`, `extract_specs`, `get_page_text`) are in
  `backend/tools.py`. The RAG tools now use real retrieval (IMPLEMENTATION
  Task 4). `search_manual` calls `retrieval.search` and returns reranked chunks
  with page citations. `get_page_text` reads the full, unchunked text of each
  requested physical page from `page_text/page_NNNN.txt`. `extract_specs` reads
  the manual's `tables.json`, matches the subject against table captions and
  row labels, skips disabled manuals (DECISIONS M1), and returns the matched
  rows verbatim (an empty list when nothing matches). The `tools` node injects
  the conversation's `vehicle_id` into every retrieval tool call, overriding
  any value the model supplied, because the model cannot know it.
- POC deviation (deliberate): `extract_specs` reads `tables.json` directly
  instead of doing targeted table retrieval in Qdrant (DECISIONS L1). Reading
  the file keeps values verbatim (never model prose, L2); it moves to the
  `is_table` search path when the spec ledger lands.
- System prompt: the graph prepends the grounding prompt before the first chat
  call. The prompt demands a `[Page N]` citation on every claim and step,
  answers only from the manual, states plainly when the manual holds no answer,
  and shows both values when the manual conflicts. The text is tunable via
  `AGENT_SYSTEM_PROMPT` (DECISIONS A3).
- Backend services (Task 5): `POST /chat/stream` streams the graph's answer as
  SSE JSON chunks — `{"type": "token"}` deltas then one final
  `{"type": "done"}` — through a new `llm.stream_chat` and a `stream` state flag
  that routes `chat_node` through a streaming path (the graph shape and the
  plain `/chat` reply are unchanged). `GET /manuals/{id}/thumbnails/{page}`
  renders one physical page of the stored `source.pdf` to a PNG at
  `THUMBNAIL_DPI` (default 150) for the viewer's raster fallback.
- Frontend: Next.js chat built on assistant-ui. The styled Thread shows
  messages, markdown, streaming, and regeneration. A thread-list sidebar keeps
  chat history in localStorage across reloads. The chat adapter in
  `frontend/app/chat-runtime.tsx` calls `POST /chat` scoped to the active
  vehicle. A vehicle selector feeds a manual-upload button and a manual-viewer
  toggle. The
  selector's dropdown ends with an Add vehicle entry; rename and delete sit
  behind a pencil icon. The upload dialog takes an optional description in
  place of the old manual kind, and its own vehicle picker (with an Add
  vehicle entry) aims the manual at a vehicle from the form. It lists the
  chosen vehicle's manuals with their ingest status and polls `GET /manuals`
  until the ingest finishes.
  A typed client in `frontend/lib/api.ts` wraps every backend call. Tailwind is
  v4, themed in red, white, gray, black, and gold. A light/dark theme toggle
  sits in a top bar that also holds the selector, upload, viewer, and model
  controls; on first visit the theme follows the operating system, then the
  stored choice wins (DECISIONS C1). The ManualChat wordmark is replaced by the
  wrench-in-bubble logo, and the manual viewer opens side by side with the chat
  instead of above it (DECISIONS C2).
- Manual viewer and citations (Task 6, DECISIONS V1-V4): each `[Page N]` in a
  reply renders as a clickable badge. Clicking one opens the viewer pane beside
  the chat and shows the cited page plus one page before and two after, with
  selectable text, rendered with react-pdf. While a slice shows, the pane hides
  the manual selector and names the slice in its place, in the form
  `Manual name, Pg. 15-19`; the selector returns when the reader closes the
  PDF. A floating X closes the PDF without closing the pane. The pane carries
  zoom controls, and the reader sets the chat/pane split by dragging the pane's
  left edge or with the arrow keys on it. The slice loads from
  `GET /manuals/{id}/pages/{start}-{end}`, which cuts the pages on demand with
  PyMuPDF (`backend/slicer.py`).
- Whole-manual view (DECISIONS V2): a `View whole manual` button in the pane
  opens the manual's stored PDF through `GET /manuals/{id}/pdf`, which streams
  the file. Pages mount one at a time as the reader scrolls, so a large manual
  stays responsive.
- Viewer byte caching (DECISIONS V5-V6): the pane caches PDF bytes, never
  rendered pages. Slices live in a module-level map with an LRU cap; a whole
  manual lives once per manual in the Cache API, and deleting a manual drops
  its bytes. Both endpoints answer with `Cache-Control: immutable` and an
  `ETag`, and a matching `If-None-Match` returns `304`.
- Docker Compose runs the backend and the frontend in two terminals. The
  backend bind-mounts `manuals/`, `vehicles/`, and `qdrant/` so uploads,
  profiles, and the embedded Qdrant index all persist on the host.
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

- The RAG pipeline, in phases. The ingest stage (Task 1), chunking and
  indexing (Task 3), and real retrieval behind the tools (Task 4) are done. The
  chunk eval is next. The prototype runs against the 56-page `pl.pdf`. The
  graph stays a flat `chat ↔ tools` loop and the answer stays markdown text with
  `[Page N]` citations. The ratified values are in `DECISIONS.md` (D9 to D13,
  R3 to R9, A1 to A3, T1 to T3).
- The chunk eval: about 15 questions with known answer pages from `pl.pdf`, to
  check recall and citation precision and confirm the chunk size and overlap.
- Future work (DECISIONS Deferred): the Supervisor and Synthesizer graph, the
  structured `AgentAnswer`, the spec ledger, the scanned-manual OCR path, and
  the Docker work.
- Memory: the summary field, the compaction node, and a checkpointer per
  `MEMORY_DESIGN.md`.
- The scanned-manual OCR path. Deferred past MVP per DECISIONS S1.
- CI linting, formatting, and tests. The current CI checks syntax, types, and the
  build only.

### Manual viewer backlog

Planned work for the Manual viewer pane. None of it is built.

- Cite the manual page that holds the answer. The answer must not name page 1 of
  the slice if slice buffer start != -0.
- Add a note that the page count follows the PDF page index, not the printed
  page number on the sheet.
- MVP+1: add a page-number offset. The reader shifts the page numbers to repair
  an off-by-n error, so that the numbers match the citations.
- MVP+1: make the pane reactive, so that it works on a phone.

### Frontend backlog

Planned frontend work. None of it is built.

- Stream the agent's progress in the chat. Show the tool calls and the RAG model
  weight loading the way the terminal shows them, so the reader sees progress
  instead of a loading spinner.
- Let the reader rename a chat session in the frontend.
- Add tooltips to the edit, theme, and manual upload buttons.

## Known problems

- The chat shows the whole answer in one flash. The frontend does not render the
  token stream one chunk at a time, so the answer does not form smoothly.
- DeepSeek `-latest` slugs need the `~` prefix, or OpenRouter returns 400. This
  is recorded in the `README.md` "Deviations" section and in `DECISIONS.md`.

## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.