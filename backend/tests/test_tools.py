"""Tests for the RAG tool executors (IMPLEMENTATION Task 4).

These verify that the three tools in ``backend/tools.py`` call the real
retrieval backend and read a manual's ingest output from disk. ``search_manual``
is tested by stubbing ``retrieval.search`` (the real search is covered in
``test_retrieval.py``), so no model is downloaded (DECISIONS T1). The other two
tools read plain files, so they need no model at all.
"""

import json
import uuid

import pytest

from backend import retrieval, storage, tools
from backend.config import get_settings
from backend.schemas import (
    ChunkPayload,
    ExtractSpecsResult,
    GetPageTextResult,
    IngestTable,
    SearchResult,
)


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    monkeypatch.setenv("QDRANT_PATH", ":memory:")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("QDRANT_COLLECTION", f"test_{uuid.uuid4().hex}")
    yield
    get_settings.cache_clear()


def _store_manual_with_pages(
    pages: dict[int, str], tables: list[dict] | None = None
) -> str:
    """Store a manual and write its page text and (optionally) tables.json."""
    manual = storage.store_manual(
        source_pdf=b"%PDF-fake",
        vehicle_id="demo_vehicle",
        display_name="Demo",
        source_filename="demo.pdf",
    )
    manual_dir = storage.manual_dir(manual.manual_id)
    page_dir = manual_dir / "page_text"
    page_dir.mkdir(parents=True, exist_ok=True)
    for page_number, text in pages.items():
        (page_dir / f"page_{page_number:04d}.txt").write_text(text)
    if tables is not None:
        (manual_dir / "tables.json").write_text(json.dumps(tables))
    return manual.manual_id


# --- search_manual --------------------------------------------------------


def test_search_manual_returns_ranked_chunks(monkeypatch):
    chunks = [
        ChunkPayload(
            text="drain bolt torque",
            vehicle_id="demo_vehicle",
            manual_id="m1",
            page_number=24,
            score=0.9,
        ),
        ChunkPayload(
            text="oil change steps",
            vehicle_id="demo_vehicle",
            manual_id="m1",
            page_number=82,
            score=0.8,
        ),
    ]
    monkeypatch.setattr(retrieval, "search", lambda *a, **k: chunks)

    result = SearchResult.model_validate_json(
        tools.search_manual("oil", "demo_vehicle")
    )
    assert result.query == "oil"
    assert result.results == chunks


def test_search_manual_maps_top_k_to_top_n(monkeypatch):
    captured: dict = {}

    def fake_search(query, vehicle_id, manual_id=None, top_n=None, **kw):
        captured["top_n"] = top_n
        return []

    monkeypatch.setattr(retrieval, "search", fake_search)

    tools.search_manual("oil", "demo_vehicle", top_k=7)
    assert captured["top_n"] == 7

    tools.search_manual("oil", "demo_vehicle")
    assert captured["top_n"] == get_settings().retrieval_top_n


# --- get_page_text --------------------------------------------------------


def test_get_page_text_returns_real_page_text():
    manual_id = _store_manual_with_pages({1: "page one text", 2: "page two text"})

    result = GetPageTextResult.model_validate_json(
        tools.get_page_text([1, 2], manual_id)
    )
    assert result.manual_id == manual_id
    assert [p.page_number for p in result.pages] == [1, 2]
    assert result.pages[0].text == "page one text"
    assert result.pages[1].text == "page two text"


def test_get_page_text_skips_missing_pages():
    manual_id = _store_manual_with_pages({1: "page one text"})

    result = GetPageTextResult.model_validate_json(
        tools.get_page_text([1, 99], manual_id)
    )
    assert [p.page_number for p in result.pages] == [1]


# --- extract_specs --------------------------------------------------------


def test_extract_specs_returns_matching_rows():
    tables = [
        IngestTable(
            page_number=14,
            caption="Specifications",
            markdown=(
                "| item | value |\n"
                "|---|---|\n"
                "| Displacement | 105.4 cu. in. (1726 cc) |\n"
                "| Engine Type | Two-Cycle |"
            ),
        ).model_dump(mode="json")
    ]
    manual_id = _store_manual_with_pages({}, tables)

    result = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("displacement", "demo_vehicle", manual_id)
    )
    assert result.subject == "displacement"
    assert len(result.specs) == 1
    assert result.specs[0].item == "Displacement"
    assert result.specs[0].value == "105.4 cu. in. (1726 cc)"
    assert result.specs[0].page_number == 14


def test_extract_specs_returns_empty_when_no_match():
    tables = [
        IngestTable(
            page_number=14,
            caption=None,
            markdown="| item | value |\n|---|---|\n| Displacement | 105.4 cu. in. |",
        ).model_dump(mode="json")
    ]
    manual_id = _store_manual_with_pages({}, tables)

    result = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("tire pressure", "demo_vehicle", manual_id)
    )
    assert result.specs == []


def test_extract_specs_matches_caption():
    tables = [
        IngestTable(
            page_number=20,
            caption="Fuel and oil mixing",
            markdown=(
                "| Ratio | Fuel - 6 U.S. Gallons |\n"
                "|---|---|\n"
                "| 50:1 | 16 fl. oz. oil |"
            ),
        ).model_dump(mode="json")
    ]
    manual_id = _store_manual_with_pages({}, tables)

    result = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("fuel oil mixing ratio", "demo_vehicle", manual_id)
    )
    assert len(result.specs) == 1
    assert result.specs[0].item == "50:1"
    assert result.specs[0].value == "16 fl. oz. oil"


def test_extract_specs_scopes_to_vehicle_when_no_manual_id():
    tables = [
        IngestTable(
            page_number=1,
            caption=None,
            markdown="| item | value |\n|---|---|\n| Displacement | 105.4 |",
        ).model_dump(mode="json")
    ]
    _store_manual_with_pages({}, tables)  # belongs to demo_vehicle

    found = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("displacement", "demo_vehicle")
    )
    assert len(found.specs) == 1

    missing = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("displacement", "other_vehicle")
    )
    assert missing.specs == []
