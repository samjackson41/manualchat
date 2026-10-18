"""Render one page of a manual to a PNG thumbnail (IMPLEMENTATION Task 5).

The viewer's fallback mode (IMPLEMENTATION §7) shows a raster page image when a
client cannot mount the PDF viewer. This module renders one physical page of the
stored ``source.pdf`` to a PNG at a caller-chosen DPI, on demand. Pages are
1-indexed physical PDF pages (DECISIONS D12).
"""

from __future__ import annotations

import pymupdf

from backend import storage


class ThumbnailError(RuntimeError):
    """A thumbnail request named a bad page or a missing source PDF."""


def thumbnail_png(manual_id: str, page: int, dpi: int) -> bytes:
    """Return the PNG bytes for ``page`` (1-indexed) of one manual."""
    if page < 1:
        raise ThumbnailError(f"page {page} is invalid")

    manual = storage.get_manual(manual_id)
    if manual is None:
        raise ThumbnailError(f"manual not found: {manual_id}")

    source = storage.manual_dir(manual_id) / "source.pdf"
    if not source.is_file():
        raise ThumbnailError(f"source.pdf is missing for manual {manual_id}")

    doc = pymupdf.open(source)
    try:
        if page > doc.page_count:
            raise ThumbnailError(f"page {page} is outside 1-{doc.page_count}")
        page_obj = doc.load_page(page - 1)
        pixmap = page_obj.get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
    finally:
        doc.close()