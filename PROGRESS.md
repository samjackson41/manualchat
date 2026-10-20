# Progress

## What works

- Backend: FastAPI with `/health`, `/models`, `/chat`, and `/chat/stream`. The
  chat reply goes through the LangGraph graph.
- Manual storage: `POST /manuals` stores an uploaded PDF under
  `manuals/{manual_id}/`. The directory is a server-generated UUID dir with
  `source.pdf` and a `manual.json` record. `GET /manuals` and
  `GET /manuals/{id}` read it back (DECISIONS U1). The env `MANUALS_DIR` sets
  the directory. Docker bind-mounts it as `/data/manuals`.
- Ingest: uploading a manual sets `status` to `processing` and runs the Docling
  pipeline in the background (IMPLEMENTATION Task 1). The pipeline probes the
  text layer and refuses a manual with no text (DECISIONS D1). It strips the
  hidden OCR font (D2). It converts with `do_ocr=False` and fast tables. It
  normalizes unit and header noise (D3). Then it writes `page_text/`,
  `tables.json`, and `ingest.json` under the manual directory and sets
  `status` to `ready` (or `error`). Once the pipeline reaches `ready`, the
  backend chunks and indexes the manual (`retrieval.index_manual`) and writes
  the `chunk_count` back. A fresh upload is searchable at once. The same
  pipeline runs by hand with `python -m backend.ingest <manual_id>`. The real
  run on `pl.pdf` produced 56 pages and 9 tables.
- Retrieval: `backend/retrieval.py` chunks an ingested manual and indexes it
  into a local Qdrant collection (IMPLEMENTATION Task 3). Chunking splits prose
  on section headings and keeps each table as one chunk. Prose chunks target
  512 tokens with 64 tokens of overlap. The `cl100k_base` tokenizer counts the
  tokens (DECISIONS D9-D11, D13). The chunks embed with
  `multi-qa-mpnet-base-dot-v1` and store in an embedded local Qdrant, which
  needs no server or credentials (R3-R6). Search reranks with
  `cross-encoder/ms-marco-MiniLM-L-6-v2` and returns a score from 0 to 1
  (R7-R9). `python -m backend.retrieval <manual_id>` indexes a manual. A query
  argument then searches the manual and prints the ranked chunks. Indexing the
  56-page `pl.pdf` produced 121 chunks.
- Vehicle profiles: `GET/POST /vehicles` and `PATCH/DELETE /vehicles/{id}`
  create, rename, and delete vehicles under `vehicles/{vehicle_id}/` (a
  server-generated UUID). The storage mirrors manual storage (SPECIFICATION
  §5). The env `VEHICLES_DIR` sets the directory, and Docker mounts it as
  `/data/vehicles`. `POST /chat` takes an optional `vehicle_id` that scopes
  the conversation to one vehicle (SPECIFICATION §6).
- Manual management: `PATCH /manuals/{id}` enables or disables a manual.
  `DELETE /manuals/{id}` removes it. A disabled manual keeps its stored files
  and index, but the search skips its chunks (DECISIONS U3). Deletion purges
  the chunks of the manual from Qdrant first, then removes the record and the
  directory. The delete is permanent (DECISIONS U4). The vehicle dialog in the
  frontend shows the vehicle details. It lists the manuals of the vehicle with
  their optional description, status, and page and chunk counts. Each manual
  gets enable/disable switches and a two-step delete. Chunk point ids derive
  from the manual id, so point ids stay unique across manuals indexed into one
  collection.
- Agent graph: the graph is a supervisor, worker, and synthesize topology
  (DECISIONS A1). The `supervisor` node reads the question and what the worker
  has found, and decides whether the worker keeps searching or the graph
  synthesizes. The `worker` node runs the tool loop. The `synthesize` node
  writes the final markdown answer with `[Page N]` citations. A hop cap
  (`AGENT_MAX_HOPS`, default 4) forces synthesis when the supervisor has not
  stopped; a second cap (`AGENT_MAX_TOOL_STEPS`, default 4) bounds the worker's
  tool loop. The model the user picked selects a tier (DECISIONS M1). Flash
  picks `fast`: the supervisor runs Flash at high reasoning effort, the worker
  runs Flash at low. Pro picks `pro`: the supervisor runs Pro at max reasoning
  effort, the worker runs Flash at high. The tier table is `SUPER_SUB_TIERS`
  (JSON), and the slug-to-tier map is `SUPER_SUB_SLUG_TIERS`.
- Tool calling: the `worker` node runs a tool loop. The
  `calculator` and three RAG tools (`search_manual`, `extract_specs`,
  `get_page_text`) are in `backend/tools.py`. The RAG tools use real retrieval
  (IMPLEMENTATION Task 4). `search_manual` calls `retrieval.search` and
  returns reranked chunks with page citations. `get_page_text` reads the full,
  unchunked text of each requested physical page from
  `page_text/page_NNNN.txt`. `extract_specs` reads the `tables.json` of the
  manual and matches the subject against table captions and row labels. It
  skips disabled manuals (DECISIONS U3). It returns the matched rows verbatim,
  an empty list when nothing matches. The `tools` node injects the
  `vehicle_id` of the conversation into every retrieval tool call. The
  injection overrides any value the model supplied, because the model cannot
  know it.
- POC deviation (deliberate): `extract_specs` reads `tables.json` directly
  instead of doing targeted table retrieval in Qdrant (DECISIONS L1). Reading
  the file keeps the values verbatim (never model prose, L2). The tool moves
  to the `is_table` search path when the spec ledger lands.
- System prompt: the graph prepends the grounding prompt before the first chat
  call. The prompt demands a `[Page N]` citation on every claim and step. It
  answers only from the manual, states plainly when the manual holds no
  answer, and shows both values when the manual conflicts. You tune the text
  through `AGENT_SYSTEM_PROMPT` (DECISIONS A3).
- Backend services (Task 5): `POST /chat/stream` streams the answer from the
  graph as SSE JSON chunks. A chunk is `{"type": "token"}`, and the last one
  is `{"type": "done"}`. The stream runs through `llm.stream_chat` and a
  `stream` state flag that sends the `synthesize` node through a streaming
  path; the supervisor and worker reasoning is internal and is not streamed.
  The plain `/chat` reply is unchanged.
  `GET /manuals/{id}/thumbnails/{page}` renders one physical page of the
  stored `source.pdf` to a PNG at `THUMBNAIL_DPI` (default 150) for the
  raster fallback of the viewer.
- Automated evals (Task 7): `backend/eval/` scores the 16-question set in
  `backend/tests/eval_questions.json` with an LLM judge (DECISIONS E1 to E6).
  `backend/eval/dataset.py` loads the set, `backend/eval/judge.py` scores one
  markdown answer against its category rubric, and `backend/eval/run.py` runs
  every case through the agent and reports the result. The rubric checks a
  spec value with its unit and qualifier, a procedure in substance and order,
  and an out-of-scope answer that must invent nothing. Citation precision is
  counted in code from the `[Page N]` markers, not by the judge. The judge
  model is distinct from the model under test (E1). The runner prints the
  pass rate overall and per category, the citation precision, and the
  fabricated count, and it gates on the pass rate, the citation precision,
  and a zero fabricated count. It is a live-LLM run, so it stays out of the
  default CI (T4). Run it from the repo root, against an ingested manual:
  `EVAL_VEHICLE_ID=<id> uv run --project backend python -m backend.eval.run`.
- Eval result on the 56-page `pl.pdf` (vehicle `demo_vehicle`): 16/16 passed
  (100%), citation precision 1.00, and 0 fabricated out-of-scope answers. The
  bar is more than 90% precision and 0% fabricated (Task 7).
- Tests: `backend/tests/` holds unit tests for the API, the configuration,
  ingest,
  retrieval, the slicer, the manual PDF endpoint, the thumbnails, the tools,
  the stream, and the eval. The tests inject fakes per DECISIONS T1, so the
  default run downloads no model.
- Frontend: Next.js chat built on assistant-ui. The styled Thread shows
  messages, markdown, streaming, and regeneration. A thread-list sidebar keeps
  chat history in localStorage across reloads. The chat adapter in
  `frontend/app/chat-runtime.tsx` calls `POST /chat` scoped to the active
  vehicle. A vehicle selector feeds a manual-upload button and a manual-viewer
  toggle. The selector dropdown ends with an Add vehicle entry. Rename and
  delete sit behind a pencil icon. The upload dialog takes an optional
  description. The dialog also holds a vehicle picker, with an Add vehicle
  entry, that aims the manual at a vehicle from the form. It lists the manuals
  of the chosen vehicle with their ingest status and polls `GET /manuals`
  until the ingest finishes. A typed client in `frontend/lib/api.ts` wraps
  every backend call. Tailwind is v4, themed in red, white, gray, black, and
  gold. A light/dark theme toggle sits in a top bar that also holds the
  selector, upload, viewer, and model controls. On first visit the theme
  follows the operating system. Then the stored choice wins (DECISIONS C1).
  The wrench-in-bubble logo replaces the ManualChat wordmark, and the manual
  viewer opens side by side with the chat instead of above it (DECISIONS C2).
- Manual viewer and citations (Task 6, DECISIONS V1-V4): each `[Page N]` in a
  reply renders as a clickable badge. Clicking one opens the viewer pane
  beside the chat. The pane shows the cited page plus one page before and two
  after. react-pdf renders the pages with selectable text. The pane opens at the cited
  page, so the page held before it scrolls out of view. While a slice shows,
  the pane hides the manual selector and names the slice in its place, in the
  form `Manual name, Pg. 15-19`. The selector returns when the reader closes
  the PDF. A floating X closes the PDF without closing the pane. The pane
  carries zoom controls. The reader sets the chat/pane split by dragging the
  left edge of the pane or with the arrow keys on it. Dragging past the
  minimum width of the chat hides the chat, so the pane fills the row beside
  the thread sidebar. A short pull back returns the chat. The slice loads from
  `GET /manuals/{id}/pages/{start}-{end}`, which cuts the pages on demand with
  PyMuPDF (`backend/slicer.py`).
- Whole-manual view (DECISIONS V2): a `View whole manual` button in the pane
  opens the stored PDF of the manual through `GET /manuals/{id}/pdf`, which
  streams the file. Pages mount one at a time as the reader scrolls, so a
  large manual stays responsive.
- Viewer byte caching (DECISIONS V5-V6): the pane caches PDF bytes, never
  rendered pages. Slices live in a module-level map with an LRU cap. A whole
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
  `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` stay
  tracked in this repo.

## What is left

- The RAG pipeline, in phases. The ingest stage (Task 1), chunking and
  indexing (Task 3), real retrieval behind the tools (Task 4), and the
  automated eval (Task 7) are done. The prototype runs against the 56-page
  `pl.pdf`. The graph runs the supervisor, worker, and synthesize topology,
  and the answer stays markdown text with `[Page N]` citations. The ratified
  values are in `DECISIONS.md` (D9 to D13, R3 to R9, A1 to A3, E1 to E6,
  T1 to T4).
- The chunk-size and overlap sweep: the eval scores one chunk configuration.
  A later run scores other sizes (DECISIONS D10) and overlaps (D11) and
  compares them.
- Future work (DECISIONS Deferred): the structured `AgentAnswer`, the
  spec ledger, the scanned-manual OCR path, and the Docker work.
- Memory: the summary field, the compaction node, and a checkpointer per
  `MEMORY_DESIGN.md`.
- The scanned-manual OCR path. Deferred past MVP per DECISIONS S1.
- CI linting, formatting, and tests. The current CI checks syntax, types, and
  the build only.

### Manual viewer backlog

Planned work for the Manual viewer pane. None of it is built.

- Add a note that the page count follows the PDF page index, not the printed
  page number on the sheet.
- MVP+1: add a page-number offset. The reader shifts the page numbers to
  repair an off-by-n error, so the numbers match the citations.
- MVP+1: make the pane reactive, so it works on a phone.

### Frontend backlog

Planned frontend work. None of it is built.

- Stream the progress of the agent in the chat. Show the tool calls and the RAG
  model weight loading the way the terminal shows them, so the reader sees
  progress instead of a loading spinner.
- Let the reader rename a chat session in the frontend.
- Add tooltips to the edit, theme, and manual upload buttons.
- Make the threads sidebar collapsible with a small button that shows a
  double right chevron icon to expand it.

## Known problems

- The chat shows the whole answer in one flash. The frontend does not render
  the token stream one chunk at a time, so the answer does not form smoothly.
- DeepSeek `-latest` slugs need the `~` prefix, or OpenRouter returns 400.
  This is recorded in the `README.md` "Deviations" section and in
  `DECISIONS.md`.

## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.
