# DECISIONS — ManualChat (decision log)

> Living log of ratified decisions. Companion to `project_proposal.md`,
> `SPIKE_FINDINGS.md`, and `MEMORY_DESIGN.md`. Each entry states the decision,
> the governing default, and (where the value is arbitrary/tunable) the config key
> that surfaces it.

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
| S3 | **Dev/test manuals**: two new manuals for another vehicle, both with a PDF text layer and fewer diagrams than the FJ40. (These replace the FJ40 as the working set.) |
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

D1–D3 apply defensively to the two digital manuals (they may or may not carry the ghost
OCR layer the Rhino manual had — sanitize-at-source is harmless either way).

---

## Model tiering (cheap-first)

| Role | Model | Config key |
|---|---|---|
| planning / internal steps | DeepSeek **Flash** | `models.planning` |
| synthesis / final answer | DeepSeek **Pro** | `models.synthesis` |
| summarization (compaction) | DeepSeek Flash (cheap bucket) | `models.summarizer` |
| eval judge (LangSmith) | DeepSeek Pro (or Flash to start) | `models.judge` |

> Exact OpenRouter slugs get pinned in config (not the code) and should be confirmed at
> implementation time — "Flash"/"Pro" are the *tiers*; the concrete model IDs live under
> the keys above.

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

## Deferred / undecided (no decision now — revisit later)

- **Spec-ledger storage (item C)** — undecided. Options on the table: Qdrant metadata
  payloads (fastest to MVP), Postgres (clean relational fit), Redis (already in scope).
  Revisit before implementing `MEMORY_DESIGN.md` §3's ledger.
- **OCR-engine head-to-head** — deferred with the whole scanned/FJ40 path (S1).
- **Normalization rules catalog** — the *existence* of the stage is decided (D3); the
  exact unit/header repair rules (`lb`/`Ib`, `m· kg`, `SPECiFiCATIONS`, diagram-symbol
  junk) should be enumerated as test fixtures when the stage is built.