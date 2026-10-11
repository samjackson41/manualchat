# Project Brainstorming — Repair Manual RAG Agent ("ManualChat")

Working notes for the Week 6–8 capstone. This file is the running record of the idea,
the architecture decisions, and the open questions — updated as the plan evolves. See
[`README.md`](README.md) for the capstone spec/assessment and [`ideas.md`](ideas.md) for
the inspiration list this idea grew out of (closest fit: "Support agent over docs" +
"Contract / lease analyzer" — RAG + tool actions + confidence gate + clause/page citations).

## 1. The idea

A system that ingests a **repair manual PDF** (any vehicle, motor, or machine — not
hardcoded to one), and answers natural-language questions with:
- a synthesized, step-by-step repair procedure,
- **page citations** for every claim (falsifiable — a real eval target),
- structured specs (torque values, fluid capacities, part numbers) pulled out of the text,
- and support for **multiple vehicles, each with multiple manuals** (e.g. an OEM
  maintenance manual and an aftermarket repair manual for the same car), with sessions
  scoped to one vehicle at a time — see §4.

Explicitly **not** a "PDF chatbot" — the win condition is a real **tool-calling agent
loop** (plan → retrieve → extract → synthesize), not a single RAG hop that pastes chunks
into a prompt.

## 2. Feasibility research — decision log

### 2.1 Is this too simple for the capstone bar?
**Conclusion: no, provided it's tool-driven, not a single RAG hop.**

The project README's explicit warning: *"A thin 'PDF chatbot' with no actions and no
evals."* The line between "thin" and "capstone-grade" is not about diagrams or polish —
it's whether the model **calls tools in a loop to do work** vs. just retrieving text and
restating it.

```
❌ THIN (Session 02 level — one RAG hop):
   User: "how do I change my oil?"
   System: [retrieve chunks] → "Here's what the manual says..."

✅ AGENTIC (capstone level — plan, multi-tool, structured extraction):
   User: "how do I change my oil on a 2023 Civic?"
   Agent loop:
     1. search_manual("oil change procedure") → pages 47-52
     2. extract_specs("oil type", "capacity", "filter part number") → structured lookup
     3. Plan: drain → replace filter → refill → check level
     4. Synthesize numbered steps, each with its own page citation
     5. Return: procedure + specs table + confidence + citations
```

### 2.2 Diagram/vision processing — deliberately deferred, not required
Scoped OUT of MVP. Rationale: repair answers are ~95% textual; a diagram reference
("see Figure 4-2, page 47") plus a clickable image link is more trustworthy than an AI
description of a mechanical diagram (which risks hallucinating exact positions/parts).
Vision (Session 04 pattern — Qwen3-VL via OpenRouter, image_url content parts) is a
Phase 2 idea, used **on demand** only when a user explicitly asks about a specific
figure — never pre-computed at ingest time.

### 2.3 `docling` — the PDF ingestion bridge (already a course dependency!)
`docling>=2.52.0` is already in `pyproject.toml` ("document parsing for ingestion").
It parses PDFs (born-digital and scanned via OCR/EasyOCR), extracts tables, and reports
page-level structure — which is exactly what page-cited retrieval needs. **First spike
task**: confirm docling's output quality on a real repair manual before committing to
the ingestion architecture (scanned vs. digital text layer, table fidelity, page-number
preservation).

### 2.4 Existing cohort code this project reuses directly
| Piece | File | Reuse plan |
|---|---|---|
| Bi-encoder + cross-encoder retrieval | `project/retrieval/embeddings.py` | Reuse as-is (`multi-qa-mpnet-base-dot-v1` + `cross-encoder/ms-marco-MiniLM-L-6-v2`) |
| Qdrant ingest/upsert pattern | `project/retrieval/ingest.py` | Adapt: add `manual_id` + `page_number` to the payload |
| `search_kb` dual-backend pattern | `.../session-02/solution/retrieve.py` | Adapt into `search_manual(query, manual_id, top_n)` with a Qdrant filter |
| Grounded, cited answer pattern | `.../session-02/starter/grounded_agent.py` | Seed of the Q&A tool — context block + "answer ONLY from context, cite [source]" |
| Multi-provider LLM client | `shared/llm/client.py`, `shared/llm/tools.py` | Reuse `chat()` + `run_tool_loop()` as-is — provider-agnostic already |
| Vision extraction pattern (Phase 2 only) | `.../session-04/starter/extract_structured.py` | Reuse the image_url + Pydantic-repair pattern for on-demand diagram description |
| Typed tools + MCP server pattern | `.../session-03/.../mcp_server.py`, `tool_calling_agent.py` | Template for `search_manual`/`extract_specs` as an MCP server, and the agent as an MCP client |
| RedisSaver checkpointer factory | `project/memory/checkpointer.py` | Reuse verbatim (`make_checkpointer()` — swaps InMemorySaver ↔ RedisSaver by config) |
| RBAC pattern (deny-by-default) | `project/security/rbac.py` | Template for the post-MVP multi-user roles (see §5) |
| LLM-as-judge pattern | `project/eval/judge.py`, `project/eval/run.py` | Template for a repair-manual rubric (citation accuracy, spec accuracy, hallucination) |
| Cloud Run deploy runbook | `project/deploy/README.md` | Template for GCP deploy (adjusted: no BigQuery needed, see §3) |

## 3. Tech stack — mapped against "use as many course tools as possible"

Goal stated by the user: portfolio depth over minimal footprint — touch as much of the
course stack as *legitimately* fits, without forcing a tool in where it hurts the
product. Decision per component:

| Course tool | Use it? | Where / why |
|---|---|---|
| **LangGraph** | ✅ Yes | The agent loop itself: a supervisor node plans, delegates to tool-calling nodes (`search_manual`, `extract_specs`, `generate_procedure`), then synthesizes. This is the Session 05 multi-agent pattern, directly reusable. |
| **Qdrant** | ✅ Yes | Vector store for manual chunks. One collection, `manual_id` as a payload filter (see §4) — not one collection per manual. |
| **Custom MCP server** | ❌ Skip for MVP (optional post-MVP) | See §3.1 — deprioritized after clarification: MCP ≠ "the agent knowing when to call tools" (that's native function calling); MCP is only for *external* client reuse, which this app-specific toolset doesn't need. |
| **GCP (Cloud Run)** | ✅ Yes (post-MVP; local-first until then) | Deploy the FastAPI service eventually. Per §6 Q8, run local/private first — no public URL until auth + spend caps exist. Free-trial credits cover this comfortably (no BigQuery-scale spend). |
| **OpenRouter + model picker** | ✅ Yes (model picker now; BYOK only when shared) | OpenRouter is already the multi-provider gateway in `shared/llm`. Model selection is a cheap, useful in-app setting from day one (§3.2); BYOK (user-supplied key) is **not needed until the app is shared beyond the owner** (§6 Q4/Q8) — deprioritize it. |
| **BigQuery** | ❌ Skip | See §3.3 — no structured/warehouse data in this domain; forcing it in would be the "using a tool because it's in the syllabus" anti-pattern. |
| **Redis** | ✅ Yes | LangGraph checkpointer for active conversation thread persistence (`project/memory/checkpointer.py` reused verbatim). |
| **LangSmith (LLM judge)** | ✅ Yes | Tracing + an eval dataset + a custom LLM-as-judge evaluator (see §3.4) — this is the most under-invested area per teams historically, and the most gradeable. |
| **Next.js (React)** | ✅ Yes (updated) | Frontend, replacing Streamlit — **Next.js**, not plain React/Vite, specifically for its zero-config Vercel pairing (Next.js is built/maintained by Vercel) and file-based API routes. See §3.5. |
| **sentence-transformers (bi/cross-encoder)** | ✅ Yes | Already required by Qdrant retrieval; free, local, no extra service. |
| **Docling** | ✅ Yes | PDF → text/tables/pages ingestion bridge (§2.3). |

### 3.1 Custom MCP server — clarified, and deprioritized for MVP

**Correction to the earlier framing (and to a common misconception):** MCP is **not**
what makes the agent "know when to call its tools." That's **native function/tool
calling** — the LLM provider's own function-calling API, which LangGraph binds to
directly (`shared.llm.run_tool_loop` does exactly this). The agent deciding "call
`search_manual`, then `extract_specs`, then synthesize" works with zero MCP involved.

MCP's actual job is narrower: a **transport/discovery standard** so a tool can be
written once and reused by *multiple different clients* (Claude Desktop, an IDE, another
app) that didn't import your code. "Is MCP worth it" therefore really means "will
anything besides this one app ever call my repair tools?"

**Given the answer is no** — the tools are explicitly app-specific (`search_manual`,
`extract_specs`, `list_manuals`), and the only consumer is this app's own LangGraph agent
— **skip MCP for MVP.** Native tool calling is simpler (one less process, one less
moving part) and still gives the portfolio the full agentics story. Revisit MCP *only*
if a "point Claude Desktop at my repair tool server" demo becomes desirable later — it's
a thin wrapper over tools whose contracts are already stable, so it's cheap to add
post-MVP and safe to defer now.

### 3.2 OpenRouter — model picker now, BYOK later

Two separate things, previously bundled; split them per §6 Q4/Q8:

- **Model picker (build now, it's cheap and useful)** — a `model` selector in the UI
  covering OpenRouter's many models, mapping straight onto the existing
  `"<provider>:<model>"` string convention already used by `LLMClient`. With a
  single-user MVP this just lets *you* switch between a cheap agent model and a stronger
  judge/eval model without editing `.env`.
- **BYOK (defer until the app is shared)** — letting a visitor supply their own
  OpenRouter key (an `api_key` override on `shared/llm`, or an `X-OpenRouter-Key` header
  at the API layer) only matters once other people use the app and you don't want to eat
  their inference cost. Single-user + "couple friends with a shared token" (§6 Q9) makes
  this a post-MVP concern, not a MVP one. It's not hard to add later — an optional
  `api_key` param is a small, isolated change to `shared/llm/client.py` — so deprioritize
  it without losing it.

### 3.3 BigQuery — explicit decision to skip
User asked: "not sure what kind of data we'll be using besides the RAG'd repair manual."
Answer: **there isn't structured/tabular data in this problem domain** the way Loom &
Co. has an orders/customers warehouse. Forcing BigQuery in would mean inventing a fake
structured dataset just to check a box — that's the anti-pattern the course explicitly
warns against ("using the right model/tool for the task" is criterion #1). If a
genuinely structured need shows up later (e.g., a maintenance-schedule-by-mileage table,
or a parts-catalog-with-prices table), BigQuery or even just SQLite would be the natural
fit — revisit then, don't force it now.

### 3.4 LangSmith judge — concrete plan
Following `project/eval/judge.py` + `project/eval/run.py`:
- Build an `EvalCase` dataset (30+ entries) across ≥2 different manuals, each with:
  `question`, `manual_id`, `expected_pages`, `expected_specs` (structured), and
  `criteria` text.
- Categories mirroring the existing rubric shape (`factual`, `citation`,
  `hallucination`) — reuse the "reason-then-score" judge pattern, structured
  `Judgement(score, passed, reason)` output.
- New rubric axis specific to this domain: **citation precision** — does the cited page
  actually contain the claim? This is stronger/more falsifiable than the Loom rubric
  because page numbers are ground truth, not judgment calls.
- Wire LangSmith tracing (`LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true` — same env vars
  already in `project/config.py`) so every agent run is traced, and push the eval
  dataset + judge as a LangSmith **experiment** (confirmed via LangSmith docs: `Client`
  + `evaluate()` support custom evaluator functions and produce a dashboard-viewable
  experiment — this is a legitimate, visible portfolio artifact, not just console output).

### 3.5 Frontend stack — Next.js + Tailwind + shadcn/ui, hosted on Vercel

**Decision (updated from "React" to specifically Next.js), driven by two explicit asks:
Vercel hosting + phone-browser reactivity.**

Every other cohort artifact uses Streamlit; this is a deliberate step up in effort, but
narrower than "plain React from scratch":
- **Next.js, not plain React/Vite** — Next.js is built and maintained by *Vercel itself*,
  so deploying it there is genuinely zero-config (`git push` → live, automatic PR preview
  URLs, global edge distribution, built-in image optimization). Plain React deploys to
  Vercel fine too, but without that same native pairing. All existing React knowledge
  transfers directly — components/hooks/JSX are identical; the only new concepts are
  file-based routing (`app/page.tsx` = `/`) and *optional* server-side data fetching
  (can be ignored entirely and built as a plain client-rendered SPA).
- **Tailwind CSS + shadcn/ui for responsiveness** — shadcn/ui is a component library
  built on Tailwind + Radix UI primitives (also from the Vercel/shadcn team, so it's the
  "native" component layer for this stack). It directly covers the requested UI: a
  `Sheet` (slide-out drawer) or `Collapsible` component for session history, `Select`/
  `Input`/`Dialog` for the OpenRouter config panel, and Tailwind's responsive utility
  classes (`flex md:flex-row flex-col`) make "sidebar becomes a bottom sheet on mobile"
  a few classes, not hand-written media queries. This is also the stack current AI
  coding agents (v0, Claude, Cursor) scaffold best — relevant since the plan is to
  scaffold the UI with an AI agent per the capstone README's explicit encouragement.
- **`react-pdf`** for the PDF viewer panel — mature, touch/pinch-zoom works out of the
  box on mobile (unlike the Streamlit `streamlit-pdf-viewer` component, which has
  documented rerun/version-compatibility caveats). See §4.7 for why this is loaded as a
  *segment*, not the whole document.
- **Mobile reactivity is genuinely a CSS/component-library concern, not a framework
  choice** — Next.js vs. plain React doesn't affect it; Tailwind + shadcn/ui does the
  actual work. Worth setting expectations honestly: the chat panel will feel great on
  phone; a dense repair-manual page (small text, tight diagrams) will be *usable* but
  cramped no matter how good the viewer component is — call this out as a known
  trade-off in the capstone pitch rather than over-engineering around it.
- **Hosting**: Vercel free tier for the Next.js frontend (static/edge, no cold start, no
  "public apps only" constraint the way Streamlit Community Cloud has); Cloud Run for
  the FastAPI backend, unchanged. Two decoupled, both-free-tier services talking over
  HTTPS — cleaner than bundling a UI process into the same container as the API.
  **Sequencing caveat (§6 Q8): local-first.** The user runs this solo/private until after
  Week 8 and does not want a public URL before auth + spend caps exist — so Vercel/Cloud
  Run are the eventual targets, not the Week 8 demo requirement. Everything in the MVP
  must run cleanly against localhost + a private Qdrant/Redis first.
- Mitigation for the added frontend effort: keep the **API** the graded surface (per the
  capstone rubric — "the caller of an API is a customer too"), treat the Next.js app as
  a thin client over it, and lean on an AI coding agent for the boilerplate so the saved
  time goes to the agent/API instead.
- Decide the FastAPI CORS story early (Vercel and Cloud Run are different origins) and
  whether the chat UI should stream tokens — the existing `project/api/main.py` already
  has a `/chat/stream` SSE precedent to mirror on the Next.js side (`EventSource` or a
  streaming `fetch` reader).

## 4. Multi-vehicle, multi-manual architecture (updated — the real target shape)

**Updated requirement (supersedes the flat "multiple manuals" framing above):** the
hierarchy is **user → vehicles → manuals**, not a flat list of manuals. A user has N
vehicles (each custom-named at creation, e.g. "My 2023 Civic" or "Garage RAV4"); each
vehicle has N manuals (e.g. the OEM maintenance manual *and* a Haynes aftermarket repair
manual for the *same* car). A session is always scoped to **one vehicle**, and the agent
searches across (or lets the user pick among) that vehicle's manuals for citations and
diagram retrieval — never across vehicles.

This is an early **post-MVP improvement**, not MVP day-one — MVP still targets a single
vehicle/manual to prove the agent loop, per the original scoping decision. But the data
model should be designed for this shape from the start so it isn't a rewrite later (see
§4.4).

### 4.1 The three-level hierarchy

```
User (account)
 └── Vehicle  ("My 2023 Civic")            <- dropdown selector, custom name at creation
      ├── Manual  ("OEM Maintenance Manual")     <- renameable, defaults to filename
      │    └── chunks (Qdrant, page-cited)
      └── Manual  ("Haynes Aftermarket Guide")
           └── chunks (Qdrant, page-cited)
 └── Vehicle  ("Garage RAV4")
      └── Manual  ("2024 RAV4 Owner's Manual")
           └── chunks (Qdrant, page-cited)
```

UX implication: the **vehicle dropdown** is the top-level session selector (switching it
re-scopes the whole session — new agent context, new manual set). Under/alongside it,
a **visual list of that vehicle's manuals** (card or chip per manual, named after the
uploaded file but user-renameable) shows what's actually searchable right now, and lets
the user add another manual to the same vehicle without creating a new vehicle.

### 4.2 Data model

```python
class Vehicle(BaseModel):
    vehicle_id: str          # slug or uuid
    user_id: str             # NEW — owner, once accounts exist (see §4.4/§5)
    display_name: str        # "My 2023 Civic" — user-supplied at creation
    created_at: datetime

class Manual(BaseModel):
    manual_id: str
    vehicle_id: str          # NEW — which vehicle this manual belongs to
    display_name: str        # defaults to filename, user-renameable
    source_filename: str     # original upload name, kept even after rename
    kind: Literal["oem", "aftermarket", "other"] = "other"  # optional light tagging
    status: Literal["processing", "ready", "error"]
    page_count: int = 0
    chunk_count: int = 0
    created_at: datetime

class Chunk(BaseModel):
    text: str
    source: str          # filename, for display
    vehicle_id: str       # NEW — top-level scope
    manual_id: str        # scopes retrieval within a vehicle
    page_number: int      # for citations
    score: float = 0.0
```

`vehicle_id` on `Chunk` is slightly redundant with `manual_id` → `vehicle_id` (a join),
but keeping it denormalized on the Qdrant payload directly means a single-field filter
(`vehicle_id == X`) is enough to search **all manuals for one vehicle at once** —
important for the default "just ask about my car" query, where the user shouldn't have
to pick a specific manual first. `manual_id` stays available for when the user (or the
agent) wants to scope to one specific manual, or to cite which manual a page number
came from (a citation needs both — "OEM Manual, page 47" vs. "Haynes Guide, page 47" are
different pages in different documents).

### 4.3 Retrieval — vehicle-scoped by default, manual-scoped on demand

```python
def search_vehicle(query: str, vehicle_id: str, manual_id: str | None = None, top_n=5):
    """Default: search every manual belonging to this vehicle.
    manual_id, if given, narrows to one manual (e.g. user picked a specific manual chip,
    or the agent is disambiguating between conflicting OEM vs. aftermarket guidance)."""
    filter_ = {"must": [{"key": "vehicle_id", "match": {"value": vehicle_id}}]}
    if manual_id:
        filter_["must"].append({"key": "manual_id", "match": {"value": manual_id}})
    # ... embed query, Qdrant query_points(query_filter=filter_), rerank ...
```

One Qdrant collection total, not one per vehicle or manual — same rationale as before
(zero setup cost per new vehicle/manual, and cross-vehicle comparison stays possible if
ever wanted, e.g. "compare the oil change procedure for the Civic vs. the RAV4").

A citation-worthy detail: when a vehicle has **two manuals that disagree** (OEM says
5W-20, aftermarket says 5W-30 for a modified engine), the agent should surface **both**,
attributed by manual name + page — not silently pick one. This is a good eval case for
§3.4 (`citation` / `hallucination` rubrics): a passing answer must attribute conflicting
specs to their correct source, not average or guess between them.

### 4.4 Storage for the account-scoped version (per the stated direction: GCP + Qdrant)

- **Qdrant** stays the vector store for chunks (as above) — `vehicle_id`/`manual_id`
  payload fields already carry the account-scoping once `user_id` exists upstream on
  `Vehicle`.
- **Vehicle/Manual metadata** (the `Vehicle`/`Manual` rows above — names, status, which
  user owns what) needs a small relational/document store *outside* Qdrant (Qdrant is a
  vector index, not a good fit for "list my vehicles" or "rename this manual" queries).
  Natural GCP-native fits, roughly in order of setup effort:
  - **Firestore** — serverless, no schema migrations, trivial from Cloud Run, generous
    free tier; a good fit for a small per-user document shape like this.
  - **Cloud SQL (Postgres)** — more traditional/relational, more setup (an instance to
    provision), better if the data model grows more relational joins later.
  - Given "whatever service makes the most sense (GCP and Qdrant probably)" — Firestore
    is the lower-effort recommendation for the account/vehicle/manual metadata layer,
    with Qdrant purely for the vector chunks. Revisit if a real relational need emerges.
- **Uploaded manual PDFs themselves** (the raw files, kept for diagram retrieval — see
  §2.2/§4.5) belong in **Cloud Storage (GCS)**, one bucket, keyed by `manual_id`, not in
  Qdrant or Firestore (both are wrong for large binary blobs).
- This full account-scoped storage layer is explicitly **post-MVP** (§5) — MVP can fake
  it with a single hardcoded vehicle/manual and no persistence beyond Qdrant, then grow
  into this shape without a rewrite because the `vehicle_id`/`manual_id` fields are
  already in the schema from day one.

### 4.5 Diagram retrieval note (ties back to §2.2)
Since diagrams are deferred but the user explicitly wants "point the agent to the
correct vectorstore **and manual file** for citations and diagram retrieval" once
accounts exist — this confirms the original PDF (or its extracted page images) needs to
be addressable by `manual_id` even in the text-only MVP scope, so the on-demand vision
lookup (§2.2) has a real file to fetch a page image from later. Practically: store the
source PDF in GCS at ingest time regardless of whether Phase 2 vision is built yet —
it's a cheap thing to do now that avoids a re-ingestion pass later.

### 4.6 Session-scoping implication for the agent
Every session (LangGraph checkpointer thread, per `project/memory/checkpointer.py`)
carries a `vehicle_id` in its state from the first turn — set when the user picks the
vehicle from the dropdown, never inferred from the conversation. The agent's
`search_manual`/`search_vehicle` tool calls always receive that `vehicle_id` as a bound
argument (not something the LLM chooses), so there's no risk of the model "deciding" to
search the wrong vehicle's manuals. This is the same least-privilege shape as
`project/security/rbac.py`'s "enforce access BEFORE the model, not by asking nicely" —
here the scope gate is the vehicle boundary rather than a role, but the principle (bind
the constraint outside the model, not inside a prompt) is identical, so it doubles as a
head start on the post-MVP RBAC pattern in §5.

### 4.7 PDF viewing at scale — segment loading, not whole-document rendering

**The problem, stated precisely:** repair manuals are diagram-heavy and often 300–800+
pages. Rendering (or even downloading) the *entire* PDF every time a user opens the
viewer is slow, memory-heavy on mobile, and pointless — a citation always points at a
specific page or a narrow page range, never "the whole book." The viewer should never
load more than the user is actually about to read.

**Decision: the PDF viewer always opens to a bounded segment, not the full document.**

- **Default segment**: cited page **± 2–3 pages** (covers a procedure that spans a
  page break, or a diagram on the facing page) or, if the ingestion pipeline captured
  section boundaries (a Table of Contents / heading structure — `docling` reports
  document structure, not just raw page text — see §2.3), the **enclosing section**
  instead of a fixed page window. Section-based is the better UX when available ("Ch.
  4: Engine — Oil System," pages 44–58) since it doesn't arbitrarily cut off
  mid-procedure; the fixed ±N window is the fallback when section boundaries aren't
  reliably detected.
- **How this is served, mechanically** — two options, and the second is strongly
  preferred:
  1. *Client slices a full PDF it already has* — simplest, but means downloading the
     whole file at least once; acceptable only if manuals stay small (see §6 Q7's
     page-count cap) and are cached client-side after first load.
  2. *Server pre-splits the PDF into per-page (or per-section) PDF/image assets at
     ingest time* and serves only the requested range — e.g. a `GET
     /manuals/{manual_id}/pages/47-52` endpoint that returns a small, already-sliced
     PDF (or a stitched image strip) covering just that range, generated once at
     ingest and cached in GCS (ties directly into §4.4/§4.5 — the manual's GCS
     entry becomes several small per-page assets instead of one large original,
     alongside the original for re-processing/vision use). **This is the
     recommended approach** — it means the client (especially on a phone, on
     cellular data) never fetches more than a handful of pages' worth of data, no
     matter how large the source manual is.
- **Rendering**: `react-pdf` (pdf.js under the hood) can either open a small pre-sliced
  PDF outright, or — if serving per-page raster images is simpler than PDF slicing —
  render a plain `<img>` per page in the segment, which is lighter-weight than a full
  pdf.js document context and trivially responsive/zoomable on mobile with standard
  CSS. Worth spiking both during the ingestion spike (§7) to see which docling/PDF
  library combination makes per-page slicing cheapest to produce at ingest time.
- **UX**: the viewer opens directly to the cited page (not page 1, ever), shows a small
  "page 47 of 312 — Chapter 4: Engine" context indicator so the user knows where they
  are in the whole document without having loaded the whole document, and offers an
  explicit "load more pages" / "next section" action rather than infinite-scrolling
  through hundreds of unfetched pages.
- **Diagram implication**: since diagrams are extracted at ingest time regardless (as
  images, for future on-demand vision use per §2.2/§4.5), the *same* extracted diagram
  images can be reused directly in the segment view — a diagram referenced in a
  citation can be shown inline in the chat/citation card immediately, without opening
  the full-page PDF viewer at all, which is both faster and often what the user
  actually wants ("show me the diagram," not "open the whole page").
- **This changes the ingestion pipeline's output contract slightly**: alongside
  `Chunk` (text, for retrieval), ingestion should also persist a **page index** — a
  cheap `{page_number: {section_title, image_asset_path, pdf_slice_path}}` map per
  manual — so the API can serve `GET /manuals/{id}/pages/{n}` and `GET
  /manuals/{id}/sections/{n}` without re-parsing the source PDF on every request. This
  is a small addition to the ingestion pipeline (§2.3/§2.4), not a redesign — worth
  building it in from the first ingestion spike rather than bolting it on later.

## 5. Explicitly deferred (post-MVP, not in scope now)

| Deferred feature | Why deferred | Do this instead in MVP |
|---|---|---|
| **User auth + per-user account storage** (vehicles, their manuals, session history, API keys stored per account — see §4) | Adds a whole account/session-management subsystem; the capstone rubric doesn't require login, and "don't reinvent the wheel" was the explicit instruction. Near-term need is only "share with a couple of friends," which is a much lower bar than real accounts. | MVP: no login, a single user-owned manual set, no persistence beyond Qdrant. **Post-MVP step 1** is a simple shared-token / allowlist gate on the FastAPI endpoint (mirrors the existing `secure_api.py` `X-API-Key` pattern from Session 11) to admit 2–3 trusted people — *not* full accounts yet. **When real per-user accounts ARE built** (the vehicle-dropdown UX in §4 depends on it), *then* outsource auth — Clerk / Auth0 / Supabase Auth — paired with **Firestore** for `Vehicle`/`Manual` metadata (§4.4), the auth provider's user id becoming `user_id` on `Vehicle`. See §6 Q9 — this is deliberately deferred, not forgotten. |
| **Multi-user roles (user vs. admin)** | The course already has a complete, directly-portable implementation. | Point to `project/security/rbac.py` when the time comes: `ROLE_POLICY: dict[role, set[allowed_sources]]`, `check_access`, deny-by-default. For this domain the "sources" become **vehicles/manuals** (a `user` may only query vehicles they own; an `admin` role can read/manage any vehicle for support purposes). Same shape as §4.6's vehicle-scoping gate — this is that pattern generalized from "always this one vehicle" to "any vehicle this role owns." |
| **Web search / forum / YouTube augmentation** (from earlier discussion) | Needs a paid search API or fragile scraping; violates the free-tier constraint the course explicitly warns about. | If added later: a confidence-gated tool the agent calls only when `search_manual` returns low-relevance results, clearly labeling `[ONLINE SOURCE]` vs `[MANUAL page N]` — never a default path. |
| **Pre-computed vision/diagram descriptions at ingest time** | Cost scales with page count; risk of confidently-wrong descriptions of mechanical diagrams. | On-demand only: user explicitly references a figure → fetch image + surrounding text → one Qwen3-VL call (Session 04 pattern). Note: extracting diagrams *as images* (no AI call) still happens at ingest time regardless — see §4.7 — only the AI *description* step is deferred. |
| **Mobile-responsive UI** (usable on a phone browser, not just desktop) | A real but bounded amount of extra frontend work (Tailwind breakpoints, touch-friendly PDF viewer, a collapsible-to-drawer sidebar) — worth sequencing after the core chat/agent loop works on desktop. | MVP: build with Tailwind + shadcn/ui from the start (§3.5) so responsive classes are the default, not retrofitted — but only *verify*/polish mobile layouts as an MVP+1 pass once the desktop flow is solid. The §4.7 segment-loading PDF design is what makes mobile viewing viable at all (a full multi-hundred-page PDF would be unusable on cellular data/phone memory regardless of CSS polish). |

## 6. Open questions — now resolved (answers folded in from the Q&A follow-up)

Every item below was answered in a follow-up and is recorded here with the resolution,
so the heading reflects that these are **closed** decisions now, not open questions. The
only genuinely still-open points are §6 Q6 (docling fidelity) and Q10 (PDF slicing),
both of which resolve *from the spike results* (§7), not from more discussion.

1. **Test manuals** — **Resolved.** Yes, 2 different vehicles on hand now, plus the
   ability to get more (including a second manual for one vehicle — satisfying the §4.3
   "conflicting specs" test need). The **MVP-focus manual is a digital-native one, ~503
   pages** (long, but see Q7 — length is not the concern it was originally framed as);
   the **stretch manual is scanned and diagram-heavy**, which is exactly the harder OCR
   case to validate against. Spike `docling` on the digital-native one first (fast, high
   confidence), then on the scanned one to learn the OCR story (§7).
2. ~~**Deployment target for the frontend**~~ — **Resolved**: Vercel, hosting a Next.js
   app (§3.5). Cloud Run continues to serve the FastAPI backend. Remaining detail: nail
   down the CORS allow-list (Vercel preview-deploy URLs are per-PR/dynamic, not one
   fixed origin) and how the frontend gets the backend's URL (env var at build time).
3. **Team size** — **Resolved: solo, with heavy AI-agent assistance.** No human
   parallelization to lean on, so sequencing matters more than it would on a 2–3 person
   team: the build order is strictly linear (spike ingestion → schemas → agent tools →
   API → frontend). The AI-agent assistance is best spent on the high-volume, well-trodden
   parts (Next.js + shadcn scaffolding, boilerplate, eval-case bookkeeping), reserving
   personal effort for the judgment calls (tool contracts, eval rubric, the conflicting-
   specs behavior). This also mean-reverts the "touch every course tool" breadth ambition:
   prioritize depth on the mandatory path (RAG + LangGraph + Qdrant + evals) over adding
   optional course tools that don't earn their keep.
4. **Model-cost posture** — **Resolved: cost is a non-issue for MVP because it's
   single-user (you, alone) until post-Week 8.** No BYOK pressure before the demo. Model
   selection default is **cheap endpoints via OpenRouter** — the user wants reasonably
   priced models like a DeepSeek-class chat model for the agent loop, reserving any
   stronger model only where it materially buys accuracy (e.g. the §3.4 judge, where one
   call per eval case is a tiny absolute cost). The `cost_meter()` in `shared.llm` is
   worth wiring up early anyway — it's free observability and becomes the guardrail if
   the app is ever shared (Q8).
5. **MCP server** — **Resolved: skipped for MVP** (§3.1 updated to match). The user's
   clarifying note ("MCP is just so the agent knows when to call the custom tools")
   actually describes **native function calling**, not MCP — the agent knowing *when* to
   call `search_manual`/`extract_specs` is LangGraph's built-in tool binding, with no MCP
   involved. MCP would only add value if some *external* client (Claude Desktop, another
   app) needed to discover/call the repair tools — and the tools are app-specific. So:
   native tool calling for MVP; MCP is a cheap, safe post-MVP add-on if ever wanted.
6. **Docling table AND section/TOC extraction fidelity** — **Resolved as "run the spike,
   then decide."** The user will run the docling proof-of-concept on the actual MVP
   manual(s) first and decide the `extract_specs` contract / §4.7 page-index output from
   real results, not ahead of time. The fallbacks stay on the table pending that:
   a second LLM pass over raw table text for specs, and falling back to the fixed ±N-page
   window (§4.7) if section/TOC detection is unreliable on the manual at hand.
   **Not an open decision to make now — it's a decision the spike feeds.**
7. **Manual size limits (~503-page MVP manual)** — **Resolved: no arbitrary page cap
   needed.** The user doesn't care about ingestion latency because each manual is
   ingested **once**, ideally ever. A 503-page digital-native PDF is fine as the MVP
   manual — it yields ~tens of thousands of chunks at most, which is trivial for Qdrant's
   free tier and only a slightly slow one-time embed+upsert. The earlier "cap at ~200
   pages" concern is dropped. What still matters (and is independent of page count):
   (a) ingestion must be **idempotent/resumable** so a long one-time ingest can be
   re-run without duplicating or corrupting chunks, and (b) the §4.7 segment-loading
   design already handles "hundreds of pages" by never sending the whole PDF to a client —
   that's where the size question actually mattered, and it's addressed there.
8. **Accounts vs. local-first priority** — **Resolved: accounts (and the vehicle-dropdown
   UX) land *after* Week 8.** The first post-MVP goal is simply being able to **run and
   use it locally** with confidence; the user explicitly does *not* want a public
   deployment yet, out of a real and correct concern that opening it to the internet
   would expose/spend their Qdrant and other resources (and a public endpoint invites
   strangers to burn the OpenRouter key). Consequence for the plan: **deployment is
   de-prioritized** — no Vercel/Cloud Run public URL is a Week 8 deliverable; "runs
   cleanly on localhost + private backends" is the bar. Public sharing (Q9) is the thing
   that eventually forces the auth + spend-cap work, and that's deliberately later.
9. **Auth provider pick** — **Resolved as "not worried about it yet" — defer entirely.**
   The only near-term need is sharing with **a couple of friends** after the Week 8 MVP
   (or MVP+1), which is a *much* lower bar than full multi-user accounts: a simple
   shared token / lightweight allowlist (or even just an API-key gate on the FastAPI
   endpoint, mirroring the existing `secure_api.py` `X-API-Key` pattern) is enough to
   let 2–3 trusted people in without the §4.4 Firestore + Clerk/Auth0/Supabase machinery.
   No provider decision needed now; revisit only when friend-sharing graduates to
   genuine per-user isolation (which pulls the §4 vehicle/account model and RBAC back in).
10. **PDF slicing implementation** (§4.7) — **Resolved as "fold into the docling spike."**
    The user confirmed this belongs in the same proof-of-concept as docling (§7), where
    both the PDF-slicing-vs-raster-image trade-off can be weighed with real data, not in
    the abstract. The pros/cons to resolve there: true PDF slicing (`pypdf`/`pikepdf`)
    preserves text-selection and vector crispness but is more pipeline work; raster
    page images (`PyMuPDF`/`pdf2image`) are simpler and friendlier on mobile but lose
    selectable text. Which **rendering mode** `react-pdf` uses (PDF vs. `<img>`) depends
    directly on which wins — so this decision and §6 Q6's docling-fidelity verdict are now
    the two spike-driven outcomes that gate the ingestion pipeline build.

## 7. Suggested next action

Spike the ingestion path **first**, against the real manuals now on hand, before writing
any agent/schema/frontend code. Order matters (§6 Q3 — solo):
1. **docling on the digital-native ~503-page MVP manual first** (fast, high confidence)
   — confirm text/table/page-number extraction quality, and whether it reliably reports
   section/heading (TOC) structure for §4.7's section-based segments. This directly feeds
   §6 Q6.
2. **docling on the scanned, diagram-heavy stretch manual second** — this is the harder
   OCR case; the result decides whether scanned manuals are a realistic MVP+1 story or
   need a separate preprocessing path.
3. **PDF page-slicing vs. raster-image trade-off** (§6 Q10), weighed on the same
   manual(s) in the same spike — confirms a library choice for per-page assets at ingest
   time, and which `react-pdf` mode (`PDF` vs. `<img>`) pairs with it.

Both Q6 and Q10 now resolve from the spike's results, not from further discussion. Once
they're decided, lock the `Chunk`/`Manual`/`Vehicle` schemas (§4) — including the
page-index output from §4.7 — and build the agent tools + ingestion pipeline against
them, with `vehicle_id`/`manual_id` in the schema from day one even though MVP exercises
a single vehicle/manual pair. Everything runs **local-first** (§6 Q8): localhost +
private Qdrant/Redis, no public URL.
