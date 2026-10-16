"""Tests for the ingest pipeline (IMPLEMENTATION Task 1).

These use a synthetic PDF and a fake converter so no Docling model is
downloaded (DECISIONS T1). The real Docling conversion is covered separately by
the heavy end-to-end run, not the default test suite.
"""

import json
from pathlib import Path

import pymupdf
import pytest

from backend import ingest, storage
from backend.config import get_settings
from backend.schemas import IngestTable


def _pdf_bytes(pages: list[str]) -> bytes:
    """Build a small PDF with one page per string; an empty string is a blank page."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes(garbage=0)
    doc.close()
    return data


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    yield
    get_settings.cache_clear()


def _store_manual(pages: list[str]) -> str:
    manual = storage.store_manual(
        source_pdf=_pdf_bytes(pages),
        vehicle_id="demo_vehicle",
        display_name="Demo manual",
        kind="oem",
        source_filename="demo.pdf",
    )
    return manual.manual_id


class _FakeProv:
    def __init__(self, page_no: int):
        self.page_no = page_no


class _FakeText:
    def __init__(self, text: str, page_no: int):
        self.text = text
        self.prov = [_FakeProv(page_no)]


class _FakeTable:
    def __init__(self, markdown: str, page_no: int, caption: str | None = None):
        self._markdown = markdown
        self._caption = caption
        self.prov = [_FakeProv(page_no)]

    def export_to_markdown(self, doc=None) -> str:
        return self._markdown

    def caption_text(self, doc) -> str:
        return self._caption or ""


class _FakeDocument:
    def __init__(self, texts, tables):
        self.texts = texts
        self.tables = tables


class _FakeConverter:
    def __init__(self, document):
        self._document = document

    def convert(self, pdf_path):
        class _Result:
            document = self._document

        return _Result()


def test_normalize_text_repairs_documented_noise():
    assert ingest.normalize_text("SPECiFiCATIONS") == "SPECIFICATIONS"
    assert ingest.normalize_text("Torque 30 ft·Ib") == "Torque 30 ft·lb"
    assert ingest.normalize_text("3.0 m· kg") == "3.0 m·kg"
    assert ingest.normalize_text("lb") == "lb"


def test_font_is_hidden_ocr():
    assert ingest._font_is_hidden_ocr("ABCDEE+HiddenHorzOCR")
    assert not ingest._font_is_hidden_ocr("ABCDEE+TimesNewRoman")


def test_probe_text_layer_flags_a_blank_manual():
    pdf = Path(get_settings().manuals_dir) / "blank.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(_pdf_bytes(["", "short"]))

    probe = ingest.probe_text_layer(pdf, threshold=50.0)
    assert probe.page_count == 2
    assert probe.needs_ocr is True
    assert probe.avg_chars_per_page < 50.0


def test_probe_text_layer_passes_a_text_manual():
    pdf = Path(get_settings().manuals_dir) / "text.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(
        _pdf_bytes(
            [
                "Remove the oil drain bolt and drain the oil fully into a pan.",
                "Refill with two litres of engine oil and tighten the bolt.",
            ]
        )
    )

    probe = ingest.probe_text_layer(pdf, threshold=50.0)
    assert probe.page_count == 2
    assert probe.needs_ocr is False
    assert probe.total_chars > 100


def test_ingest_manual_writes_pages_tables_and_record():
    manual_id = _store_manual(
        [
            "Remove the oil drain bolt and drain the oil fully into a pan.",
            "Refill with two litres of engine oil and tighten the bolt.",
        ]
    )
    document = _FakeDocument(
        texts=[
            _FakeText("Remove the oil drain bolt and drain the oil fully.", 1),
            _FakeText("Refill with two litres of engine oil.", 2),
        ],
        tables=[_FakeTable("| item | value |\n| drain bolt | 30 |", 1, "Torque")],
    )
    result = ingest.ingest_manual(manual_id, converter=_FakeConverter(document))

    assert result.page_count == 2
    assert result.table_count == 1
    assert result.hidden_ocr_detected is False

    manual_dir = storage.manual_dir(manual_id)
    assert (manual_dir / "page_text" / "page_0001.txt").read_text() == (
        "Remove the oil drain bolt and drain the oil fully."
    )
    assert (manual_dir / "page_text" / "page_0002.txt").read_text() == (
        "Refill with two litres of engine oil."
    )

    tables_path = manual_dir / "tables.json"
    tables = [IngestTable.model_validate(t) for t in json.loads(tables_path.read_text())]
    assert tables[0].page_number == 1
    assert tables[0].caption == "Torque"
    assert "drain bolt" in tables[0].markdown

    assert (manual_dir / "ingest.json").is_file()

    manual = storage.get_manual(manual_id)
    assert manual.page_count == 2
    assert manual.status == "ready"


def test_ingest_manual_refuses_a_manual_with_no_text_layer():
    manual_id = _store_manual([""])
    with pytest.raises(ingest.IngestError):
        ingest.ingest_manual(manual_id, converter=_FakeConverter(_FakeDocument([], [])))

    assert storage.get_manual(manual_id).status == "error"