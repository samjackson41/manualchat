# IMPLEMENTATION — ManualChat

## 1. Decided Tech Stack & Rationale

| Layer | Component | Decision / Rationale |
|---|---|---|
| **Language & Runtime** | Python 3.11+, UV virtual environment | Cohort standard (`aie-cohort-202609/.venv`), fast dependency management. |
| **PDF Extraction** | IBM Docling (`docling>=2.52.0`) | High-fidelity table structure extraction (`TableFormerMode.FAST`) and layout blocks. Ingestion pins `do_ocr=False` to prevent memory blowups. |
| **PDF Slicing & Raster** | `pypdf>=6.19.0` & `PyMuPDF>=1.28.2` | `pypdf` generates lightweight multi-page PDF slices (50 KB) for selectable text and zoom. `PyMuPDF` pre-renders raster PNG thumbnails for mobile/inline diagram viewing. |
| **Vector Database** | Qdrant (local Docker / local service) | Single collection with payload filtering (`vehicle_id`, `manual_id`). Low overhead, dense cosine index. |
| **Embeddings & Re-ranking** | `sentence-transformers` | `multi-qa-mpnet-base-dot-v1` (768-dim) for first-pass bi-encoder retrieval; `cross-encoder/ms-marco-MiniLM-L-6-v2` for citation re-ranking. Reused from cohort repository. |
| **Agent Orchestration** | LangGraph (`StateGraph`) | Supervisor/Planner node $\to$ a `worker` node that runs the tool loop (`search_manual`, `extract_specs`, `get_page_text`, `calculator`) $\to$ a `synthesize` node. |
| **LLM Gateway** | OpenRouter (`shared.llm.client`) | Provider-agnostic gateway. The UI-selectable model picks a tier that fixes the supervisor and worker models and their reasoning effort (DECISIONS M1). |
| **Session & State Memory** | LangGraph `InMemorySaver` / `RedisSaver` | Swappable checkpointer from cohort memory patterns. Scoped per vehicle session. |
| **API Backend** | FastAPI | Async endpoints for ingestion (`POST /manuals/upload`), chat stream (`POST /chat/stream`), and sliced document retrieval (`GET /manuals/{id}/pages/{start}-{end}`). |
| **Frontend** | Next.js 14+ (App Router), Tailwind CSS v4, shadcn/ui, assistant-ui, `react-pdf` | Dedicated garage chat interface built on assistant-ui (thread history, markdown, streaming), with a split-pane PDF viewer using `react-pdf` in PDF slice mode. |
| **Evaluations** | Custom LLM-as-judge script (`project/eval`) | Automated scoring on citation precision, torque/fluid accuracy, and hallucination rate against a synthetic ground-truth eval set. |

### Considered and Rejected
* **BigQuery**: Rejected. The problem domain consists of document chunks, tables, and unstructured manual text. Tabular OLAP warehousing provides zero benefit and adds infrastructure bloat.
* **Custom MCP Server**: Rejected for MVP. Function calls are internal to the LangGraph agent (`bind_tools`). Model Context Protocol is designed for cross-client external tool sharing, which is unnecessary for this single-application system.
* **BYOK (Bring Your Own Key)**: Rejected for MVP. The system is run single-user locally. Key management interfaces add friction with zero MVP utility.
* **Full Multi-Tenant Authentication (Auth0/Clerk/Supabase)**: Rejected for MVP. Local execution requires no auth. When shared with trusted peers post-MVP, a static `X-API-Key` or shared bearer token suffices.
* **Client-Side Full PDF Rendering**: Rejected. Parsing 500+ page (25+ MB) PDFs in browser WebAssembly crashes mobile browsers and causes severe rendering lag. Server-side page slicing resolves this cleanly.


---

## 2. Architecture & Data Flow

### 2.1 System Topology

```
                  ┌─────────────────────────────────────────┐
                  │           Next.js Frontend              │
                  │   (Chat + Citations + react-pdf Slice)  │
                  └──────────────┬───────────────────▲──────┘
                                 │                   │
                 SSE Stream / API Calls        PDF Slices & Thumbnails
                                 │                   │
                  ┌──────────────▼───────────────────┴──────┐
                  │             FastAPI Backend             │
                  └───────┬───────────────────────────┬─────┘
                          │                           │
            ┌─────────────▼───────────────┐     ┌─────▼─────────────────────┐
            │       LangGraph Agent       │     │     Document Storage      │
            │  (Supervisor + Tool Nodes)  │     │ - Uploaded Full PDFs      │
            └───────┬───────────────┬─────┘     │ - Sliced PDF Segments     │
                    │               │           │ - Raster Thumbnail PNGs   │
         ┌──────────▼─────┐   ┌─────▼───────┐   └───────────────────────────┘
         │ Qdrant Vector  │   │ OpenRouter  │
         │ (Payload-filt) │   │ (LLM / VLM) │
         └────────────────┘   └─────────────┘
```

### 2.2 Ingestion Pipeline Flow
```
PDF Upload
  │
  ├─► PyMuPDF Page Check & Slice Index Generator
  │     └─► Emits physical-to-printed page mapping JSON
  │
  ├─► Docling Converter (`do_ocr=False`, `FAST` tables, batch=1)
  │     ├─► Text Blocks (with section header hints)
  │     └─► Structured TableItems (converted to Pandas DataFrames -> Markdown)
  │
  ├─► Text & Unit Normalizer (Fixes `HiddenHorzOCR` artifacts, `Ib` -> `lb`, strip junk)
  │
  ├─► Chunk Generator (Section-aware split, 512 tokens / 64 overlap, tables kept whole, tagged with `vehicle_id`, `manual_id`, `page_number`)
  │
  ├─► SentenceTransformer (`multi-qa-mpnet-base-dot-v1`) Embedder
  │
  ├─► Qdrant Payload Upsert (`points` with embeddings + chunk metadata)
  │
  └─► Slice & Thumbnail Generator (Runs in background worker):
        ├─► `pypdf` extracts 5-page window PDF slices
        └─► `PyMuPDF` renders 150 DPI page preview PNGs
```

### 2.3 Agent Tool Loop (LangGraph StateGraph)

Implemented. The agent uses a supervisor-directed topology to keep grounded reasoning:

```
        User Query
             |
             v
      +--------------+   keep searching   +-------------------------------+
      |  Supervisor  |------------------->|  Worker (tool loop)           |
      |   (Plan)     |<-------------------|  search_manual, extract_specs |
      +------+-------+      findings      |  get_page_text, calculator    |
             |                            +-------------------------------+
             | synthesize
             v
      +--------------+
      |  Synthesize  |   markdown + [Page N]
      +------+-------+
             v
      Final Grounded Output to User
```

The graph has three nodes: `supervisor`, `worker`, and `synthesize`.
The `supervisor` decides whether the worker keeps searching or the graph synthesizes, and a hop cap (`AGENT_MAX_HOPS`) forces synthesis when it has not stopped.
The `worker` runs the tool loop over `search_manual`, `extract_specs`, `get_page_text`, and `calculator`.
The selected model picks the tier (DECISIONS M1): Flash selects `fast` (supervisor and synthesize on Flash at high effort, worker on Flash at low effort), and Pro selects `pro` (supervisor and synthesize on Pro at max effort, worker on Flash at high effort).

1. **Supervisor**: Analyzes the request and the worker's findings, then routes to the worker for more search, or to synthesis. It runs on the tier's supervisor model.
2. **`search_manual`**: Executes filtered Qdrant vector retrieval scoped to `vehicle_id` (and optional `manual_id`), reranked via `cross-encoder/ms-marco-MiniLM-L-6-v2`.
3. **`extract_specs`**: Targeted retrieval over extracted `TableItem` structured data to extract exact key/value parameters.
4. **`get_page_text`**: Retrieves the complete unchunked text for a target page when a procedure spans consecutive paragraphs.
5. **Synthesize**: Compiles the final response: Markdown steps and inline `[Page X]` citations. Enforces the strict rule: "If unmentioned in context, state not found." It runs on the tier's supervisor model.



---

## 3. Reuse Map (Cohort Repository Patterns)

| Component | Cohort Source Path | Adaptation Strategy |
|---|---|---|
| **Embeddings & Re-ranking** | `/home/sam/dev/aie-cohort-202609/project/retrieval/embeddings.py` | Import directly: `embed(texts)` and `rerank(query, candidates, top_n)`. Uses `multi-qa-mpnet-base-dot-v1` and `ms-marco-MiniLM-L-6-v2`. |
| **Qdrant Ingest Pattern** | `/home/sam/dev/aie-cohort-202609/project/retrieval/ingest.py` | Adapt `ingest()` to attach `vehicle_id`, `manual_id`, and `page_number` in `PointStruct` payload. Replace flat markdown loader with Docling output. |
| **Filtered Search** | `/home/sam/dev/aie-cohort-202609/project/retrieval/search.py` | Add Qdrant `Filter` with `must` match on `vehicle_id` and optional `manual_id`. |
| **LLM Gateway & Tools** | `/home/sam/dev/aie-cohort-202609/shared/llm/client.py`, `tools.py` | Reuse `chat()`, OpenRouter model config, and function-calling schemas as-is. |
| **StateGraph Pattern** | `/home/sam/dev/aie-cohort-202609/project/agents/graph.py` | Adapt the supervisor graph to one retrieval worker: a `supervisor` node, a `worker` node that runs the RAG tool loop, and a `synthesize` node. |
| **Memory Checkpointer** | `/home/sam/dev/aie-cohort-202609/project/memory/checkpointer.py` | Reuse `make_checkpointer()` to swap `InMemorySaver` (dev) and `RedisSaver` (production) via config. |
| **FastAPI SSE Streaming** | `/home/sam/dev/aie-cohort-202609/project/api/main.py` | Reuse Server-Sent Events (`EventSource`) streaming patterns for token-by-token UI updates. |
| **LLM-as-a-Judge Eval** | `/home/sam/dev/aie-cohort-202609/project/eval/judge.py`, `run.py` | Adapt rubric to evaluate `citation_precision`, `spec_exactness`, and `hallucination_rate`. |

---

## 4. Schemas, Naming, and Conventions

### 4.1 Data Schemas (`backend/schemas.py`)

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class Vehicle(BaseModel):
    vehicle_id: str
    user_id: str = "default_user"  # Single-user local default
    display_name: str              # e.g., "2023 Civic"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Manual(BaseModel):
    manual_id: str
    vehicle_id: str
    display_name: str
    source_filename: str
    description: Optional[str] = None
    status: Literal["processing", "ready", "error"] = "processing"
    page_count: int = 0
    chunk_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ChunkPayload(BaseModel):
    text: str
    vehicle_id: str
    manual_id: str
    page_number: int               # Printed page number
    physical_page: int             # 1-indexed PDF page
    section_name: Optional[str] = None
    is_table: bool = False
    score: float = 0.0

class SpecItem(BaseModel):
    item: str                      # e.g., "Engine oil drain bolt"
    value: str                     # e.g., "30"
    unit: str                      # e.g., "Nm (22 ft·lb)"
    page_number: int

class ProcedureStep(BaseModel):
    step_number: int
    instruction: str
    tools: list[str] = []
    warnings: list[str] = []
    specs: list[SpecItem] = []
    page_citations: list[int] = []

class AgentAnswer(BaseModel):
    summary: str
    procedure: list[ProcedureStep] = []
    specs: list[SpecItem] = []
    citations: list[int] = []      # Distinct pages referenced
    confidence: float
```



---

## 5. Build Order (Step-by-Step Milestones)

The POC order is: the system prompt (its own branch), the dependencies and
configuration, local storage and upload, ingest on `pl.pdf`, chunk and index in
local Qdrant, the retrieval tools with markdown answers, then the eval. The
`AgentAnswer` and the spec ledger come
later (DECISIONS Deferred).

Each task is scoped to be executed and verified in a single session:

1. **Task 1: Ingestion Pipeline & Normalization**
   - *Action*: Implement `ingest.py` integrating Docling with pinned config (`do_ocr=False`, `TableFormerMode.FAST`, threads=2, batch=1). Run the text-layer probe and refuse a manual that carries no text layer (DECISIONS D13). Build the printed-to-physical page map from the page footer or the header, with the TOC table as the fallback (DECISIONS D12). Add OCR artifact cleaning (`SPECiFiCATIONS` $\to$ `SPECIFICATIONS`, `Ib` $\to$ `lb`).
   - *Done when*: Running `python -m ingest /path/to/manual.pdf` extracts the 56-page `pl.pdf` in about 8 minutes, emitting normalized text and tables. The 503-page Rhino manual is a later, longer run.

2. **Task 2: Slicing & Thumbnail Pre-generation**
   - *Action*: Implement `slicer.py` using `pypdf` to produce 5-page window PDF slices and `PyMuPDF` for 150 DPI thumbnail images saved in `data/manuals/{manual_id}/`.
   - *Done when*: A slice request returns a clean ~50 KB vector PDF slice, and thumbnails render crisp images for sample pages 1, 9, 24, 82.

3. **Task 3: Qdrant Indexing & Payload Filtering**
   - *Action*: Implement chunking (512 tokens with 64 overlap, split on section headings, each table kept whole per DECISIONS D9 to D11), embedding via `multi-qa-mpnet-base-dot-v1`, and upsert into local Qdrant with `vehicle_id` and `manual_id` payload fields.
   - *Done when*: Querying `search_manual("oil change drain bolt", vehicle_id="demo_vehicle")` returns chunks from pages 24 and 82 with cross-encoder scores $> 0.7$.

4. **Task 4: Agent Tool Contracts & LangGraph Graph**
   - *Action*: Build `search_manual`, `extract_specs`, and `get_page_text` as Pydantic-typed tools, then run them in the supervisor/worker/synthesize graph. The POC answers in markdown with `[Page N]` citations. The structured `AgentAnswer` is a later task.
   - *Done when*: Running `python -m agent "how do I change engine oil?"` returns ordered steps, torque values, and correct page citations from the prototype manual.

5. **Task 5: FastAPI Backend Services**
   - *Action*: Expose REST endpoints: `GET /manuals/{id}/pages/{start}-{end}` (serves PDF slices), `GET /manuals/{id}/thumbnails/{page}` (serves PNG images), and `POST /chat/stream` (SSE token stream).
   - *Done when*: `curl -N http://localhost:8000/chat/stream` streams JSON chunks of a synthesized repair procedure.

6. **Task 6: Next.js Frontend with Sliced PDF Viewer**
   - *Action*: Build chat interface with Tailwind + shadcn/ui. Wire citation badges to trigger `react-pdf` in PDF mode loading `GET /manuals/{id}/pages/{start}-{end}`.
   - *Done when*: Clicking a `[Page 82]` badge in a chat bubble renders page 82 with selectable text in under 1.5 seconds.

7. **Task 7: Automated Evals & Quality Benchmark**
   - *Action*: Create synthetic eval suite (15 queries covering specs, procedures, and out-of-scope questions). Run LLM-as-a-judge scoring citation precision and spec correctness.
   - *Done when*: Evaluation run achieves $>90\%$ citation precision and $0\%$ fabricated specifications on out-of-scope queries.



---

## 6. Spike Outcomes & Resolved Decisions

The two gating spikes from brainstorming §6 are resolved by empirical data in `SPIKE_FINDINGS.md`:

### Spike Outcome 1: Docling Fidelity (Q6)
* **Status**: **RESOLVED / PASS WITH CONSTRAINTS**.
* **Criterion**: Docling extracts tables and text with high fidelity without exhausting system resources.
* **Result**:
  - `DocumentConverter(do_ocr=False, table_structure_options=TableFormerMode.FAST)` succeeded on 42-page sample in 335s with 2.92 GB peak RSS.
  - 34 structured spec tables cleanly parsed to DataFrames (e.g., M14 oil drain bolt 30 Nm, oil capacities 2.0L / 2.1L / 3.0L).
  - *Hard Constraint*: Default Docling config crashes host with OOM (~6 GB RSS). Ingestion pipeline must strictly enforce `do_ocr=False`, batch size 1, and max 2 threads.
  - *Heading Constraint*: `document_index` is empty; section names must be parsed from TOC table + section header regex, not Docling's document tree.

### Spike Outcome 2: PDF Slicing vs. Raster Images (Q10)
* **Status**: **RESOLVED / HYBRID ARCHITECTURE**.
* **Criterion**: Optimal rendering mode for `react-pdf` and bandwidth performance.
* **Result**:
  - `pypdf` slicing yields 5-page PDF segments of ~50 KB (10 KB/page) retaining vector crispness and selectable text (critical for copying torque numbers).
  - Raster PNG thumbnails (PyMuPDF at 150 DPI) are ~283 KB/page, lacking selectable text.
  - *Decision*: Serve **pre-sliced PDFs** as the primary viewer format in `react-pdf` (`<Document file={slice}><Page/></Document>`). Use **raster thumbnails** only for static image companions, mobile list views, and future on-demand diagram inspection.

---

## 7. Implementation Risks & Fallbacks

| Risk | Trigger Condition | Concrete Fallback Plan |
|---|---|---|
| **Host OOM during Full Ingestion** | Ingestion process RSS exceeds 3.5 GB or crashes worker on 500-page manual. | Split PDF into 50-page chunks using `pypdf` before passing to Docling; process chunks sequentially with manual `gc.collect()` between runs, then merge resulting JSON structures. |
| **Noisy OCR Text Layer Distortion** | Extracted specs contain garbled characters (e.g., `ft·Ib` or missing decimals). | Run deterministic regex normalizer on all text blocks prior to embedding and table conversion (`re.sub(r'ft·Ib', 'ft·lb', ...)`). |
| **Docling TOC Outline Missing** | Section titles missing in viewer context navigation bar. | Fallback from document tree to page-window navigation: use fixed 5-page windows (`[Page-2, Page+2]`) around cited page, reading section names from pre-parsed printed TOC table (pages 1–7). |
| **Agent Tool Calling Loops** | Agent repeatedly calls `search_manual` without progressing to synthesis. | Enforce a strict hop cap (`AGENT_MAX_HOPS`, default `4`) in the graph state. If exceeded, force the transition to `synthesize` with the context gathered so far, or return a gap acknowledgment. |
| **Browser PDF Rendering Latency** | `react-pdf` WebAssembly takes $>3$ seconds to mount on mobile browsers. | Toggle viewer to fallback `<img>` raster thumbnail mode (`GET /manuals/{id}/thumbnails/{page}`) for low-power mobile clients. |

