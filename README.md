# ManualChat — skeleton

The **bare-minimum "ask a model" loop** for ManualChat, the grounded repair-manual
assistant (capstone). One LangGraph node, zero tools, one FastAPI endpoint, one
Next.js chat box with a model selector — deliberately skeletal so nodes/tools/RAG
can be added later without rework.

> **In scope this pass:** LangGraph `StateGraph` (no tools), FastAPI `/chat` via
> OpenRouter, Next.js chat + model dropdown, Docker (one image per terminal).
>
> **Out of scope (not built / no deps):** Qdrant, Redis, embeddings, rerankers,
> Docling, PDF ingestion, vector search, the spec ledger, the PDF Manual Viewer.

## Lay of the land

```
manualchat/
  backend/
    config.py        # pydantic-settings BaseSettings — env vars ONLY (no .env)
    llm.py           # thin OpenRouter wrapper (httpx) -> chat(messages, model, params)
    agent/graph.py   # minimal StateGraph: AgentState, chat node, tools=[]  (iteration point)
    api/main.py      # FastAPI: GET /health, GET /models, POST /chat
    pyproject.toml   #                 uv project (package = false; deps only)
    uv.lock          #                 generated lockfile (deps only)
    Dockerfile
  frontend/          # Next.js 14 App Router + Tailwind (no shadcn/ui)
    app/page.tsx     # chat box + model-selector dropdown (fetches /models)
    app/layout.tsx
    app/globals.css
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

Then open <http://localhost:3000>, pick **DeepSeek Flash** or **DeepSeek Pro**
in the dropdown, type a query, and get a reply.

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

Generation params are **under research** and surfaced as `MODEL_*` env vars so
they can be tuned without code edits. Unset values are omitted from the OpenRouter
request entirely.

## Where the next change goes (documented in code)

- **System prompt** → prepend a `system` message to `messages` (no new node).
- **Tool calling** → append schemas to `tools` in `backend/agent/graph.py` and
  add a `chat -> tool -> chat` loop.
- **RAG** → `search_manual` / `extract_specs` / `get_page_text` land in the same
  `tools` list (IMPLEMENTATION Task 4).
- **Memory** → add `summary` field + compaction node (MEMORY_DESIGN §4-5) and a
  checkpointer.

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