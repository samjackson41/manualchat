# ManualChat — skeleton

The **bare-minimum "ask a model" loop** for ManualChat, the grounded repair-manual
assistant (capstone). A `chat -> tools -> chat` LangGraph loop with a calculator
tool and three RAG stubs, one FastAPI endpoint, one Next.js chat built on
assistant-ui, deliberately skeletal so real RAG and memory can be added later
without rework.

> **In scope this pass:** LangGraph `StateGraph` with a tool-calling loop, FastAPI `/chat` via
> OpenRouter, Next.js chat + model dropdown, Docker (one image per terminal).
>
> **Out of scope (not built / no deps):** Qdrant, Redis, embeddings, rerankers,
> vector search, the spec ledger.

## Lay of the land

```
manualchat/
  backend/
    config.py        # pydantic-settings BaseSettings — env vars ONLY (no .env)
    llm.py           # thin OpenRouter wrapper (httpx) -> chat(messages, model, params, tools)
    tools.py         # agent tools: OpenAI schemas + executors (calculator, RAG stubs)
    agent/graph.py   # StateGraph: AgentState, chat -> tools -> chat loop (iteration point)
    api/main.py      # FastAPI: /health, /models, /chat, /chat/stream, /manuals
                     # (upload/read/toggle/delete, page slices, whole manual,
                     # thumbnails), /vehicles create/rename/delete
    storage.py       # local manual + vehicle storage (DECISIONS U1, SPEC §5)
    slicer.py        # on-demand PDF page slices for the manual viewer (PyMuPDF)
    schemas.py       # shared Pydantic contracts (Vehicle, Manual, RAG models)
    pyproject.toml   #                 uv project (package = false; deps only)
    uv.lock          #                 generated lockfile (deps only)
    Dockerfile
  frontend/          # Next.js 14 App Router + Tailwind v4 + shadcn/ui + assistant-ui + react-pdf
    app/page.tsx     # top bar + thread-list sidebar + chat, side-by-side viewer
    app/chat-runtime.tsx  # thread-list runtime + localStorage adapter -> POST /chat
    app/vehicle-runtime.tsx  # vehicle list + selection context -> /vehicles
    app/viewer-runtime.tsx  # viewer state: open/close, cited page, manual choice, pane width
    app/theme-runtime.tsx  # light/dark theme state; the choice survives reloads
    app/layout.tsx   # provider stack + a pre-paint script that sets the theme
    app/globals.css  # Tailwind v4 theme, light and dark (red, white, gray, black, gold)
    lib/api.ts       # typed client for every backend call
    lib/viewer-config.ts  # viewer tunables, each from a NEXT_PUBLIC_ env var
    lib/pdf-cache.ts # viewer byte caches: slice map + whole-manual Cache API
    lib/theme.ts     # theme key, the stored choice, and the pre-paint script
    components/      # assistant-ui elements + shadcn/ui primitives + garage UI
                     # (top bar, vehicle selector, manual upload, PDF viewer)
    Dockerfile
  docker-compose.yml # services: backend, frontend (started one-per-terminal)
  README.md          # this file
```

## Run it — one terminal per image

**Terminal 1 — backend** (FastAPI on `:8000`, hot reload):

```bash
OPENROUTER_API_KEY=sk-or-... docker compose up backend
```

**Terminal 2 — frontend** (Next.js on `:3000`, hot reload):

```bash
docker compose up frontend
```

Then open <http://localhost:3000>, add a vehicle, upload a manual, pick
**DeepSeek Flash** or **DeepSeek Pro** in the dropdown, type a query, and get
a reply.

> Do **not** run `docker compose up` (all-in-one) or `-d` (detached) — the two
> services are meant to run in two explicit terminals.

### Good output

- **Terminal 1** prints `Uvicorn running on http://0.0.0.0:8000` and
  `curl http://localhost:8000/health` returns `{"status":"ok"}`.
- **Terminal 2** prints `Ready in …` / `Local: http://localhost:3000`.
- `curl http://localhost:8000/models` returns:
  ```json
  {"default":"~deepseek/deepseek-flash-latest",
   "options":[{"id":"~deepseek/deepseek-flash-latest","label":"DeepSeek Flash"},
              {"id":"~deepseek/deepseek-pro-latest","label":"DeepSeek Pro"}]}
  ```

## Secrets

`OPENROUTER_API_KEY` is the **only** secret. It is passed through as an env var
(`docker-compose.yml` → `OPENROUTER_API_KEY=${OPENROUTER_API_KEY}`), never stored
in the repo. If it's missing, `POST /chat` fails fast with a clear error while
`/health` and `/models` still respond. Never echo or commit the key.

## Configuration (all env vars, no `.env` file)

| Env var | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | _(required for /chat)_ | secret |
| `MODEL_DEFAULT` | `~deepseek/deepseek-flash-latest` | DECISIONS M1 |
| `MODEL_OPTIONS` | `~deepseek/deepseek-flash-latest,~deepseek/deepseek-pro-latest` | DECISIONS M2 (comma-separated) |
| `MODEL_REASONING_EFFORT` | `medium` | ratified (DECISIONS M note) |
| `MODEL_TEMPERATURE` | _(unset)_ | **TBD** — omit to use provider default |
| `MODEL_MAX_TOKENS` | _(unset)_ | **TBD** — omit to use provider default |
| `AGENT_SYSTEM_PROMPT` | the grounding prompt text | DECISIONS A3 — prepended before the first chat call |
| `MANUALS_DIR` | `manuals` | DECISIONS U1 — where each uploaded manual lands as `{manual_id}/`; in Docker this is `/data/manuals` |
| `VEHICLES_DIR` | `vehicles` | SPEC §5 — where each vehicle profile lands as `{vehicle_id}/`; in Docker this is `/data/vehicles` |
| `THUMBNAIL_DPI` | `150` | IMPLEMENTATION Task 5 — the PNG page-preview resolution (dots per inch) for the manual viewer's raster fallback |
| `VIEWER_CACHE_MAX_AGE_SECONDS` | `31536000` | DECISIONS V5 — how long a browser may cache served page bytes; a manual never changes after upload |
| `INGEST_OCR_MIN_CHARS_PER_PAGE` | `50` | DECISIONS D1 — a manual below this average needs OCR and is refused |
| `INGEST_STRIP_HIDDEN_OCR_LAYER` | `true` | DECISIONS D2 — remove the ghost OCR font before Docling |
| `INGEST_NORMALIZATION_ENABLED` | `true` | DECISIONS D3 — repair unit and header noise after Docling |
| `INGEST_USE_PRINTED_PAGE_NUMBERS` | `false` | DECISIONS D12 — citations use the PDF page number |
| `INGEST_DO_OCR` | `false` | DECISIONS S2 — OCR stays off for digital manuals |
| `INGEST_DO_TABLE_STRUCTURE` | `true` | IMPLEMENTATION Task 1 — turn on table extraction |
| `INGEST_TABLE_MODE` | `FAST` | IMPLEMENTATION Task 1 — the fast table model |
| `INGEST_THREADS` | `2` | IMPLEMENTATION Task 1 — keeps peak memory low |
| `INGEST_BATCH_SIZE` | `1` | IMPLEMENTATION Task 1 — one page per batch |
| `INGEST_CHUNK_STRUCTURE_AWARE` | `true` | DECISIONS D9 — split prose on section headings, keep each table as one chunk |
| `INGEST_CHUNK_TOKENS` | `512` | DECISIONS D10 — target size of a prose chunk, in tokens |
| `INGEST_CHUNK_OVERLAP_TOKENS` | `64` | DECISIONS D11 — overlap between neighbouring prose chunks, in tokens |
| `INGEST_TOKENIZER` | `cl100k_base` | DECISIONS D13 — the tiktoken encoding that counts chunk tokens |
| `QDRANT_URL` | _(empty)_ | DECISIONS R3 — empty means local mode: the store lives on disk under `QDRANT_PATH`, no server or credentials; an `http(s)` URL switches to a remote server |
| `QDRANT_PATH` | `qdrant` | DECISIONS R3 — the on-disk directory for the local-mode store (git-ignored) |
| `QDRANT_COLLECTION` | `manualchat_chunks` | DECISIONS R4 — the one collection that holds every manual's chunks |
| `QDRANT_API_KEY` | _(empty in dev)_ | DECISIONS R5 — only set when a remote Qdrant server needs it |
| `RETRIEVAL_EMBED_MODEL` | `multi-qa-mpnet-base-dot-v1` | DECISIONS R6 — the sentence-transformers model that embeds chunks and queries |
| `RETRIEVAL_RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | DECISIONS R7 — the cross-encoder that reranks the candidate chunks |
| `RETRIEVAL_CANDIDATE_K` | `50` | DECISIONS R8 — how many first-pass candidates the reranker gets |
| `RETRIEVAL_TOP_N` | `5` | DECISIONS R9 — how many chunks come back to the agent |

Generation params are **under research** and surfaced as `MODEL_*` env vars so
they can be tuned without code edits. Unset values are omitted from the OpenRouter
request entirely.

The viewer tunables are **frontend** values. Next.js inlines `NEXT_PUBLIC_` env
vars when it builds, or when the dev server starts, so restart the frontend
after a change.

| Env var | Default | Notes |
|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | base URL of the backend API |
| `NEXT_PUBLIC_VIEWER_SLICE_BEFORE` | `1` | DECISIONS V1 — pages loaded before the cited page |
| `NEXT_PUBLIC_VIEWER_SLICE_AFTER` | `2` | DECISIONS V1 — pages loaded after the cited page |
| `NEXT_PUBLIC_VIEWER_PAGE_ASPECT` | `1.294` | height/width that sizes a page before it renders |
| `NEXT_PUBLIC_VIEWER_ZOOM_STEP` | `0.25` | DECISIONS V3 — the scale a zoom click adds |
| `NEXT_PUBLIC_VIEWER_ZOOM_MIN` | `0.5` | DECISIONS V3 — the smallest zoom |
| `NEXT_PUBLIC_VIEWER_ZOOM_MAX` | `3` | DECISIONS V3 — the largest zoom |
| `NEXT_PUBLIC_VIEWER_WIDTH_DEFAULT` | `416` | DECISIONS V4 — pane width on first use, in pixels |
| `NEXT_PUBLIC_VIEWER_WIDTH_MIN` | `280` | DECISIONS V4 — the narrowest the pane drags |
| `NEXT_PUBLIC_VIEWER_WIDTH_MAX` | `900` | DECISIONS V4 — the widest the pane drags |
| `NEXT_PUBLIC_VIEWER_SLICE_CACHE_ENTRIES` | `12` | DECISIONS V6 — slice byte windows kept in memory |

## Where the next change goes (documented in code)

- **RAG** → the contracts and stub bodies for `search_manual` / `extract_specs` /
  `get_page_text` are in `backend/tools.py`. Real retrieval replaces the stub
  bodies (IMPLEMENTATION Task 4). The graph loop is already in place.
- **Ingest** → `POST /manuals` stores the PDF, sets `status` to `processing`,
  and runs the Docling pipeline in the background (IMPLEMENTATION Task 1). It
  fills the manual's directory with `page_text/`, `tables.json`, and
  `ingest.json`, then sets `status` to `ready` or `error`. Clients poll
  `GET /manuals/{id}` for the outcome. The pipeline is also runnable by hand
  with `python -m backend.ingest <manual_id>`.
- **Manual management** → `PATCH /manuals/{id}` enables or disables a manual.
  A disabled manual keeps its stored files and its index, but search skips its
  chunks. `DELETE /manuals/{id}` purges the manual's chunks from the index,
  then removes the record and its directory. Deletion is permanent, so the
  vehicle dialog in the frontend asks for confirmation before it deletes.
- **Memory** → add `summary` field + compaction node (MEMORY_DESIGN §4-5) and a
  checkpointer.

## Git workflow

Short-lived feature branches + PRs into a protected `main` (GitHub Flow). See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for branch naming, commit conventions, the
PR template, and the one-time branch-protection setup.

## Coding assistant (Copilot Chat)

Development runs in the built-in VS Code Copilot Chat with OpenRouter models.
The **OpenRouter Maestro** extension is the language provider: it puts any
OpenRouter model into the chat model picker. The model in use is DeepSeek V4
Pro 0813 (`deepseek/deepseek-v4-pro-0813`). Your OpenRouter API key goes into
the Maestro panel (VS Code SecretStorage), never into the repo.

Agent rules and skills live in Copilot formats. The VS Code workspace root sits
one level above this repo, so the agent files live in the workspace `.github/`
folder. This repo keeps only the two files that GitHub reads from it:

- `AGENTS.md`: project-wide rules, read at the start of every task. Tracked here.
- `.github/copilot-instructions.md`: the same project rules. Workspace root.
- `.github/instructions/*.instructions.md`: targeted rules for `**/backend/**`,
  `**/frontend/**`, and `**/*.md`. Workspace root.
- `.github/skills/`: the `simple-english` and `open-pr` skills. Workspace root.
  `open-pr` opens a PR with the `gh` CLI.
- `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md`: tracked in
  this repo, because GitHub reads them from the repository.

The workspace agent files are local only. The `applyTo` globs are relative to
the workspace root, so the workspace `.github/` folder is the right place for
them.

## Deviations from DECISIONS.md (flagged, not silent)

1. **Config surface: env vars, not `.env`.** DECISIONS P1 says "Pydantic
   `BaseSettings` backed by `.env`"; this pass reads **env vars only** (per the
   bootstrap scope: "no `.env` file in repo"). Consistent with DECISIONS' own
   "secrets via Secret Manager / environment" rule. Revisit `.env` (git-ignored)
   if local non-secret tunables should be filed.
2. **`models.options` stored as slugs, not display names.** DECISIONS M2 lists the
   options as `["DeepSeek Flash", "DeepSeek Pro"]` (display names); the slugs
   (`deepseek/deepseek-f|pro-latest`) are pinned below that table, and the
   bootstrap scope pins the slugs as config values. So config holds slugs (source
   of truth) and a tiny `_MODEL_LABELS` map (`backend/config.py`) supplies the
   cosmetic dropdown labels.
3. **Config-key naming is flat (`MODEL_*`), not dotted (`models.*`).** DECISIONS
   uses dotted keys like `models.reasoning_effort = "medium"`. Since this pass is
   env-only, those map to flat `MODEL_REASONING_EFFORT` / `MODEL_TEMPERATURE` /
   `MODEL_MAX_TOKENS`. A nested dotted config object can be reintroduced when a
   `.env`-backed config layer returns.
4. **Model slugs carry a `~` prefix (corrected against the live catalog).** DECISIONS.md pinned the slugs as `deepseek/deepseek-f|pro-latest`, but OpenRouter serves DeepSeek's `-latest` aliases as *prerelease* and requires the `~` prefix — the bare slug returns `400 "not a valid model ID"`. Both `~deepseek/deepseek-flash-latest` and `~deepseek/deepseek-pro-latest` were confirmed live (HTTP 200) and resolve to `deepseek-v4.1-flash` / `deepseek-v4-pro-0813`. This is a correction to DECISIONS, not a silent change — flagging it here. Also confirmed `reasoning_effort=medium` is accepted (OpenRouter forwards it; DeepSeek ignores it), so the ratified `medium` default is safe.