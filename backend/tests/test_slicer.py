"""Tests for the on-demand page-slice endpoint (IMPLEMENTATION Task 6).

These build a real multi-page PDF with PyMuPDF (already a dependency) so the
slice path opens, selects, and re-serialises real pages — no uploaded models or
network needed.
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


def _slice_pages(data: bytes) -> list[str]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return [page.get_text().strip() for page in doc]
    finally:
        doc.close()


def test_page_slice_returns_the_requested_pages():
    manual_id = _store_manual(["one", "two", "three", "four"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pages/2-3")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert _slice_pages(resp.content) == ["two", "three"]


def test_page_slice_supports_a_single_page():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pages/2-2")
    assert resp.status_code == 200
    assert _slice_pages(resp.content) == ["two"]


def test_page_slice_rejects_a_range_past_the_end():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pages/2-9")
    assert resp.status_code == 400
    assert "outside" in resp.json()["detail"]


def test_page_slice_rejects_a_malformed_range():
    manual_id = _store_manual(["one", "two"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pages/not-a-range")
    assert resp.status_code == 400
    assert "start-end" in resp.json()["detail"]


def test_page_slice_unknown_manual_returns_404():
    client = TestClient(app)
    resp = client.get("/manuals/does-not-exist/pages/1-2")
    assert resp.status_code == 404


def test_page_slice_sets_immutable_cache_headers():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    resp = client.get(f"/manuals/{manual_id}/pages/2-3")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]
    assert resp.headers["etag"]


def test_page_slice_answers_a_matching_etag_with_304():
    manual_id = _store_manual(["one", "two", "three"])
    client = TestClient(app)

    first = client.get(f"/manuals/{manual_id}/pages/2-3")
    again = client.get(
        f"/manuals/{manual_id}/pages/2-3",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert again.status_code == 304
    assert again.content == b""