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


class Manual(BaseModel):
    """A registered, locally stored manual (DECISIONS U1).

    `page_count` and `chunk_count` are ingest outputs (IMPLEMENTATION §4.1).
    Storage records only what the upload provides; the ingest pipeline fills
    them in later.
    """

    manual_id: str
    vehicle_id: str
    display_name: str
    source_filename: str
    kind: Literal["oem", "aftermarket", "supplement", "other"] = "oem"
    status: Literal["processing", "ready", "error"] = "ready"
    page_count: int = 0
    chunk_count: int = 0
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
    page_number: int  # printed page number (not the PDF's 0-indexed physical page)
    physical_page: Optional[int] = None
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
