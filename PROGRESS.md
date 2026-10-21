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

- Manual management: `PATCH /manuals/{id}` enables or disables a manual, and
  `DELETE /manuals/{id}` removes it. A delete is permanent. Search skips the
  chunks of a disabled manual. The vehicle dialog shows each manual's
  description, status, page count, and chunk count, with an enable switch and a
  two-step delete.

- Agent tools: the agent runs a `chat -> tools -> chat` loop. The tools are a
  calculator, `search_manual`, `extract_specs`, and `get_page_text`.
  `search_manual` returns reranked chunks with page citations, `get_page_text`
  returns the full text of a page, and `extract_specs` returns the matching rows
  from the manual's tables.

- Grounding: the agent answers only from the manual. Every claim and step
  carries a `[Page N]` citation. When the manual holds no answer, the agent says
  so. When the manual gives conflicting values, the agent shows each one with
  its own citation.

- Streaming: `POST /chat/stream` sends the answer as Server-Sent Events, one
  token at a time, then a final done event.

- Page thumbnails: `GET /manuals/{id}/thumbnails/{page}` renders one page of the
  stored PDF as a PNG.

- Frontend chat: a Next.js chat built on assistant-ui. It shows messages and
  markdown, and regenerates a reply. A sidebar keeps the chat history in the
  browser across reloads.

- Vehicle and upload dialogs: a vehicle selector feeds a manual-upload button
  and a manual-viewer toggle. The selector can add a vehicle, and rename and
  delete sit behind a pencil icon. The upload dialog takes an optional
  description and its own vehicle picker. It lists the chosen vehicle's manuals
  with their ingest status, and a guard stops a quick double click from starting
  an ingest twice.

- Manual viewer: each `[Page N]` in a reply is a clickable badge. Clicking one
  opens the viewer beside the chat at the cited page, with selectable text and
  zoom.

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
  `instructions/`, and `skills/`. `.github/workflows/ci.yml` and
  `.github/PULL_REQUEST_TEMPLATE.md` stay tracked in this repo.

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
- Make the threads sidebar collapsible with a small button that shows a double
  right chevron icon to expand it.

## Known problems

- The chat shows the whole answer in one flash. The frontend does not render the
  token stream one chunk at a time, so the answer does not form smoothly.


## Decisions

`DECISIONS.md` holds the ratified decisions. Keep it current.
