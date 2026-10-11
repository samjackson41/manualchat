# Project Proposal: ManualChat

ManualChat is a repair manual assistant for a vehicle. You ingest service manuals one time. Then you ask questions in plain English to get step-by-step procedures, technical values, and page citations. The system grounds every answer in the manual text. It does not guess.

---

## Use Case

Vehicle owners and mechanics must find exact values in dense manuals that often exceed 500 pages. These values include tightening limits, fluid volumes, part numbers, and instructions. Manuals are also fragmented. An original equipment manufacturer manual and an aftermarket manual for the same vehicle can disagree. Both are difficult to search on a phone during a repair.

ManualChat indexes these documents into a searchable knowledge base. When you ask a question, the system finds the source pages, builds a procedure, and provides the exact page citations. You can read the citation and inspect the source page directly.

## Product Features

### Minimum Viable Product

You can test these core features in the initial version:
- Ingest a digital repair manual in Portable Document Format (PDF). The system parses text, tables, and page boundaries with IBM Docling, and removes text errors caused by bad embedded character layers.
- Ask questions about the vehicle and receive answers that include page citations for every fact.
- Request repair instructions to receive an ordered procedure. Each step contains its source page citation, required tools, safety warnings, and tightening values.
- Open a cited page in a document viewer. The viewer loads a light 5-page slice of about 50 kilobytes with vector text, rather than loading the full 500-page file.
- Receive explicit missing-information notices. If the manual does not contain an answer, the system states that the manual omits that topic.

### Features Planned After the Minimum Viable Product

These features expand the system in later updates:
- Save multiple vehicle profiles, and attach multiple manuals to each vehicle.
- Identify conflicts between manuals. If two manuals for the same vehicle give different values, the system shows both values with their source citations.
- Ingest paper manuals with an optical character recognition pipeline (software that reads text from images).
- View magnified wiring schematics and assembly drawings.
- Share access with trusted users through an access key.


## Technical Architecture: Tools and Methods

The core system is an agent loop (a program that uses a language model to plan, call tools, and make sure that output meets constraints). The table below lists each tool, its job, and its method of operation.

| Layer | Selection | What the tool does | How the system uses the tool |
|---|---|---|---|
| Document Extraction | IBM Docling (`docling`) | Extracts text blocks, layout, and tables from PDF manuals. | The pipeline sets `do_ocr=False` and uses `TableFormerMode.FAST` to prevent out-of-memory errors on 500-page files. It converts tables to structured data frames, then cleans corrupted character sequences. |
| Document Slicing | `pypdf` and `PyMuPDF` | Creates page assets to allow fast document viewing without large file transfers. | `pypdf` extracts 5-page PDF slices of about 50 kilobytes so the viewer keeps clear vector lines and selectable text. `PyMuPDF` creates image thumbnails for preview cards and mobile screens. |
| Vector Storage | Qdrant | Stores document pieces as mathematical vectors to allow similarity search. | Qdrant stores 768-dimension vectors with metadata tags for the vehicle, the manual, and the page number. The search filters these tags to isolate the active vehicle. |
| Text Search and Re-ranking | `sentence-transformers` | Executes a two-stage search to find accurate reference chunks. | The first stage uses `multi-qa-mpnet-base-dot-v1` to retrieve candidate text blocks. The second stage uses `cross-encoder/ms-marco-MiniLM-L-6-v2` to score candidates and select top citations. |
| Agent Orchestration | LangGraph (`StateGraph`) | Controls multi-step agent execution with a supervisor graph. | A supervisor node evaluates the query, calls search tools, collects findings, and sends the context to a synthesizer node that produces the final answer. |
| Agent Tool Contracts | Native function calling with Pydantic | Defines input parameters and validation rules for each tool. | The agent calls `search_manual` for instructions, `extract_specs` for torque and fluid tables, and `get_page_text` for full page context. |
| Model Gateway | OpenRouter | Routes requests across different language models through one network interface. | The agent uses fast models for internal planning steps, and saves larger models for final synthesis and automated evaluation scoring. |
| Session Memory | LangGraph Checkpointers (`InMemorySaver` and `RedisSaver`) | Stores conversation state across multiple questions. | The checkpointer preserves the vehicle identity and prior repair steps, so the user can ask follow-up questions without repeating context. |
| Application Programming Interface | FastAPI | Serves web endpoints for background tasks and data delivery. | FastAPI receives document uploads at `POST /manuals/upload`, streams text tokens to the screen with `POST /chat/stream`, and returns document slices at `GET /manuals/{id}/pages/{start}-{end}`. |
| User Interface | Next.js, Tailwind CSS, shadcn/ui, and `react-pdf` | Displays a split screen for the chat dialog and the document viewer. | Next.js streams the agent response in the chat panel. When the user selects a page citation, `react-pdf` loads the 5-page PDF slice and displays the target page. |
| Evaluation and Quality | LangSmith with language model judges | Measures answer accuracy against a benchmark test set. | The evaluation pipeline tests three metrics: citation precision (the cited page must contain the fact), specification accuracy (numbers must match manual tables), and hallucination rate (unsupported claims must equal zero). |
| Hosting | Google Cloud Run and Vercel | Hosts the application containers in the cloud. | Cloud Run hosts the FastAPI container, and Vercel hosts the Next.js interface. The initial version runs on a local computer to protect network resources and API credentials. |

### Tools Deliberately Omitted

The project excludes these tools to prevent unnecessary complexity:
- Google BigQuery: the project uses document text and tables, not warehouse tables that require SQL queries.
- Model Context Protocol (MCP) servers: the tools serve one internal application rather than separate external clients, so standard function calling is sufficient.
- User-supplied API keys: the initial system runs for one local user, so key collection screens add unnecessary work.
- Full multi-user authentication: simple access tokens satisfy sharing requirements before the project requires complex user identity providers.

## Why the System Is Agentic

A basic search system returns text chunks directly to the user. ManualChat uses an agent loop that completes real work:
1. It reads the user request and builds a search plan.
2. It executes multiple tool calls. It queries text passages for procedural steps, calls table tools for exact tightening values, and fetches surrounding pages when steps continue across page boundaries.
3. It validates the output against a data schema. It places safety warnings before dangerous steps, makes sure that each claim has an exact page number, and makes sure that extracted specifications match source tables.

## Project Scope and Plan

- Minimum Viable Product: one vehicle and one digital manual of approximately 503 pages. The system runs on a local computer with private database backends, while using the multi-vehicle data schema.
- Post-MVP: support for multiple vehicles, conflict detection across multiple manuals, optical character recognition for scanned documents, and cloud hosting.7
- Build Order: set up the document ingestion pipeline, create page slicing tools, initialize the vector index, build LangGraph agent tools, write FastAPI endpoints, assemble the Next.js interface, and run quality evaluations.
