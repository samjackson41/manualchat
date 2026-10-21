# ManualChat

ManualChat is a grounded repair-manual assistant. A grounded answer comes from
the manual text itself, and every claim carries a page citation. You add a
vehicle, upload its PDF manual, and ask questions in the chat. A citation
badge opens the manual at the cited page in a viewer beside the chat.

The backend is FastAPI with a LangGraph graph. The frontend is Next.js 14 with
assistant-ui and react-pdf. The models come from OpenRouter. Docling turns an
uploaded PDF into page text and tables during ingest. A chunk is a piece of
manual text sized in tokens. Qdrant stores the chunk index and runs in local
mode, which means a directory on disk with no server.

## Layout

```
manualchat/
  backend/
    config.py        # env-only configuration through pydantic-settings
    llm.py           # the OpenRouter wrapper (chat, stream_chat, tool calls)
    tracing.py       # LangSmith runs per model call: tokens, latency, errors
    ingest.py        # Docling ingest: page text, tables, and the ingest record
    retrieval.py     # chunking, embedding, and search over the Qdrant index
    thumbnails.py    # PNG page thumbnails for the viewer raster fallback
    tools.py         # agent tools: calculator, search_manual, extract_specs,
                     # get_page_text
    agent/graph.py   # LangGraph StateGraph: chat to tools and back to chat
    api/main.py      # routes: /health, /models, /chat, /chat/stream,
                     # /manuals, /vehicles, page slices, whole manual,
                     # thumbnails
    storage.py       # local manual and vehicle storage (DECISIONS U1)
    slicer.py        # on-demand PDF page slices with PyMuPDF
    schemas.py       # the shared Pydantic contracts
    tests/           # unit tests and the eval question set
    pyproject.toml   # the uv project (deps only, no package)
    uv.lock          # the generated lockfile
    Dockerfile
  frontend/          # Next.js 14 App Router, Tailwind v4, shadcn/ui,
                     # assistant-ui, react-pdf
    app/page.tsx     # top bar, thread-list sidebar, chat, and side viewer
    app/chat-runtime.tsx  # the chat runtime and the local thread storage
    app/vehicle-runtime.tsx  # the vehicle list and selection
    app/viewer-runtime.tsx  # viewer state: open, cited page, pane width
    app/theme-runtime.tsx  # light and dark theme state
    app/layout.tsx   # the provider stack and the pre-paint theme script
    app/globals.css  # the Tailwind v4 theme, light and dark
    lib/api.ts       # the typed client for the backend routes
    lib/viewer-config.ts  # viewer tunables, each from a NEXT_PUBLIC_ env var
    lib/pdf-cache.ts # the viewer byte caches: slice map and whole manual
    lib/theme.ts     # the theme key, the stored choice, and the pre-paint script
    assets/          # the logo (manualchat-logo.svg)
    components/      # assistant-ui elements, shadcn/ui primitives, and the
                     # garage UI
    Dockerfile
  docker-compose.yml # two services: backend and frontend, one terminal each
  Makefile           # shared targets: backend, frontend, status, build, down
  README.md          # this file: run steps, API output, and the config tables
  AGENTS.md          # the rules for the coding agent
  CONTRIBUTING.md    # branch, commit, and pull-request conventions
  project_proposal.md     # the capstone proposal
  project_brainstorming.md # the running idea and open-question notes
  SPECIFICATION.md   # the feature specification
  IMPLEMENTATION.md  # the phased implementation plan
  DECISIONS.md       # the ratified decision log
  PROGRESS.md        # what works, what is left, and known problems
  MEMORY_DESIGN.md   # the memory design for later phases
  SCANNED_OCR_RUNBOOK.md # the OCR recipe for scanned manuals (MVP+1, S1)
  SPIKE_FINDINGS.md  # the findings from the FJ40 OCR spike
```

## Run it

Docker Compose runs one service per terminal. Start the backend first.

Terminal 1: the backend (FastAPI on :8000, hot reload).

```bash
OPENROUTER_API_KEY=sk-or-... docker compose up backend
```

Terminal 2: the frontend (Next.js on :3000, hot reload).

```bash
docker compose up frontend
```

Open <http://localhost:3000>. Add a vehicle. Upload its manual. Wait for the
ingest status `ready`. Pick a model in the dropdown. Ask a question.

The Makefile wraps the same commands: `make backend`, `make frontend`, and
`make status`. The API key still comes from the shell environment.

Do not run `docker compose up` without a service name. Do not add `-d`. The
services are meant to run in two visible terminals.

### Good output

Terminal 1 prints `Uvicorn running on http://0.0.0.0:8000`. This command
returns `{"status":"ok"}`:

```bash
curl http://localhost:8000/health
```

Terminal 2 prints `Ready in …` and `Local: http://localhost:3000`.

This command lists the models:

```bash
curl http://localhost:8000/models
```

```json
{"default": "~deepseek/deepseek-flash-latest",
 "options": [{"id": "~deepseek/deepseek-flash-latest", "label": "DeepSeek Flash"},
             {"id": "~deepseek/deepseek-pro-latest", "label": "DeepSeek Pro"}]}
```

## Secrets

`OPENROUTER_API_KEY` and `LANGSMITH_API_KEY` are the only secrets.
`docker-compose.yml` passes them through from the host shell. They never enter
the repository. `LANGSMITH_API_KEY` is optional: it turns on LangSmith tracing
only while `LANGSMITH_TRACING` is also set (see Configuration). If
`OPENROUTER_API_KEY` is missing, `POST /chat` fails fast with a clear error,
while `/health` and `/models` still respond.

Never print a key, and never commit one.

## Configuration

Every tunable value lives in config (DECISIONS P1). The backend reads
environment variables through pydantic-settings, and the frontend reads
`NEXT_PUBLIC_` environment variables. There is no `.env` file in the repo
(see Deviation 1).

### Backend

Generation parameters are under research and surface as `MODEL_*` env vars,
so they can change without code edits. Unset values are omitted from the
OpenRouter request entirely.

| Variable | Default | Notes |
|---|---|---|
| OPENROUTER_API_KEY | _(empty)_ | Required for `POST /chat`. The empty default keeps `/health` and `/models` working without it. Never commit it. |
| OPENROUTER_BASE_URL | `https://openrouter.ai/api/v1` | The OpenRouter API base URL. `backend/llm.py` appends the chat endpoint. |
| MODEL_DEFAULT | `~deepseek/deepseek-flash-latest` | DECISIONS M1. The model used when the request names none. |
| MODEL_OPTIONS | `~deepseek/deepseek-flash-latest,~deepseek/deepseek-pro-latest` | DECISIONS M2. Comma-separated slugs. `_MODEL_LABELS` in `backend/config.py` holds the dropdown labels. |
| MODEL_REASONING_EFFORT | `medium` | The fallback reasoning effort when a node passes none. The tier sets the per-node effort (DECISIONS M1). |
| MODEL_TEMPERATURE | _(unset)_ | Pending decision. Omit the variable to use the provider default. |
| MODEL_MAX_TOKENS | _(unset)_ | Pending decision. Omit the variable to use the provider default. |
| SUPER_SUB_TIERS | the tier table in `backend/config.py` | DECISIONS M1. JSON. Each tier names the supervisor and worker model and their reasoning effort. |
| SUPER_SUB_SLUG_TIERS | `~deepseek/deepseek-flash-latest`→`fast`, `~deepseek/deepseek-pro-latest`→`pro` | DECISIONS M1. JSON. Maps a selected model slug to a tier. |
| SUPER_SUB_DEFAULT_TIER | `fast` | DECISIONS M1. The tier used when the selected slug matches no entry. |
| AGENT_MAX_HOPS | `4` | DECISIONS A1. The supervisor forces synthesis after this many worker hops. |
| AGENT_MAX_TOOL_STEPS | `4` | DECISIONS A1. The cap on the worker's tool loop. |
| AGENT_SYSTEM_PROMPT | the grounding prompt in `backend/config.py` | DECISIONS A3. The grounding rules for the agent. |
| MANUALS_DIR | `manuals` | DECISIONS U1. One `{manual_id}/` subdirectory per manual, with the PDF and its JSON record. In Docker: `/data/manuals`. |
| VEHICLES_DIR | `vehicles` | One `{vehicle_id}/` subdirectory per vehicle profile. In Docker: `/data/vehicles`. |
| THUMBNAIL_DPI | `150` | The PNG page preview resolution in dots per inch (IMPLEMENTATION Task 5). |
| VIEWER_CACHE_MAX_AGE_SECONDS | `31536000` | DECISIONS V5. A manual never changes after upload, so the browser can cache the page bytes this long. |
| INGEST_DO_OCR | `false` | False for MVP, because every manual is born-digital (DECISIONS S2). |
| INGEST_OCR_MIN_CHARS_PER_PAGE | `50` | DECISIONS D1. A manual needs OCR when its average text per page falls below this count. |
| INGEST_STRIP_HIDDEN_OCR_LAYER | `true` | DECISIONS D2. Removes an invisible OCR font layer before Docling reads the PDF. |
| INGEST_NORMALIZATION_ENABLED | `true` | DECISIONS D3. Runs the unit and header repair stage after Docling. |
| INGEST_USE_PRINTED_PAGE_NUMBERS | `false` | DECISIONS D12. Citations carry the physical PDF page number. |
| INGEST_DO_TABLE_STRUCTURE | `true` | Docling reconstructs table structure. |
| INGEST_TABLE_MODE | `FAST` | The Docling table mode. `FAST` keeps peak memory low. |
| INGEST_THREADS | `2` | The Docling thread count. |
| INGEST_BATCH_SIZE | `1` | The Docling batch size. |
| INGEST_CHUNK_STRUCTURE_AWARE | `true` | DECISIONS D9. Splits prose on section headings and keeps each table as one chunk. |
| INGEST_CHUNK_TOKENS | `512` | DECISIONS D10. The prose chunk target in tokens. |
| INGEST_CHUNK_OVERLAP_TOKENS | `64` | DECISIONS D11. Tokens shared between neighboring chunks. |
| INGEST_TOKENIZER | `cl100k_base` | DECISIONS D13. The tiktoken token counter. |
| QDRANT_URL | _(empty)_ | DECISIONS R3. Empty means local mode: Qdrant stores under `QDRANT_PATH` with no server, network, or credentials. An http(s) URL switches to a remote server. |
| QDRANT_PATH | `qdrant` | The local-mode directory, relative to the repo. |
| QDRANT_COLLECTION | `manualchat_chunks` | DECISIONS R4. The collection name. |
| QDRANT_API_KEY | _(empty)_ | DECISIONS R5. Empty in development. Production supplies it through the environment. |
| RETRIEVAL_EMBED_MODEL | `multi-qa-mpnet-base-dot-v1` | DECISIONS R6. The embedding model. |
| RETRIEVAL_RERANK_MODEL | `cross-encoder/ms-marco-MiniLM-L-6-v2` | DECISIONS R7. The reranker. |
| RETRIEVAL_CANDIDATE_K | `50` | DECISIONS R8. Chunks fetched before the rerank. |
| RETRIEVAL_TOP_N | `5` | DECISIONS R9. Chunks returned to the agent. |
| LANGSMITH_TRACING | `false` | DECISIONS O1. Set `true` with `LANGSMITH_API_KEY` to record one LangSmith `llm` run per OpenRouter call. |
| LANGSMITH_API_KEY | _(empty)_ | DECISIONS O1. The LangSmith API key. A secret; never commit it. |
| LANGSMITH_PROJECT | `manualchat` | DECISIONS O1. The LangSmith project that receives the runs. |
| LANGSMITH_ENDPOINT | `https://api.smith.langchain.com` | DECISIONS O1. The LangSmith API endpoint. |

### Frontend

Next.js inlines `NEXT_PUBLIC_` env vars at build time, or when the dev server
starts. Restart the frontend after a change to these variables.

| Variable | Default | Notes |
|---|---|---|
| NEXT_PUBLIC_BACKEND_URL | `http://localhost:8000` | The backend base URL. |
| NEXT_PUBLIC_VIEWER_SLICE_BEFORE | `1` | DECISIONS V1. Pages loaded before the cited page. |
| NEXT_PUBLIC_VIEWER_SLICE_AFTER | `2` | DECISIONS V1. Pages loaded after the cited page. |
| NEXT_PUBLIC_VIEWER_PAGE_ASPECT | `1.294` | The page aspect ratio for the loading placeholders. Fits US Letter. |
| NEXT_PUBLIC_VIEWER_ZOOM_STEP | `0.25` | DECISIONS V3. The scale a zoom click adds. |
| NEXT_PUBLIC_VIEWER_ZOOM_MIN | `0.5` | DECISIONS V3. The smallest zoom factor. |
| NEXT_PUBLIC_VIEWER_ZOOM_MAX | `3` | DECISIONS V3. The largest zoom factor. |
| NEXT_PUBLIC_VIEWER_WIDTH_DEFAULT | `416` | DECISIONS V4. The pane width on first use, in pixels. |
| NEXT_PUBLIC_VIEWER_WIDTH_MIN | `280` | DECISIONS V4. The narrowest the pane gets. |
| NEXT_PUBLIC_VIEWER_WIDTH_MAX | `900` | DECISIONS V4. The widest the pane gets while the chat shows. |
| NEXT_PUBLIC_CHAT_MIN_WIDTH | `360` | DECISIONS V4. The narrowest the chat gets before it hides and the pane fills the row. |
| NEXT_PUBLIC_CHAT_RESTORE_TRAVEL | `24` | DECISIONS V4. The travel to the right, in pixels, that brings a hidden chat back. |
| NEXT_PUBLIC_VIEWER_SLICE_CACHE_ENTRIES | `12` | DECISIONS V6. Slice byte windows kept in memory. |

## Where the next change goes

- Chunk eval: 16 questions with known answer pages and expected answers, from
  the 56-page `pl.pdf`, live in `backend/tests/eval_questions.json`. Nothing
  runs or scores the set yet. Run and score the set. The scores give recall
  and citation precision, and they test the chunk size (DECISIONS D10) and
  the overlap (D11).
- Memory: add the `summary` state field, a compaction node, and a checkpointer
  (MEMORY_DESIGN §4-5).
- Later graph: the Supervisor and Synthesizer topology, the structured
  `AgentAnswer`, and the spec ledger are future work (DECISIONS, Deferred).
- File locations: the graph is `backend/agent/graph.py`, the tools are
  `backend/tools.py`, retrieval is `backend/retrieval.py`, and the routes are
  `backend/api/main.py`.

## Git workflow

The repo uses short-lived feature branches and pull requests into a protected
`main` (GitHub Flow). [`CONTRIBUTING.md`](CONTRIBUTING.md) holds the branch
naming, the commit conventions, the pull-request template, and the one-time
branch-protection setup.

## Coding assistant (Copilot Chat)

Development runs in the built-in VS Code Copilot Chat with OpenRouter models.
The OpenRouter Maestro extension is the language provider: it puts the
OpenRouter models into the chat model picker. The model in use is DeepSeek V4
Pro 0813 (`deepseek/deepseek-v4-pro-0813`). The OpenRouter API key goes into
the Maestro panel, which stores it in VS Code SecretStorage.

The VS Code workspace root sits one level above this repo, so most agent files
live in the workspace `.github/` folder:

- `AGENTS.md` in this repo: the project rules for the coding agent.
- `.github/copilot-instructions.md` at the workspace root: the same project
  rules.
- `.github/instructions/` at the workspace root: targeted rules for
  `**/backend/**`, `**/frontend/**`, and `**/*.md`.
- `.github/skills/` at the workspace root: the `simple-english` and
  `open-pr` skills.
- `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` in this
  repo: GitHub reads these from the repository.

The workspace agent files are local only. The `applyTo` globs are relative to
the workspace root, so the workspace `.github/` folder is the right place for
them.

## Deviations from DECISIONS.md (flagged, not silent)

1. Config surface: env vars, not a `.env` file. DECISIONS P1 says "Pydantic
   `BaseSettings` backed by `.env`". This pass reads env vars only, per the
   bootstrap scope ("no `.env` file in repo"). The DECISIONS rule keeps
   secrets in the environment or a secret store, and this matches it.
2. `models.options` stores slugs, not display names. DECISIONS M2 lists the
   options as `["DeepSeek Flash", "DeepSeek Pro"]` (display names). The slugs
   are the source of truth, so config holds the slugs, and a small
   `_MODEL_LABELS` map (`backend/config.py`) supplies the dropdown labels.
3. Config keys are flat (`MODEL_*`), not dotted (`models.*`). DECISIONS uses
   dotted keys like `models.reasoning_effort = "medium"`. The env-only pass
   maps those to `MODEL_REASONING_EFFORT`, `MODEL_TEMPERATURE`, and
   `MODEL_MAX_TOKENS`.
4. The DeepSeek slugs carry a `~` prefix. OpenRouter serves the DeepSeek
   `-latest` aliases as prerelease, and a slug without the prefix gets a
   `400 "not a valid model ID"` response. Both
   `~deepseek/deepseek-flash-latest` and `~deepseek/deepseek-pro-latest` were
   confirmed live (HTTP 200), and they resolve to `deepseek-v4.1-flash` and
   `deepseek-v4-pro-0813`. DECISIONS.md records the corrected slugs. OpenRouter
   reports the supported reasoning efforts of both slugs as
   `["max", "high", "low", "none"]`, so every tier effort is accepted.
