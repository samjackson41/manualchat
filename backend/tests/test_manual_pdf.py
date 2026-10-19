"""Tests for the whole-manual PDF endpoint (DECISIONS V2).

The endpoint streams the stored `source.pdf` back, so the viewer can show the
full manual. These build a real PDF with PyMuPDF, as the slicer tests do.
"""

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend import storage
from backend.api.main import app
from backend.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    yield
    get_settings.cache_clear()


def _pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes(garbage=0)
    doc.close()
    return data


def _store_manual(pages: list[str]) -> str:
    return storage.store_manual(
        source_pdf=_pdf_bytes(pages),
        vehicle_id="demo_vehicle",
        display_name="Demo manual",
        source_filename="demo.pdf",
    ).manual_id


def _pdf_pages(data: bytes) -> list[str]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return [page.get_text().strip() for page in doc]
    finally:
        doc.close()


def test_whole_pdf_returns_every_page():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert _pdf_pages(resp.content) == ["one", "two", "three"]


def test_whole_pdf_unknown_manual_returns_404():
    client = TestClient(app)
    resp = client.get("/manuals/does-not-exist/pdf")
    assert resp.status_code == 404
