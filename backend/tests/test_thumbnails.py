"""End-to-end tests for the page-thumbnail endpoint (IMPLEMENTATION Task 5).

Builds a real multi-page PDF with PyMuPDF (already a dependency) so the render
path produces a real PNG — no network or downloaded models needed.
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
    """Build a PDF with one page per string; an empty string is a blank page."""
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


def test_thumbnail_returns_a_png():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/thumbnails/2")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumbnail_rejects_page_zero():
    manual_id = _store_manual(["one", "two"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/thumbnails/0")
    assert resp.status_code == 400


def test_thumbnail_rejects_page_past_the_end():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/thumbnails/9")
    assert resp.status_code == 400
    assert "outside" in resp.json()["detail"]


def test_thumbnail_unknown_manual_returns_404():
    client = TestClient(app)
    resp = client.get("/manuals/does-not-exist/thumbnails/1")
    assert resp.status_code == 404