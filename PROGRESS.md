# Progress

## What works

- Backend: FastAPI serves `/health`, `/models`, and `/chat`. A chat reply runs
  through the LangGraph agent.

- Manual upload: `POST /manuals` stores an uploaded PDF and a record of it.
  `GET /manuals` and `GET /manuals/{id}` read them back. An upload whose content
  matches an existing manual of the same vehicle is refused.

- Ingest: an upload converts the PDF in the background and marks the manual
  `processing`. When the conversion finishes, the manual is `ready`. While it
  works, the upload dialog shows a progress bar and a time estimate.

- Retrieval: a ready manual is chunked and indexed into a local Qdrant
  collection, which needs no server or credentials. A search reranks its results
  and returns a score from 0 to 1.

- Vehicle profiles: `GET/POST /vehicles` and `PATCH/DELETE /vehicles/{id}`
  create, rename, and delete vehicles. A chat can be scoped to one vehicle.

- Manual management: `PATCH /manuals/{id}` enables, disables, or renames a
  manual, and `DELETE /manuals/{id}` removes it. A delete is permanent. Search
  skips the chunks of a disabled manual. The vehicle dialog shows each manual's
  description, status, page count, and chunk count, with an enable switch, a
  rename behind a pencil icon on the title, and a two-step delete.

- Agent graph: the agent runs a supervisor, worker, and synthesize topology.
  The supervisor decides whether the worker keeps searching the manual or the
  graph writes the answer. The worker runs the tool loop over a calculator,
  `search_manual`, `extract_specs`, and `get_page_text`. `search_manual`
  returns reranked chunks with page citations, `get_page_text` returns the full
  text of a page, and `extract_specs` returns the matching rows from the
  manual's tables.

- Grounding: the agent answers only from the manual. Every claim and step
  carries a `[Page N] (manual <manual_id>)` citation, so a click opens the right
  manual. When the manual holds no answer, the agent says so. When the manual
  gives conflicting values, the agent shows each one with its own citation.

- Streaming: `POST /chat/stream` sends the answer as Server-Sent Events. The
  worker emits a `tool_call` event before each tool runs and a `tool_result`
  event after, then the answer streams one token at a time and a final done
  event ends the stream.

- Page thumbnails: `GET /manuals/{id}/thumbnails/{page}` renders one page of the
  stored PDF as a PNG.

- Automated evals: `backend/eval/` scores a 16-question set with an LLM judge.
  On the 56-page `pl.pdf` the run passed 16/16, with citation precision 0.95 to
  1.00 and no fabricated out-of-scope answers.

- Frontend chat: a Next.js chat built on assistant-ui. It shows messages and
  markdown, and regenerates a reply. The answer forms token by token as the
  stream arrives, and each agent tool call shows its name, arguments, and
  result while it runs. A sidebar keeps the chat history in the browser across
  reloads. History is scoped per vehicle: each vehicle keeps its own threads,
  and the sidebar shows a "<Vehicle Name> Chat History" header.

- Vehicle and upload dialogs: a vehicle selector feeds a manual-upload button
  and a manual-viewer toggle. The selector can add a vehicle, and rename and
  delete sit behind a pencil icon. The manage vehicle dialog is 32rem wide.
  A long manual name truncates and a long ID wraps, so each button stays
  inside the dialog. The upload dialog has its own vehicle picker. It lists the
  chosen vehicle's manuals and their ingest status. A guard stops a quick double
  click from starting an ingest twice. Closing the dialog during an ingest keeps
  the run in view:
  the Upload manual button reopens the progress panel, and a toast below the top
  bar does the same.

- Manual viewer: each `[Page N]` in a reply is a clickable badge. Clicking one
  opens the viewer beside the chat at the cited page in the manual the citation
  names, with selectable text and zoom. The manual selector opens a wide
  dropdown that shows a long name, and dragging the pane right past its minimum
  snaps it closed.

- Whole-manual view: a `View whole manual` button in the viewer opens the
  manual's stored PDF. Pages mount one at a time as the reader scrolls, so a
  large manual stays responsive.

- Viewer caching: the viewer caches the PDF bytes it has downloaded. The page
  endpoints answer with an `ETag`, so a matching request returns `304`.

- Themes: a light and dark theme toggle sits in the top bar. On first visit the
  theme follows the operating system, then the stored choice wins.

- Docker Compose: runs the backend and the frontend in two terminals. Uploads,
  vehicle profiles, and the search index persist on the host.

- Manual commands: `python -m backend.ingest <manual_id>` reruns the ingest
  pipeline by hand, and `python -m backend.retrieval <manual_id>` indexes a
  manual and prints the ranked chunks for a query.

- Git workflow: Conventional Commits, feature branches, squash merges.

- Repo hygiene: the spike experiments live outside this repo at
  `/home/sam/dev/spikes/fj40ocr`, and `/spike/` is git-ignored.
  `SPIKE_FINDINGS.md` stays tracked.

- Dev coding assistant: VS Code Copilot Chat with OpenRouter models (the
  OpenRouter Maestro extension, model `deepseek/deepseek-v4-pro-0813`). Repo
  rules live in `AGENTS.md`. The other agent files live in the workspace
  `.github/` folder one level above this repo: `copilot-instructions.md`,
  `instructions/`, and `skills/` with the `simple-english` and `open-pr`
  skills. The `open-pr` skill opens one PR per branch with the `gh` CLI. The
  workspace agent files are local only.
  `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` stay
  tracked in this repo.
- Monitoring (MVP+1): LangSmith traces every OpenRouter model call
  (`backend/tracing.py`, wired into `backend/llm.py`). One `llm` run per call
  records the model slug, the token usage, the wall-clock latency, and any
  error. Tracing is off until `LANGSMITH_TRACING=true` and
  `LANGSMITH_API_KEY` are both set; a failed post is swallowed, so an
  unreachable LangSmith never breaks the chat (DECISIONS O1).

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

- Stream the progress of the agent in the chat. Show the RAG model weight
  loading the way the terminal shows them, so the reader sees ingest progress
  instead of a loading spinner. Tool calls are shown; this item remains for
  the RAG model weight loading.
- Let the reader rename a chat session in the frontend.
- Add tooltips to the edit, theme, and manual upload buttons.
- Make the threads sidebar collapsible with a small button that shows a
  double right chevron icon to expand it.

## Known problems

- DeepSeek `-latest` slugs need the `~` prefix, or OpenRouter returns 400.
  This is recorded in the `README.md` "Deviations" section and in
  `DECISIONS.md`.

## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.
