"""On-demand PDF page slicing (DECISIONS V1, IMPLEMENTATION Task 6).

The manual viewer asks for the few pages around the page an answer cites. This
module cuts that window out of the stored ``source.pdf`` with PyMuPDF (already
a dependency of the ingest pipeline) and returns the slice bytes.

Pages are 1-indexed physical PDF pages, inclusive on both ends (DECISIONS D12).
"""

from __future__ import annotations

import pymupdf

from backend import storage


class SliceError(RuntimeError):
    """A slice request named a bad page range or a missing source PDF."""


def slice_pages(manual_id: str, start: int, end: int) -> bytes:
    """Return a PDF holding pages ``start..end`` of one manual, both inclusive."""
    if start < 1 or end < start:
        raise SliceError(f"page range {start}-{end} is invalid")

    manual = storage.get_manual(manual_id)
    if manual is None:
        raise SliceError(f"manual not found: {manual_id}")

    source = storage.manual_dir(manual_id) / "source.pdf"
    if not source.is_file():
        raise SliceError(f"source.pdf is missing for manual {manual_id}")

    doc = pymupdf.open(source)
    try:
        page_count = doc.page_count
        if end > page_count:
            raise SliceError(
                f"page range {start}-{end} is outside 1-{page_count}"
            )
        # `insert_pdf` copies the source pages (0-indexed, inclusive) into a
        # fresh document without touching the stored PDF.
        sliced = pymupdf.open()
        try:
            sliced.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            return sliced.tobytes(garbage=0)
        finally:
            sliced.close()
    finally:
        doc.close()