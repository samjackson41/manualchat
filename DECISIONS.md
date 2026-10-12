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

D1–D3 apply defensively to the Rhino + Johnson manuals (the Rhino was produced through an
Acrobat "Paper Capture" pipeline, so it may carry the ghost OCR layer — sanitize-at-source
is harmless either way).

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
> OpenRouter slugs (pinned in config, not code):
> - DeepSeek Pro → `deepseek/deepseek-pro-latest`
> - DeepSeek Flash → `deepseek/deepseek-flash-latest`
>
> Reasoning: both models run with **medium** reasoning effort for now
> (`models.reasoning_effort = "medium"`).

---

## Cloud region

| Item | Decision |
|---|---|
| R1 | Region = **us-east-1** (closest). GCP `us-east1` for Cloud Run/GCS; Qdrant Cloud in us-east-1. |
| R2 | Redis stays on its existing **AWS us-east-1** Essentials tier — accept the cross-cloud hop; revisit only if latency shows up in eval. |

---

## Manual upload idempotency

| Item | Decision |
|---|---|
| U1 | **MVP**: assume a smart single-user — each manual is uploaded/processed **once** and must **remain in storage** (GCS) so the processed result is never re-derived. No dedup check. |
| U2 | **MVP+1**: add a **file-hash check** (against stored manual hashes) and surface a **warning** to the user on a suspected re-upload. |

---

## Spec ledger storage

| Item | Decision |
|---|---|
| L1 | The spec ledger lives in **Qdrant** and is **populated lazily** — only when the agent retrieves a table that answers a spec question. Values are parsed **verbatim from the source table** (never from model prose output) and upserted keyed by `(vehicle_id, manual_id, subject)`. No full-manual preprocessing at ingest. |
| L2 | **MVP scope = table-derived specs only.** A value buried in prose is answered with citation grounding, not written into the ledger. |
| L3 | Revisit Postgres **only if** post-MVP multi-manual conflict attribution requires relational joins across manuals. |

---

## Manual Viewer (PDF pane)

| Item | Decision |
|---|---|
| V1 | A dedicated **Manual Viewer** mode — a UI toggle that opens a full-width PDF view of the pages the agent deemed relevant (the top-scored `search_manual` chunk page-set, gated by a rerank-score threshold), rendered with `react-pdf` in `[Page−2, Page+2]` 5-page slices. (See SPECIFICATION §2.1 and IMPLEMENTATION Tasks 2/6.) |

---

## Dev tooling (coding assistant)

| # | Decision | Notes |
|---|---|---|
| W1 | The development assistant is the built-in VS Code Copilot Chat with **OpenRouter Maestro** as the language-provider extension (any OpenRouter model appears in the chat model picker). Cline is retired. | Chat model in use: `deepseek/deepseek-v4-pro-0813` (DeepSeek V4 Pro 0813). The API key lives in VS Code SecretStorage, not in the repo. |
| W2 | Agent customization lives in Copilot formats: `AGENTS.md` (project, tracked), `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` (targeted, `applyTo` scopes), and `.github/skills/{simple-english,open-pr}/SKILL.md`. The `.github/` agent files are local only and git-ignored, like the old `.clinerules`. `AGENTS.md`, `.github/workflows/ci.yml`, and `.github/PULL_REQUEST_TEMPLATE.md` stay tracked. | Changed on 2026-10-12: the `.github/` agent files moved to local-only, so GitHub Copilot code review can no longer read `.github/copilot-instructions.md`. The old `.clinerules/` and `~/.cline/skills/` copies were removed on 2026-10-12. The `pr-description` skill was replaced by `open-pr`, which opens the PR with the `gh` CLI. |

Source: https://code.visualstudio.com/docs/agent-customization/custom-instructions and
https://marketplace.visualstudio.com/items?itemName=husamettinulutas.openrouter-maestro
Last-checked: 2026-10-12

---

## Deferred / undecided (no decision now — revisit later)

- **OCR-engine head-to-head** — deferred with the whole scanned/FJ40 path (S1).
- **Normalization rules catalog** — the *existence* of the stage is decided (D3); the
  exact unit/header repair rules (`lb`/`Ib`, `m· kg`, `SPECiFiCATIONS`, diagram-symbol
  junk) should be enumerated as test fixtures when the stage is built.