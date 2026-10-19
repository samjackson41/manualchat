# DECISIONS — ManualChat (decision log)

> Living log of ratified decisions. Companion to `project_proposal.md`,
> `SPIKE_FINDINGS.md`, and `MEMORY_DESIGN.md`. Each entry states the decision,
> the governing default, and (where the value is arbitrary/tunable) the config key
> that surfaces it.
>
> Recording sources. When a decision rests on external documentation, add
> `Source:` and `Last-checked:` lines to the entry. `Source:` is a URL or a doc
> title. `Last-checked:` is an ISO date (`YYYY-MM-DD`). This makes a stale
> decision easy to see.

---

## Governing principle

**P1 — every arbitrary/tunable value is surfaced to config, never hardcoded.**

Thresholds, buffer sizes, model IDs, regions, feature flags — anything a reasonable
engineer might later tweak — lives in a single config surface (Pydantic `BaseSettings`
backed by `.env`, matching the project's existing Pydantic-for-tool-contracts choice).
Non-secret values (thresholds, model slugs, regions) belong in config. Actual secrets
(API keys) stay out of config/repo — managed via Secret Manager / environment, per the
workspace secret rules.

---

## MVP scope (revised)

| Decision | Value |
|---|---|
| S1 | **Scanned-manual / FJ40 spike work is out of MVP.** Deferred to post-MVP. |
| S2 | MVP is **digital-only**: every manual has a PDF text layer → `do_ocr=False` everywhere. |
| S3 | **Dev/test manuals**: Yamaha Rhino 700 Service Manual (503 p) + two Johnson outboard manuals — the 2002/2003 SN/ST 60° V 2-stroke Service Manual (375 p) and the 2004 90–175 hp PL/PX/CX/GL Operator's Guide (56 p). (These form the digital-only working set; the FJ40 is out of MVP per S1.) |
| S4 | "Has text layer?" probe still runs at ingest so future scanned uploads are handled safely, but no scanned manual is expected in MVP. |

**Consequence**: the OCR-engine choice (RapidOCR vs. Tesseract/Surya/Paddle) drops out of
MVP. It stays a *placeholder* default (RapidOCR, `lang=["english"]`) for when the scanned
path returns — no spike, no config churn, just a deferred note.

---

## Ratified defaults (all approved; values surfaced to config)

| # | Decision | Default | Config key |
|---|---|---|---|
| D1 | Text-layer probe threshold — gate `do_ocr` per manual (`needs_ocr = chars/page < threshold`) | `50` chars/page | `ingest.ocr_min_chars_per_page` |
| D2 | Sanitize the hidden OCR text layer **at source** (PyMuPDF suppresses `HiddenHorzOCR`-style ghost fonts) before docling | `true` | `ingest.strip_hidden_ocr_layer` |
| D3 | Normalization is an **explicit ingest stage** (`docling → normalize → embed`), not a post-hoc fallback | — (always on) | `ingest.normalization_enabled` |
| D4 | OCR engine (deferred post-MVP; placeholder only) | RapidOCR `lang=["english"]` | `ocr.engine`, `ocr.lang` |
| D5 | Ingestion worker ships **models baked into the Docker image** (no warm volume) for MVP | baked | `worker.models_in_image` |
| D6 | Compaction token threshold, as a fraction of context window | `0.60` | `memory.compact_threshold_fraction` |
| D7 | Rolling-buffer `keep_last` message count | `8` | `memory.keep_last_messages` |
| D8 | Token counter for compaction | `cl100k_base` (tiktoken proxy) | `memory.tokenizer` |
| D9 | Chunking strategy: split on section headings and keep each table inside one chunk | `true` | `ingest.chunk_structure_aware` |
| D10 | Chunk size in tokens | `512` | `ingest.chunk_tokens` |
| D11 | Chunk overlap in tokens | `64` | `ingest.chunk_overlap_tokens` |
| D12 | Citations use the physical PDF page number for every manual. Manuals use different printed numbering systems, so the printed number is not recovered. The interface tells the user that the number is a PDF page number. | `false` | `ingest.use_printed_page_numbers` |
| D13 | Token counter for chunking | `cl100k_base`, the counter that `memory.tokenizer` already names | `ingest.tokenizer` |
| D14 | Docker image ships **CPU-only torch/torchvision** (no CUDA) for MVP | CPU | — (build-time) |

D1–D3 apply defensively to the Rhino + Johnson manuals (the Rhino was produced through an
Acrobat "Paper Capture" pipeline, so it may carry the ghost OCR layer — sanitize-at-source
is harmless either way).

D14 keeps the image CPU-only for MVP. The CPU torch build is pinned in
`backend/pyproject.toml` through the PyTorch CPU index. GPU acceleration is
deferred to MVP+1, when the scanned-manual OCR path (S1) returns and a GPU host
is in play.

D9 to D11 and D13 follow common practice. A chunk holds 256 to 1024 tokens, and
neighbouring chunks share 10 to 20 percent of their text. The prototype runs
against the 56-page `pl.pdf` operator's guide first, so one ingest pass stays
short. The `512` and `64` values are a starting point. The eval reports recall
and citation precision for other sizes, and the numbers move only when the eval
shows a better value.

Source: https://python.langchain.com/docs/how_to/recursive_text_splitter/ and
https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_splitter/
Last-checked: 2026-10-15

---

## Model selection (single model, UI-selectable)

> Replaces the earlier "cheap-first tiering" plan. One active model powers **every**
> process — planning, synthesis, summarization/compaction, and the eval judge. The user
> picks it via a simple dropdown in the UI; there are no per-role tiers to reason about.

| # | Decision | Config key |
|---|---|---|
| M1 | A single active model drives all agent processes (planning, synthesis, summarization, judge) | `models.default` = **DeepSeek Flash** |
| M2 | The ordered list of models offered in the UI selector | `models.options` = **["DeepSeek Flash", "DeepSeek Pro"]** to start |
| M3 | The UI selection is a **runtime override** of `models.default`, scoped to the session (in-memory for MVP — no persistence yet) | (session override) |

> **Later improvement**: expand `models.options` with more models — no schema/flow change,
> it's just a longer list feeding the same dropdown.
>
> OpenRouter slugs (pinned in config, not code). OpenRouter serves the DeepSeek
> `-latest` aliases as prerelease, so each slug carries a `~` prefix:
> - DeepSeek Pro → `~deepseek/deepseek-pro-latest`
> - DeepSeek Flash → `~deepseek/deepseek-flash-latest`
>
> Reasoning: both models run with **medium** reasoning effort for now
> (`models.reasoning_effort = "medium"`).

Source: https://openrouter.ai/docs/quickstart
Last-checked: 2026-10-15

---

## Cloud region

| Item | Decision |
|---|---|
| R1 | Region = **us-east-1** (closest). GCP `us-east1` for Cloud Run/GCS; Qdrant Cloud in us-east-1. |
| R2 | Redis stays on its existing **AWS us-east-1** Essentials tier — accept the cross-cloud hop; revisit only if latency shows up in eval. |

**Prototyping**: everything except OpenRouter stays local on the development
machine (16 GB RAM). Qdrant, storage, and the models run locally. R1 and R2 hold
for a production deployment.

---

## Manual upload idempotency

| Item | Decision |
|---|---|
| U1 | **MVP**: assume a smart single-user — each manual is uploaded/processed **once** and must **remain in local storage** in a `manuals/{manual_id}/` subdirectory so the processed result is never re-derived. No dedup check. |
| U2 | **MVP+1**: add a **file-hash check** (against stored manual hashes) and surface a **warning** to the user on a suspected re-upload. |

---

## Manual enable, disable, and delete

| Item | Decision |
|---|---|
| M1 | A manual can be **disabled**. The record, files, and index stay in place; the retrieval search excludes the manual's chunks. A disabled manual can be re-enabled at any time. API: `PATCH /manuals/{manual_id}` with `{"enabled": true/false}`. |
| M2 | Delete is **permanent**. `DELETE /manuals/{manual_id}` purges the manual's chunks from Qdrant, then removes the record and its directory (PDF, page text, tables). There is no undo, so the UI asks for confirmation. The purge runs first: if the purge fails, the record stays in place and the deletion can be retried. |
| M3 | Manuals cannot be renamed. A manual keeps the display name it was uploaded with. |

---

## Spec ledger storage

| Item | Decision |
|---|---|
| L1 | The spec ledger lives in **Qdrant** and is **populated lazily** — only when the agent retrieves a table that answers a spec question. Values are parsed **verbatim from the source table** (never from model prose output) and upserted keyed by `(vehicle_id, manual_id, subject)`. No full-manual preprocessing at ingest. |
| L2 | **MVP scope = table-derived specs only.** A value buried in prose is answered with citation grounding, not written into the ledger. |
| L3 | Revisit Postgres **only if** post-MVP multi-manual conflict attribution requires relational joins across manuals. |

The POC keeps the ledger minimal: `extract_specs` does targeted table retrieval
and returns values without writing a ledger. The lazy Qdrant ledger in L1 is
future work.

---

## Retrieval (RAG pipeline)

The ingestion stages and the retrieval models. IMPLEMENTATION §2.2 and Tasks 1 to
4 hold the design. These entries fix the values that the design left open, and
the values that the documents disagreed about.

| # | Decision | Default | Config key |
|---|---|---|---|
| R3 | Retrieval backend in development: Qdrant in local mode (a path on disk or in memory), not a `docker-compose.yml` service yet | local mode | `qdrant.url` |
| R4 | Qdrant collection name | `manualchat_chunks` | `qdrant.collection` |
| R5 | Qdrant API key | Empty in development, because the local service needs no key. Production supplies a secret through the environment. The value never enters the repository. | `qdrant.api_key` |
| R6 | Embedding model for the first pass | `multi-qa-mpnet-base-dot-v1` | `retrieval.embed_model` |
| R7 | Reranker model for the second pass | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `retrieval.rerank_model` |
| R8 | Candidate count handed to the reranker | `50` | `retrieval.candidate_k` |
| R9 | Chunk count returned to the agent | `5` | `retrieval.top_n` |

R3 keeps DECISIONS R1 for production. R1 names Qdrant Cloud in `us-east-1`. The
local service is a development choice, so an ingest run and a query need no
network and no credentials.

Source: https://qdrant.tech/documentation/ and
https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-dot-v1 and
https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2
Last-checked: 2026-10-15

---

## Agent graph and answer contract

| # | Decision | Value | Config key |
|---|---|---|---|
| A1 | The POC graph stays a flat `chat ↔ tools` loop. The Supervisor plus Synthesizer topology in IMPLEMENTATION §2.3 is future work. | — | — |
| A2 | The agent answers in markdown text with `[Page N]` citations. The structured `AgentAnswer` in IMPLEMENTATION §4.1 is future work. | — | — |
| A3 | The system prompt carries the grounding rules: every claim and step names its page, the answer states plainly when the manual holds no answer, and conflicting values show both pages. The prompt text lives in config (field `agent_system_prompt`, env `AGENT_SYSTEM_PROMPT`) so it is tunable, and the graph prepends it before the first chat call. | — | `agent.system_prompt` |

The graph runs as a flat `chat ↔ tools` loop today, and `/chat` returns markdown
text with `[Page N]` citations. The Supervisor, the Synthesizer, the
`AgentAnswer`, the hop cap, and the confidence gate are future work (see the
Deferred section).

---

## Testing and continuous integration

| # | Decision | Value |
|---|---|---|
| T1 | Unit tests inject a fake embedder, so no test downloads a model | — |
| T2 | The end-to-end retrieval test carries a pytest marker and stays out of the default run | `@pytest.mark.heavy` |
| T3 | The default CI run stays cheap: dependency install, the syntax check, and the marked test excluded | — |

Docling, torch, and sentence-transformers make a full install slow and large. T1
and T2 keep the default check fast. Tests run against mocks, not the full model
set, even though the project prefers end-to-end tests. Some behaviour needs a
mock to stay testable without a download.

---

## Manual Viewer (PDF pane)

| Item | Decision |
|---|---|
| V1 | A dedicated **Manual Viewer** mode — a UI toggle that opens the page set the agent deemed relevant (the top-scored `search_manual` chunk page-set, gated by a rerank-score threshold) in a pane beside the chat, rendered with `react-pdf` in `[Page−1, Page+2]` 4-page slices. The window sizes are the `NEXT_PUBLIC_VIEWER_SLICE_BEFORE` and `NEXT_PUBLIC_VIEWER_SLICE_AFTER` config values. (See SPECIFICATION §2.1 and IMPLEMENTATION Tasks 2/6.) |
| V2 | The pane can open a manual's whole PDF on demand, so the reader can read the full manual in the app. A `View whole manual` button in the pane fetches `GET /manuals/{id}/pdf`, which streams the stored `source.pdf`. The button carries the tooltip `Whole manual may be slow to load`. The pages mount lazily as the reader scrolls, so a large manual stays responsive. |
| V3 | The pane carries zoom controls over the pages: a step per click (`NEXT_PUBLIC_VIEWER_ZOOM_STEP`, default `0.25`) inside a range (`NEXT_PUBLIC_VIEWER_ZOOM_MIN` `0.5` to `NEXT_PUBLIC_VIEWER_ZOOM_MAX` `3`). A zoom of `1` fits a page to the pane width. A click on the shown percentage resets the zoom to `1`. |
| V4 | The reader sets the chat/pane split by dragging the pane's left edge, or with the arrow keys on that edge. The width is clamped to `NEXT_PUBLIC_VIEWER_WIDTH_MIN` (`280`) and `NEXT_PUBLIC_VIEWER_WIDTH_MAX` (`900`) pixels and defaults to `NEXT_PUBLIC_VIEWER_WIDTH_DEFAULT` (`416`). The choice survives reloads in `localStorage`. |
| V5 | The stored page bytes never change after upload (U1), so the page-slice and whole-manual endpoints answer with `Cache-Control: public, max-age=<VIEWER_CACHE_MAX_AGE_SECONDS>, immutable` (default `31536000`) and an `ETag`. A request whose `If-None-Match` matches returns `304`. The slice `ETag` comes from the stored PDF and the page range, not the slice bytes, because PyMuPDF stamps a fresh document id into every re-serialisation. |
| V6 | The viewer caches PDF bytes, never rendered pages. Page slices live in a module-level `Map` keyed by manual id and page range, capped at `NEXT_PUBLIC_VIEWER_SLICE_CACHE_ENTRIES` (`12`) entries with the least recently used entry dropped first; the map clears on a reload or a tab close, not when the reader switches threads or pane modes. A whole manual is cached once per manual in the Cache API, under `manualchat-manual-pdf`. Both caches hold Blobs, which react-pdf can read more than once, unlike the ArrayBuffer that pdfjs detaches. Deleting a manual drops its cached bytes. |

---

## Frontend appearance

| Item | Decision |
|---|---|
| C1 | The UI has a light theme and a dark theme. The first visit follows the operating system's colour scheme. After the visitor chooses, the choice is stored in `localStorage` and wins on later visits. The theme is applied before the first paint, so the page never flashes the wrong theme. |
| C2 | A top bar carries the vehicle selector, the upload button, the viewer toggle, the model selector, and the theme toggle, over a thin red rule. The manual viewer opens as a right-hand pane beside the chat. The wrench-in-bubble logo (`frontend/assets/manualchat-logo.svg`) replaces the ManualChat wordmark at the top of the thread list. |

---

## Dev tooling (coding assistant)

| # | Decision | Notes |
|---|---|---|
| W1 | The development assistant is the built-in VS Code Copilot Chat with **OpenRouter Maestro** as the language-provider extension (any OpenRouter model appears in the chat model picker). | Chat model in use: `deepseek/deepseek-v4-pro-0813` (DeepSeek V4 Pro 0813). The API key lives in VS Code SecretStorage, not in the repo. |
| W2 | Agent customization lives in Copilot formats. The agent files sit in the VS Code workspace `.github/` folder, one level above the repo: `copilot-instructions.md`, `instructions/*.instructions.md` (targeted `applyTo` scopes), and `skills/{simple-english,open-pr}/SKILL.md`. `AGENTS.md` stays tracked in the repo. `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` stay tracked in the repo, because GitHub reads them from the repository. The workspace agent files are local only and tracked by no repository. The `applyTo` globs are relative to the workspace root, so they read `**/backend/**` and `**/frontend/**`. | GitHub Copilot code review reads `.github/copilot-instructions.md` only from the repository root, so it does not read the workspace-level file. |

Source: https://code.visualstudio.com/docs/agent-customization/custom-instructions and
https://marketplace.visualstudio.com/items?itemName=husamettinulutas.openrouter-maestro
Last-checked: 2026-10-13

---

## Deferred / undecided (no decision now — revisit later)

- **OCR-engine head-to-head** — deferred with the whole scanned/FJ40 path (S1).
- **Normalization rules catalog** — the *existence* of the stage is decided (D3); the
  exact unit/header repair rules (`lb`/`Ib`, `m· kg`, `SPECiFiCATIONS`, diagram-symbol
  junk) should be enumerated as test fixtures when the stage is built.
- **Supervisor and Synthesizer graph, the `AgentAnswer`, the hop cap, and the
  confidence gate** — the POC uses a flat loop with markdown answers.
- **Spec ledger** — the POC returns table values without writing a ledger.
- **Scanned-manual rejection probe** — not built for the POC. The prototype
  manual `pl.pdf` is digital, so no scanned manual is expected.
- **Manual Viewer rerank threshold** — the value that opens the viewer page set.
- **Docker work** — the Qdrant service in `docker-compose.yml` and the baked
  ingestion models.
- **GPU acceleration** — deferred to MVP+1 with the scanned-manual OCR path (S1).
  The Docker image ships CPU-only torch (D14); revisit when a GPU host is in play.