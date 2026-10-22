"""Shared Pydantic schemas — the data contracts for ManualChat.

IMPLEMENTATION §4.1 defines these models. The RAG tool executors build and
validate instances of them, then serialize to JSON strings for the model to
read (a `ToolMessage`'s content is a string). When real retrieval lands
(Tasks 1-3), the same models validate Qdrant output — the contract stays fixed
and only the data source changes.

These are the *output* contracts of the tools. The *input* contracts (the
OpenAI function-calling schemas the model sees) live in `tools.py`.
"""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Vehicle(BaseModel):
    """A named vehicle profile, the scope of a repair conversation.

    `vehicle_id` is a server-generated UUID, the same way `manual_id` is. The
    client names the vehicle in `display_name` and keys everything else — its
    manuals, chunks, and the active conversation — to the returned id
    (SPECIFICATION §5 domain model).
    """

    vehicle_id: str
    user_id: str = "default_user"  # single-user local default
    display_name: str
    created_at: datetime = Field(default_factory=_utcnow)


class IngestProgress(BaseModel):
    """How far the ingest of one manual has come (DECISIONS U3).

    The upload dialog polls the manual record for this, so the reader sees a
    bar instead of an unexplained wait. `stage` names the pipeline step that is
    in progress. `completed` and `total` count the units of that step. The
    units are pages while `convert` reads the PDF, and chunks while `index`
    embeds them. A stage with nothing to count reports `total` as 0.
    """

    stage: Literal["probe", "convert", "index", "done"] = "probe"
    completed: int = 0
    total: int = 0


class Manual(BaseModel):
    """A registered, locally stored manual (DECISIONS U1).

    `page_count` and `chunk_count` are ingest outputs (IMPLEMENTATION §4.1).
    Storage records only what the upload provides; the ingest pipeline fills
    them in later.

    `enabled` gates retrieval only (DECISIONS M1): a disabled manual stays
    stored and listed, but its chunks never come back from search.

    `content_hash` is the SHA-256 of the uploaded PDF bytes. The upload path
    compares it against the stored hashes of the same vehicle so a duplicate
    manual is refused instead of ingested twice (DECISIONS U2).

    `progress` is the live position of the ingest run (DECISIONS U3). It is
    only meaningful while `status` is `processing`.
    """

    manual_id: str
    vehicle_id: str
    display_name: str
    source_filename: str
    description: Optional[str] = None
    content_hash: Optional[str] = None
    status: Literal["processing", "ready", "error"] = "processing"
    enabled: bool = True
    page_count: int = 0
    chunk_count: int = 0
    progress: IngestProgress = Field(default_factory=IngestProgress)
    created_at: datetime = Field(default_factory=_utcnow)


class TextLayerProbe(BaseModel):
    """The text-layer check that gates OCR (DECISIONS D1, S4)."""

    page_count: int
    total_chars: int
    avg_chars_per_page: float
    threshold: float
    needs_ocr: bool


class IngestTable(BaseModel):
    """One table exported to Markdown during ingest (IMPLEMENTATION Task 1)."""

    page_number: int
    caption: Optional[str] = None
    markdown: str


class IngestResult(BaseModel):
    """The on-disk summary written by the ingest pipeline."""

    manual_id: str
    page_count: int
    table_count: int
    probe: TextLayerProbe
    normalized: bool
    hidden_ocr_detected: bool


class ChunkPayload(BaseModel):
    """One retrieved chunk returned by `search_manual`."""

    text: str
    vehicle_id: str
    manual_id: str
    page_number: int  # physical PDF page (1-indexed); printed numbers stay unrecovered (DECISIONS D12)
    physical_page: Optional[int] = None  # legacy; unused now that D12 fixed physical pages
    section_name: Optional[str] = None
    is_table: bool = False
    score: float = 0.0


class SpecItem(BaseModel):
    """One extracted spec — e.g. a torque, capacity, or part number."""

    item: str  # "Engine oil drain bolt"
    value: str  # "30"
    unit: str  # "N·m (22 ft·lb)"
    page_number: int


class PageText(BaseModel):
    """The full, unchunked text of a single page."""

    page_number: int
    text: str


class SearchResult(BaseModel):
    """`search_manual` output: reranked chunks for a query."""

    query: str
    results: list[ChunkPayload]


class ExtractSpecsResult(BaseModel):
    """`extract_specs` output: exact key/value parameters from tables."""

    subject: str
    specs: list[SpecItem]


class GetPageTextResult(BaseModel):
    """`get_page_text` output: complete page text for a procedure span."""

    manual_id: str
    pages: list[PageText]
