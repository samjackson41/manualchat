"""Docling ingestion pipeline (IMPLEMENTATION Task 1).

Read a stored PDF under ``manuals/{manual_id}/source.pdf`` and turn it into the
normalized text and tables that later stages chunk and index. Stages, in order:

1. Text-layer probe (DECISIONS D1, S4): PyMuPDF counts text per page. A manual
   whose average falls below ``ingest_ocr_min_chars_per_page`` is refused, so a
   scanned upload is caught before Docling tries to OCR it.
2. Hidden-OCR sanitize (DECISIONS D2): PyMuPDF removes ghost-font text before
   Docling reads it. The noise stays behind only as a fallback for the
   normalizer when it overlaps visible text.
3. Docling convert: ``do_ocr=False``, FAST table structure, one batch item, and
   a small thread count keep peak memory below the spike's crash threshold.
4. Normalize (DECISIONS D3): deterministic unit/header string repair.
5. Persist: per-page text, table Markdown, and a summary under
   ``manuals/{manual_id}/``, then update the manual record.

Run it with ``python -m backend.ingest <manual_id>``. On upload, the API calls
``ingest_in_background`` instead so the pipeline runs in a worker thread after
the response.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

from backend import retrieval, storage
from backend.config import Settings, get_settings
from backend.schemas import IngestResult, IngestTable, TextLayerProbe


class IngestError(RuntimeError):
    """The pipeline refused or failed to ingest a manual."""


# Unit and header repair rules (DECISIONS D3). The longer, more specific pattern
# runs before its shorter substring so ``ft·Ib`` repairs before the bare ``Ib``
# rule. The full normalization catalog is deferred (DECISIONS Deferred).
_NORMALIZATION_RULES: tuple[tuple[str, str], ...] = (
    ("SPECiFiCATIONS", "SPECIFICATIONS"),
    ("ft·Ib", "ft·lb"),
    ("m· kg", "m·kg"),
    ("Ib", "lb"),
)

# Substrings that mark an invisible OCR font (the spike's ``HiddenHorzOCR``).
_HIDDEN_OCR_MARKERS: tuple[str, str] = ("hidden", "ocr")


def normalize_text(text: str) -> str:
    """Repair the documented OCR and diacritic noise in one text block."""
    repaired = text
    for pattern, replacement in _NORMALIZATION_RULES:
        repaired = repaired.replace(pattern, replacement)
    return repaired


def _font_is_hidden_ocr(font_name: str) -> bool:
    lowered = font_name.lower()
    return all(marker in lowered for marker in _HIDDEN_OCR_MARKERS)


def probe_text_layer(pdf_path: Path, threshold: float) -> TextLayerProbe:
    """Count text per page and decide whether the manual needs OCR (D1)."""
    doc = pymupdf.open(pdf_path)
    try:
        page_count = doc.page_count
        chars = [len(page.get_text()) for page in doc]
    finally:
        doc.close()
    total = sum(chars)
    avg = total / page_count if page_count else 0.0
    return TextLayerProbe(
        page_count=page_count,
        total_chars=total,
        avg_chars_per_page=round(avg, 2),
        threshold=threshold,
        needs_ocr=avg < threshold,
    )


def _hidden_ocr_detected(doc: pymupdf.Document) -> bool:
    """True when any page uses a hidden-OCR ghost font."""
    for page in doc:
        for font in page.get_fonts():
            # A get_fonts entry is (xref, ext, type, basefont, name, encoding).
            if _font_is_hidden_ocr(font[3] or "") or _font_is_hidden_ocr(font[4] or ""):
                return True
    return False


def _visible_rects(page) -> list[pymupdf.Rect]:
    """Bounding boxes of every non-hidden text span on a page."""
    rects: list[pymupdf.Rect] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if not _font_is_hidden_ocr(span.get("font", "")):
                    rects.append(pymupdf.Rect(span["bbox"]))
    return rects


def _remove_hidden_ocr(page) -> None:
    """Redact ghost-font spans that do not overlap visible text.

    A hidden OCR layer usually sits exactly on top of the visible glyphs it
    transcribes. Redacting there would delete the real text too, so those
    overlaps are left alone; the normalizer repairs the ``ft·Ib``-style noise
    they produce. Orphan ghost text (no visible span in the same box) is safe
    to remove.
    """
    visible = _visible_rects(page)
    hidden: list[pymupdf.Rect] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if _font_is_hidden_ocr(span.get("font", "")):
                    hidden.append(pymupdf.Rect(span["bbox"]))

    for rect in hidden:
        if any(rect.intersects(v) for v in visible):
            continue
        page.add_redact_annot(rect)
    if hidden:
        page.apply_redactions()


def prepare_pdf(pdf_path: Path, strip_enabled: bool) -> tuple[Path, bool]:
    """Return the PDF path for Docling and whether a hidden layer was stripped.

    When ``strip_enabled`` is false or no ghost font is present, the original
    path is returned unchanged (the common born-digital case). Otherwise a
    sanitized sibling copy is written and returned.
    """
    if not strip_enabled:
        return pdf_path, False

    doc = pymupdf.open(pdf_path)
    try:
        if not _hidden_ocr_detected(doc):
            return pdf_path, False
        sanitized = pdf_path.with_name(pdf_path.stem + ".sanitized.pdf")
        for page in doc:
            _remove_hidden_ocr(page)
        doc.save(sanitized)
        return sanitized, True
    finally:
        doc.close()


def build_converter(settings: Settings) -> object:
    """Build the Docling converter with the pinned low-memory options."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline = PdfPipelineOptions()
    pipeline.do_ocr = settings.ingest_do_ocr
    pipeline.do_table_structure = settings.ingest_do_table_structure
    pipeline.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode[settings.ingest_table_mode.upper()],
    )
    pipeline.accelerator_options = AcceleratorOptions(
        num_threads=settings.ingest_threads,
        device="auto",
    )
    pipeline.table_batch_size = settings.ingest_batch_size
    pipeline.layout_batch_size = settings.ingest_batch_size
    pipeline.generate_page_images = False
    pipeline.generate_picture_images = False

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline),
        }
    )


def convert_document(converter, pdf_path: Path):
    """Run Docling on one PDF and return its document."""
    return converter.convert(pdf_path).document


def _pages_text(document, page_count: int) -> dict[int, str]:
    """Group the document's text items by 1-indexed physical page."""
    pages: dict[int, str] = {n: "" for n in range(1, page_count + 1)}
    for item in document.texts:
        if not item.prov:
            continue
        page = item.prov[0].page_no
        pages[page] = pages.get(page, "") + item.text + "\n"
    return {n: text.rstrip() for n, text in pages.items()}


def _tables(document, normalize: bool) -> list[IngestTable]:
    """Export each table to Markdown with its page number and caption."""
    tables: list[IngestTable] = []
    for item in document.tables:
        if not item.prov:
            continue
        page = item.prov[0].page_no
        markdown = item.export_to_markdown(document)
        caption = item.caption_text(document) or None
        if normalize:
            markdown = normalize_text(markdown)
            caption = normalize_text(caption) if caption else None
        tables.append(IngestTable(page_number=page, caption=caption, markdown=markdown))
    return tables


def ingest_manual(manual_id: str, converter=None) -> IngestResult:
    """Run the full pipeline for one stored manual."""
    settings = get_settings()
    manual = storage.get_manual(manual_id)
    if manual is None:
        raise IngestError(f"manual not found: {manual_id}")

    source = storage.manual_dir(manual_id) / "source.pdf"
    if not source.is_file():
        raise IngestError(f"source.pdf is missing for manual {manual_id}")

    probe = probe_text_layer(source, settings.ingest_ocr_min_chars_per_page)
    if probe.needs_ocr:
        storage.update_manual(manual_id, status="error")
        raise IngestError(
            f"manual {manual_id} has no usable text layer "
            f"({probe.avg_chars_per_page} chars/page, threshold "
            f"{settings.ingest_ocr_min_chars_per_page}); OCR is out of MVP scope"
        )

    working_pdf, stripped = prepare_pdf(
        source, settings.ingest_strip_hidden_ocr_layer
    )
    try:
        document = convert_document(converter or build_converter(settings), working_pdf)
    finally:
        if stripped:
            working_pdf.unlink(missing_ok=True)

    normalize = settings.ingest_normalization_enabled
    pages = _pages_text(document, probe.page_count)
    tables = _tables(document, normalize)

    page_dir = storage.manual_dir(manual_id) / "page_text"
    page_dir.mkdir(parents=True, exist_ok=True)
    for page_number, text in pages.items():
        (page_dir / f"page_{page_number:04d}.txt").write_text(
            normalize_text(text) if normalize else text
        )

    tables_path = storage.manual_dir(manual_id) / "tables.json"
    tables_path.write_text(
        json.dumps([t.model_dump(mode="json") for t in tables], indent=2)
    )

    result = IngestResult(
        manual_id=manual_id,
        page_count=probe.page_count,
        table_count=len(tables),
        probe=probe,
        normalized=normalize,
        hidden_ocr_detected=stripped,
    )
    (storage.manual_dir(manual_id) / "ingest.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2)
    )
    storage.update_manual(manual_id, page_count=probe.page_count, status="ready")
    return result


def ingest_in_background(manual_id: str) -> None:
    """Run ingest for a worker thread, then index the manual.

    The upload endpoint schedules this after the response. On success,
    ``ingest_manual`` writes ``status="ready"``, then the manual is chunked and
    indexed via ``retrieval.index_manual``, which records ``chunk_count``. On
    any failure this writes ``status="error"`` and re-raises so the server logs
    the cause.
    """
    try:
        ingest_manual(manual_id)
        retrieval.index_manual(manual_id)
    except Exception:
        storage.update_manual(manual_id, status="error")
        raise


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="backend.ingest",
        description="Ingest one stored manual through the Docling pipeline.",
    )
    parser.add_argument("manual_id", help="the stored manual's UUID directory name")
    args = parser.parse_args(argv)
    try:
        result = ingest_manual(args.manual_id)
    except IngestError as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))