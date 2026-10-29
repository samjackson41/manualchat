# DECISIONS

The decision log for ManualChat.
Companion files are `project_proposal.md`, `SPIKE_FINDINGS.md`, and `MEMORY_DESIGN.md`.
Each entry states the decision, the default value, and the configuration key that holds the value.
When a decision rests on external documentation, the entry carries `Source:` and `Last-checked:` lines.
The date makes a stale decision easy to see.

## Governing principle

P1: every arbitrary or tunable value lives in the configuration, never in code.
A Pydantic `BaseSettings` object reads the values from `.env`.
Non-secret values (thresholds, model slugs, regions) belong in the configuration.
Secrets (API keys) stay out of the repository and come from the environment.

## MVP scope

| Decision | Value |
|---|---|
| S1 | Scanned-manual and FJ40 spike work is out of the MVP scope. |
| S2 | The MVP handles digital manuals only. Every manual has a PDF text layer, so the ingestion runs with `do_ocr=False`. |
| S3 | The dev and test manuals are the Yamaha Rhino 700 Service Manual (503 pages) and two Johnson outboard manuals: the 2002/2003 SN/ST 60° V 2-stroke Service Manual (375 pages) and the 2004 90 to 175 hp PL/PX/CX/GL Operator Guide (56 pages). |
| S4 | The text-layer probe still runs at ingest, so a future scanned upload is handled safely. No scanned manual is expected in the MVP. |

The OCR-engine choice drops out of the MVP scope.
The OCR engine stays a placeholder default (RapidOCR, `lang=["english"]`) for the day the scanned path returns.
There is no spike and no configuration churn.

## Ratified defaults

| ID | Decision | Default | Configuration key |
|---|---|---|---|
| D1 | Text-layer probe threshold. The ingest sets `needs_ocr` when a manual has fewer characters per page than this value. | `50` chars/page | `ingest.ocr_min_chars_per_page` |
| D2 | Sanitize the hidden OCR text layer at source before docling. PyMuPDF suppresses ghost fonts such as `HiddenHorzOCR`. | `true` | `ingest.strip_hidden_ocr_layer` |
| D3 | Normalization is an explicit ingest stage (`docling → normalize → embed`), not a fallback. | always on | `ingest.normalization_enabled` |
| D4 | OCR engine, deferred to post-MVP as a placeholder | RapidOCR, `lang=["english"]` | `ocr.engine`, `ocr.lang` |
| D5 | The ingestion worker ships the models baked into the Docker image for the MVP. No warm volume. | baked | `worker.models_in_image` |
| D6 | Compaction token threshold, as a fraction of the context window | `0.60` | `memory.compact_threshold_fraction` |
| D7 | Rolling-buffer count of kept messages | `8` | `memory.keep_last_messages` |
| D8 | Token counter for compaction | `cl100k_base` (the tiktoken proxy) | `memory.tokenizer` |
| D9 | Chunking splits on section headings and keeps each table inside one chunk | `true` | `ingest.chunk_structure_aware` |
| D10 | Chunk size in tokens | `512` | `ingest.chunk_tokens` |
| D11 | Chunk overlap in tokens | `64` | `ingest.chunk_overlap_tokens` |
| D12 | Citations use the physical PDF page number. Manuals use different printed numbering, so the printed number is not recovered. The interface tells the user that the number is a PDF page number. | `false` | `ingest.use_printed_page_numbers` |
| D13 | Token counter for chunking, the counter that `memory.tokenizer` already names | `cl100k_base` | `ingest.tokenizer` |
| D14 | The Docker image ships CPU-only torch and torchvision (no CUDA) for the MVP | CPU | build-time, no key |

D1 to D3 apply to the Rhino and Johnson manuals.
The Rhino came from an Acrobat Paper Capture pipeline, so it can carry the ghost OCR layer.
The sanitize step is harmless either way.

D14 keeps the image CPU-only for the MVP.
The CPU torch build is pinned in `backend/pyproject.toml` through the PyTorch CPU index.
GPU acceleration is deferred to MVP+1, when the scanned-manual OCR path (S1) returns and a GPU host is in play.

D9 to D11 and D13 follow common practice.
A chunk holds 256 to 1024 tokens, and neighboring chunks share 10 to 20 percent of their text.
The prototype runs against the 56-page operator guide first, so one ingest pass stays short.
The values `512` and `64` are a starting point.
The eval reports recall and citation precision for other sizes.
The numbers move only when the eval shows a better value.

Source: https://python.langchain.com/docs/how_to/recursive_text_splitter/ and
https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_splitter/
Last-checked: 2026-10-15

## Model selection

| ID | Decision | Value | Configuration key |
|---|---|---|---|
| M1 | The selected model sets the agent's tier. A tier fixes a cheap working model that runs the tool loop and the supervisor's routing check, and a strong authoring model that writes the final answer. Flash selects `fast`; Pro selects `pro`; a slug that matches neither falls back to `fast`. | see the tier table below | `models.super_sub_tiers`, `models.super_sub_slug_tiers`, `models.super_sub_default_tier` |
| M2 | The ordered model list for the UI selector | DeepSeek Flash, then DeepSeek Pro | `models.options` |
| M3 | The UI selection is a runtime override of `models.default`, scoped to the session and held in memory | session override | (none yet) |

| Tier | Trigger slug | Working model (`sub_model`): routing and tools | Authoring model (`supervisor_model`): the answer |
|---|---|---|---|
| `fast` | `~deepseek/deepseek-flash-latest` | Flash, `reasoning_effort=low` | Flash, `reasoning_effort=high` |
| `pro` | `~deepseek/deepseek-pro-latest` | Flash, `reasoning_effort=low` | Pro, `reasoning_effort=high` |

The tier table lives in `SUPER_SUB_TIERS` as JSON, with code defaults equal to the table above.
The slug-to-tier map lives in `SUPER_SUB_SLUG_TIERS`.
The `fast` tier is "flash low thinking for the working model, flash high thinking for the answer".
The `pro` tier is "flash low thinking for the working model, pro high thinking for the answer".
The two tiers differ only in the authoring model, so the expensive model is spent only on the answer.

A routing check is a two-way decision, so it runs on the working model.
Measured against OpenRouter, Pro at `max` cost $0.00062 to $0.00087 and took 3.4 to 7.7 seconds per routing call.
Flash at `low` cost $0.00002 to $0.00005 and took 0.3 to 1.4 seconds, and chose the same route.
Pro output costs $8.00 per million tokens against Flash at $0.50, so the authoring model is reserved for the answer.
`max` did not produce more reasoning tokens than `high`; it is a budget cap, not a guarantee of more thinking.

The working model keeps `low` effort, never `none`.
At `none` the model skipped the calculator and answered arithmetic from its own knowledge, and returned a wrong result once in four runs.
`none` also overrides the model's own default: OpenRouter reports Flash as `default_enabled: true` with `default_effort: "high"`.

The `models.options` list can grow later with no schema or flow change.
OpenRouter serves the DeepSeek `-latest` aliases as prerelease, so each slug carries a `~` prefix.
DeepSeek Pro is `~deepseek/deepseek-pro-latest`.
DeepSeek Flash is `~deepseek/deepseek-flash-latest`.
OpenRouter reports the supported efforts of both slugs as `["max", "high", "low", "none"]`, so every tier effort is accepted and no fallback is needed.

Source: https://openrouter.ai/docs/quickstart and https://openrouter.ai/api/v1/models
Last-checked: 2026-10-20

## Cloud region

| Item | Decision |
|---|---|
| R1 | The region is us-east-1, the closest one. GCP `us-east1` for Cloud Run and GCS. Qdrant Cloud runs in us-east-1. |
| R2 | Redis stays on its existing AWS us-east-1 Essentials tier. The cross-cloud hop is accepted. Latency results in the eval reopen the question. |

For prototyping, everything except OpenRouter runs on the development machine (16 GB of RAM).
Qdrant, storage, and the models run locally.
R1 and R2 hold for a production deployment.

## Upload idempotency

| Item | Decision |
|---|---|
| U1 | **MVP**: assume a smart single-user — each manual is uploaded/processed **once** and must **remain in local storage** in a `manuals/{manual_id}/` subdirectory so the processed result is never re-derived. Duplicate detection is U2. |
| U2 | Each manual stores the SHA-256 of its uploaded PDF in `content_hash`. An upload whose hash matches an existing manual of the same vehicle is refused with `409` before ingest, naming the stored manual. A record that carries no digest has one computed from its stored `source.pdf` and written back. The same PDF can still be uploaded under a different vehicle. |
| U3 | Ingest records how far it has come on the manual's `progress` field, so the upload dialog shows a bar instead of an unexplained wait. `stage` names the step: `probe`, `convert`, `index`, or `done`. `completed` and `total` count the units of that step. The units are pages while `convert` reads the PDF, and chunks while `index` embeds them. Docling reports every converted page through its own progress callback, and indexing reports every embedded batch. |

---

## Manual enable, disable, and delete

| Item | Decision |
|---|---|
| M1 | A manual can be disabled. The record, the files, and the index stay in place. The retrieval search excludes the chunks of a disabled manual, and the manual can be re-enabled at any time. API: `PATCH /manuals/{manual_id}` with `{"enabled": true/false}`. |
| M2 | Delete is permanent. `DELETE /manuals/{manual_id}` purges the chunks of the manual from Qdrant, then removes the record and its directory (PDF, page text, tables). There is no undo, so the UI asks for confirmation. The purge runs first. If the purge fails, the record stays in place and the deletion can be retried. |
| M3 | Manuals cannot be renamed. A manual keeps the display name it was uploaded with. |

## Spec ledger storage

| Item | Decision |
|---|---|
| L1 | The spec ledger lives in Qdrant and is populated lazily, only when the agent retrieves a table that answers a spec question. Values are parsed verbatim from the source table, never from model prose. The ledger keys are `vehicle_id`, `manual_id`, and `subject`. No full-manual preprocessing happens at ingest. |
| L2 | MVP scope covers table-derived specs only. A value buried in prose is answered with citation grounding and is not written into the ledger. |
| L3 | Postgres is revisited only if post-MVP multi-manual conflict attribution needs relational joins across manuals. |

The POC keeps the ledger minimal.
`extract_specs` does targeted table retrieval and returns values without writing a ledger.
The lazy Qdrant ledger in L1 is future work.

## Retrieval

The ingestion stages and the retrieval models are designed in IMPLEMENTATION §2.2 and Tasks 1 to 4.
The entries below fix the values that the design left open, and the values that the documents disagreed about.

| ID | Decision | Default | Configuration key |
|---|---|---|---|
| R3 | Retrieval backend in development: Qdrant in local mode (a path on disk or in memory), not a docker-compose service yet | local mode | `qdrant.url` |
| R4 | Qdrant collection name | `manualchat_chunks` | `qdrant.collection` |
| R5 | Qdrant API key. Empty in development, because the local service needs no key. Production supplies a secret through the environment. The value never enters the repository. | (empty) | `qdrant.api_key` |
| R6 | Embedding model for the first pass | `multi-qa-mpnet-base-dot-v1` | `retrieval.embed_model` |
| R7 | Reranker model for the second pass | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `retrieval.rerank_model` |
| R8 | Candidate count handed to the reranker | `50` | `retrieval.candidate_k` |
| R9 | Chunk count returned to the agent | `5` | `retrieval.top_n` |
| R10 | Chunks embedded per call while indexing. Batching keeps peak memory low on a large manual, and it carries the upload dialog's indexing progress (U3). | `64` | `retrieval.embed_batch_size` |

R3 keeps R1 for production.
R1 names Qdrant Cloud in us-east-1.
The local service is a development choice, so an ingest run and a query need no network and no credentials.

Source: https://qdrant.tech/documentation/ and
https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-dot-v1 and
https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2
Last-checked: 2026-10-15

## Agent graph and answer contract

| ID | Decision | Value | Configuration key |
|---|---|---|---|
| A1 | The graph is a supervisor, worker, and synthesize topology. The supervisor routes between the retrieval worker and synthesis, capped by a hop limit. The worker runs the tool loop. `synthesize` writes the answer. | see IMPLEMENTATION §2.3 | `agent.max_hops`, `agent.max_tool_steps` |
| A2 | The agent answers in markdown text with `[Page N]` citations. Each citation names its manual: `[Page N] (manual <manual_id>)`, so a click opens the right manual. The structured `AgentAnswer` is future work (see the Deferred section). | (none) | (none) |
| A3 | The system prompt carries the grounding rules: every claim and step names its page, the answer states plainly when the manual holds no answer, and conflicting values show both pages. The prompt text lives in the configuration (field `agent_system_prompt`, env `AGENT_SYSTEM_PROMPT`), and the graph prepends it before the first chat call. | (none) | `agent.system_prompt` |

The graph runs as a supervisor, a retrieval worker, and a synthesize node.
The supervisor plans and decides when to stop; the worker gathers manual evidence with the calculator and the three RAG tools; `synthesize` writes the final answer.
The routing check in the supervisor and the tool loop in the worker run on the tier's working model and effort.
`Synthesize` writes the answer on the tier's authoring model and effort, so the expensive model is spent only on the answer (M1).
`/chat` returns markdown text with `[Page N] (manual <manual_id>)` citations.
The structured `AgentAnswer` and the confidence gate are future work (see the Deferred section).

## Automated evals

| ID | Decision | Default | Configuration key |
|---|---|---|---|
| E1 | The eval scores the 16-question accuracy set with an LLM judge. The judge model stays distinct from the model under test, so self-preference bias stays low: the run drives the agent with Flash, so Pro judges. | `~deepseek/deepseek-pro-latest` | `eval.judge_model` |
| E2 | The reasoning effort for the judge call. | `high` | `eval.judge_reasoning_effort` |
| E3 | A case passes at or above this score when the judge omits an explicit `passed`. | `0.7` | `eval.pass_threshold` |
| E4 | The CI gate on the overall pass rate. | `0.8` | `eval.min_pass_rate` |
| E5 | The CI gate on citation precision. Task 7 asks for more than `0.9`. | `0.9` | `eval.citation_precision_min` |
| E6 | The vehicle that owns the eval manual. The run supplies it, because the vehicle id is generated when the manual is uploaded. | from the environment | `eval.vehicle_id` |

The set has three categories, and each category has one rubric.
A `spec` answer scores against the gold value, with the correct unit and qualifier (model range, U.S. versus non-U.S., torque units).
A `procedure` answer scores against the gold steps in substance and order, with every key number correct.
An `out-of-scope` question has no answer in the manual: a pass says so and invents nothing, and a fluent invention scores `0`.

The gold `expected` text and the `answer_pages` list are the authoritative reference, and the judge prompt tells the judge to trust them over the agent.
The judge writes its reason before its score, and it returns one JSON object, so the run aggregates without reading prose.
Citation precision is computed in code, not by the judge: the `[Page N]` set is exact, so a count beats a model.

The agent answers in markdown text (A2), so the judge reads that text directly and no structured answer is added.
The judge shares no model with the agent in the default run.
A judge from another vendor would add independence; it stays a later improvement.
OpenRouter reports `high` for both DeepSeek slugs, so the judge effort needs no fallback (M1).

Source: https://openrouter.ai/api/v1/models
Last-checked: 2026-10-19

## Testing and continuous integration

| ID | Decision | Value |
|---|---|---|
| T1 | Unit tests inject a fake embedder, so no test downloads a model | (none) |
| T2 | The end-to-end retrieval test carries a pytest marker and stays out of the default run | `@pytest.mark.heavy` |
| T3 | The default CI run stays cheap: dependency install, the syntax check, and the marked test excluded | (none) |
| T4 | The eval runner is a live-LLM run, so it stays out of the default cheap CI, the same way the marked heavy test does. It needs `OPENROUTER_API_KEY` and an ingested manual, and it runs by hand with `python -m backend.eval.run`. | (none) |

Docling, torch, and sentence-transformers make a full install slow and large.
T1 and T2 keep the default check fast.
Tests run against mocks, not the full model set, even though the project prefers end-to-end tests.
Some behavior needs a mock to stay testable without a download.
T4 keeps the default run offline: the eval calls OpenRouter and reads an indexed manual, so it needs a key and a live index.

## Manual Viewer

| Item | Decision |
|---|---|
| V1 | The Manual Viewer is a dedicated mode. A UI toggle opens the page set the agent deemed relevant: the top-scored `search_manual` chunk page set, gated by a rerank-score threshold. The set renders in a pane beside the chat with `react-pdf` in four-page slices (one page before the cited page, two after). The window sizes are the `NEXT_PUBLIC_VIEWER_SLICE_BEFORE` and `NEXT_PUBLIC_VIEWER_SLICE_AFTER` configuration values. The pane opens at the cited page, so the pages held before it scroll out of view. A citation carries its manual id, so the pane opens the manual the citation came from, not the last manual the reader opened. (See SPECIFICATION §2.1 and IMPLEMENTATION Tasks 2 and 6.) |
| V2 | The pane can open the whole PDF of a manual on demand, so the reader can read the full manual in the app. A `View whole manual` button in the pane fetches `GET /manuals/{id}/pdf`, which streams the stored `source.pdf`. The button carries the tooltip `Whole manual may be slow to load`. The pages mount lazily as the reader scrolls, so a large manual stays responsive. |
| V3 | The pane carries zoom controls over the pages. One click steps the zoom by `NEXT_PUBLIC_VIEWER_ZOOM_STEP` (default `0.25`), inside the range from `NEXT_PUBLIC_VIEWER_ZOOM_MIN` (`0.5`) to `NEXT_PUBLIC_VIEWER_ZOOM_MAX` (`3`). A zoom of `1` fits a page to the pane width. A click on the shown percentage resets the zoom to `1`. |
| V4 | The reader sets the chat and pane split by dragging the left edge of the pane, or with the arrow keys on that edge. While the chat shows, the pane stays between `NEXT_PUBLIC_VIEWER_WIDTH_MIN` (`280`) and `NEXT_PUBLIC_VIEWER_WIDTH_MAX` (`900`) pixels and leaves the chat at least `NEXT_PUBLIC_CHAT_MIN_WIDTH` (`360`). Dragging past that point hides the chat, so the pane fills the row beside the thread sidebar. A short pull right of `NEXT_PUBLIC_CHAT_RESTORE_TRAVEL` (`24`) pixels brings the chat back at the width it last had. Closing the pane brings the chat back too. The width survives reloads in `localStorage`, and the pane opens with the chat showing. |
| V5 | The stored page bytes never change after upload (U1). The page-slice and whole-manual endpoints answer with `Cache-Control: public, max-age=<VIEWER_CACHE_MAX_AGE_SECONDS>, immutable` (default `31536000`) and an `ETag`. A request whose `If-None-Match` matches returns `304`. The slice `ETag` comes from the stored PDF and the page range, not from the slice bytes, because PyMuPDF stamps a fresh document id into every re-serialization. |
| V6 | The viewer caches PDF bytes, never rendered pages. Page slices live in a module-level `Map` keyed by manual id and page range, capped at `NEXT_PUBLIC_VIEWER_SLICE_CACHE_ENTRIES` (`12`) entries with the least recently used entry dropped first. The map clears on a reload or a tab close, not when the reader switches threads or pane modes. A whole manual is cached once per manual in the Cache API under `manualchat-manual-pdf`. Both caches hold Blobs, which react-pdf can read more than once, unlike the ArrayBuffer that pdfjs detaches. Deleting a manual drops its cached bytes. |

## Frontend appearance

| Item | Decision |
|---|---|
| C1 | The UI has a light theme and a dark theme. The first visit follows the operating system's colour scheme. After the visitor chooses, the choice is stored in `localStorage` and wins on later visits. The theme is applied before the first paint, so the page never flashes the wrong theme. |
| C2 | A top bar carries the vehicle selector, the upload button, the viewer toggle, the model selector, and the theme toggle, over a thin red rule. The manual viewer opens as a right-hand pane beside the chat. The wrench-in-bubble logo (`frontend/assets/manualchat-logo.svg`) replaces the ManualChat wordmark at the top of the thread list. |
| C3 | The upload dialog shows how far an ingest has come. The bar is determinate over the units of the current stage, and it moves for a stage with nothing to count. The estimate beside the bar comes from the rate the run has kept. The same manual can take a minute or an hour, so a fixed guess is wrong in one case or the other. The form and the Upload button stay locked while a manual uploads or ingests. A manual list row shows its own percent, for example `Processing 29%`. The dialog polls the manual record on its own, so the progress panel returns when the reader reopens the dialog. While the dialog is closed, a toast below the top bar reports the upload and opens the dialog again on a click. It sits below the top bar, because the chat composer and the viewer pane hold the bottom corners of the window. |

## Dev tooling

| ID | Decision |
|---|---|
| W1 | The development assistant is the built-in VS Code Copilot Chat with OpenRouter Maestro as the language-provider extension. Any OpenRouter model then appears in the chat model picker. The chat model in use is `deepseek/deepseek-v4-pro-0813` (DeepSeek V4 Pro 0813). The API key lives in VS Code SecretStorage, not in the repository. |
| W2 | Agent customization lives in Copilot formats. The agent files sit in the workspace `.github/` folder one level above the repo: `copilot-instructions.md`, `instructions/*.instructions.md` with targeted `applyTo` scopes, and `skills/{simple-english,open-pr}/SKILL.md`. `AGENTS.md` stays tracked in the repo. `.github/workflows/ci.yml` and `.github/PULL_REQUEST_TEMPLATE.md` stay tracked in the repo too, because GitHub reads them from the repository. The workspace agent files are local only and are tracked by no repository. The `applyTo` globs are relative to the workspace root, so they read `**/backend/**` and `**/frontend/**`. GitHub Copilot code review reads `.github/copilot-instructions.md` only from the repository root, so it does not read the workspace-level file. |

Source: https://code.visualstudio.com/docs/agent-customization/custom-instructions and
https://marketplace.visualstudio.com/items?itemName=husamettinulutas.openrouter-maestro
Last-checked: 2026-10-13

## Monitoring (observability)

| ID | Decision | Default | Configuration key |
|---|---|---|---|
| O1 | LangSmith traces every OpenRouter model call (MVP+1). Each run has type `llm` and records the model slug, token usage (`prompt_tokens`, `completion_tokens`, `total_tokens`), wall-clock latency from its start and end times, and any error. A failed post is swallowed, so an unreachable LangSmith never breaks the chat. Tracing turns on only while `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are both set. | off | `langsmith_tracing` (bool), `langsmith_api_key` (secret), `langsmith_project` (`manualchat`), `langsmith_endpoint` (`https://api.smith.langchain.com`) |

The trace layer (`backend/tracing.py`) is decoupled from the wrapper. `backend/llm.py` records one run per call and never lets recording fail the call.
Token usage comes from the OpenRouter `usage` object; the stream path reads it from the final usage chunk.

Source: https://docs.smith.langchain.com/ and https://openrouter.ai/docs/api-reference/streaming
Last-checked: 2026-10-20

## Deferred and undecided

- The OCR-engine head-to-head is deferred with the whole scanned and FJ40 path (S1).
- The normalization rules catalog: the existence of the stage is decided (D3).
The exact unit and header repair rules (`lb` and `Ib`, `m· kg`, `SPECiFiCATIONS`, diagram-symbol junk) become test fixtures when the stage is built.
- The structured `AgentAnswer` and the confidence gate: the graph answers in markdown text.
- The spec ledger: the POC returns table values without writing a ledger.
- The scanned-manual rejection probe: not built for the POC. The prototype manual `pl.pdf` is digital, so no scanned manual is expected.
- The manual viewer rerank threshold: the value that opens the viewer page set.
- Docker work: the Qdrant service in `docker-compose.yml` and the baked ingestion models.
- GPU acceleration: deferred to MVP+1 with the scanned-manual path (S1). The Docker image ships CPU-only torch (D14). A GPU host in play reopens it.
