"""Shared Pydantic schemas — the data contracts for ManualChat.

IMPLEMENTATION §4.1 defines these models. The RAG tool executors build and
validate instances of them, then serialize to JSON strings for the model to
read (a `ToolMessage`'s content is a string). When real retrieval lands
(Tasks 1-3), the same models validate Qdrant output — the contract stays fixed
and only the data source changes.

These are the *output* contracts of the tools. The *input* contracts (the
OpenAI function-calling schemas the model sees) live in `tools.py`.
"""

from typing import Optional

from pydantic import BaseModel


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
