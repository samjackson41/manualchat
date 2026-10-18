"""Tests for chunking and retrieval (IMPLEMENTATION Task 3).

The cheap tests cover the pure chunking behaviour with the real cl100k_base
tokenizer, plus one index-and-search round trip that injects a fake embedder
and reranker so no model downloads (DECISIONS T1). The real sentence-transformers
path is the heavy test at the bottom, which carries ``@pytest.mark.heavy`` and
sits outside the default run (DECISIONS T2/T3).
"""

import json
import math
import uuid
from pathlib import Path

import pytest

from backend import retrieval, storage
from backend.config import get_settings
from backend.schemas import IngestTable


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    monkeypatch.setenv("QDRANT_PATH", ":memory:")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("QDRANT_COLLECTION", f"test_{uuid.uuid4().hex}")
    yield
    get_settings.cache_clear()


# --- Pure chunking --------------------------------------------------------


def test_count_tokens_uses_cl100k_base():
    assert retrieval.count_tokens("hello world") == 2
    assert retrieval.count_tokens("hello world") < retrieval.count_tokens(
        "hello world " * 10
    )


def test_is_heading():
    assert retrieval.is_heading("ENGINE STARTING")
    assert retrieval.is_heading("BEFORE START-UP")
    assert retrieval.is_heading("SPECIFICATIONS")
    assert retrieval.is_heading("3. OIL")
    assert not retrieval.is_heading("DANGER")
    assert not retrieval.is_heading("WARNING")
    assert not retrieval.is_heading("Remove the oil drain bolt.")
    assert not retrieval.is_heading("1")
    assert not retrieval.is_heading("")


def test_window_text_overlong_run_gets_several_windows():
    text = "the quick brown fox jumps over the lazy dog " * 10
    pieces = retrieval._window_text(text, max_tokens=20, overlap_tokens=5)
    assert len(pieces) > 1
    assert all(pieces)
    # Overlap re-reads the tail of the previous window, so the pieces carry
    # more total tokens than the source text.
    total = sum(len(retrieval._tokenizer().encode(piece)) for piece in pieces)
    assert total > len(retrieval._tokenizer().encode(text))


def test_window_text_short_run_stays_whole():
    text = "short text"
    assert retrieval._window_text(text, max_tokens=100, overlap_tokens=10) == [text]


def test_build_chunks_keeps_each_table_whole(monkeypatch):
    monkeypatch.setenv("INGEST_CHUNK_TOKENS", "4")
    monkeypatch.setenv("INGEST_CHUNK_OVERLAP_TOKENS", "1")
    get_settings.cache_clear()

    pages = {1: "a", 2: "b"}
    table = IngestTable(
        page_number=1,
        caption="Torque specs",
        markdown="| item | value |\n| drain bolt | 30 |\n| oil | 2.0 |",
    )
    chunks = retrieval.build_chunks(pages, [table], "v1", "m1")

    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert table_chunks[0].text == table.markdown
    assert table_chunks[0].page_number == 1
    assert table_chunks[0].section_name == "Torque specs"


def test_build_chunks_attaches_section_headings():
    pages = {
        1: "ENGINE STARTING\nRun the engine only outdoors.",
        2: "OIL CHANGE\nRemove the drain bolt and drain the oil.",
    }
    chunks = retrieval.build_chunks(pages, [], "v1", "m1")

    by_page = {c.page_number: c for c in chunks}
    assert by_page[1].section_name == "ENGINE STARTING"
    assert by_page[1].text.startswith("ENGINE STARTING")
    assert by_page[2].section_name == "OIL CHANGE"


def test_build_chunks_structure_aware_can_be_disabled(monkeypatch):
    monkeypatch.setenv("INGEST_CHUNK_STRUCTURE_AWARE", "false")
    get_settings.cache_clear()

    pages = {1: "ENGINE STARTING\nRun the engine only outdoors."}
    chunks = retrieval.build_chunks(pages, [], "v1", "m1")
    assert chunks[0].section_name is None


# --- Index and search round trip (fake embedder/reranker) -----------------


def _fake_embed(texts, dim=64):
    vectors = []
    for text in texts:
        vec = [0.0] * dim
        for token in text.lower().split():
            vec[hash(token) % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


def _fake_rerank(_query, chunks, top_n):
    return chunks[:top_n]


def _store_ingested_manual(pages: dict[int, str]) -> str:
    manual = storage.store_manual(
        source_pdf=b"%PDF-fake",
        vehicle_id="demo_vehicle",
        display_name="Demo",
        kind="oem",
        source_filename="demo.pdf",
    )
    manual_dir = storage.manual_dir(manual.manual_id)
    page_dir = manual_dir / "page_text"
    page_dir.mkdir(parents=True, exist_ok=True)
    for page_number, text in pages.items():
        (page_dir / f"page_{page_number:04d}.txt").write_text(text)
    (manual_dir / "tables.json").write_text(
        json.dumps(
            [
                IngestTable(
                    page_number=2,
                    caption="Torque specs",
                    markdown="| item | value |\n| drain bolt | 30 |",
                ).model_dump(mode="json")
            ]
        )
    )
    return manual.manual_id


def test_index_then_search_returns_the_indexed_chunks():
    manual_id = _store_ingested_manual(
        {
            1: "Engine oil and oil filter change: remove the oil drain bolt.",
            2: "Tightening torque for the engine oil drain bolt is 30 N·m.",
        }
    )

    count = retrieval.index_manual(manual_id, embed=_fake_embed)
    assert count > 0
    assert storage.get_manual(manual_id).chunk_count == count

    result = retrieval.search(
        "oil drain bolt torque",
        "demo_vehicle",
        manual_id,
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert result
    assert result[0].manual_id == manual_id
    assert result[0].vehicle_id == "demo_vehicle"
    assert {c.page_number for c in result} == {1, 2}


def test_search_is_scoped_to_vehicle():
    manual_id = _store_ingested_manual(
        {1: "Engine oil and oil filter change: remove the oil drain bolt."}
    )
    retrieval.index_manual(manual_id, embed=_fake_embed)

    result = retrieval.search(
        "oil change",
        "someone_else",
        manual_id,
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert result == []


# --- Disabled manuals are excluded from search (DECISIONS M1) ---


def test_search_skips_disabled_manuals():
    manual_id = _store_ingested_manual(
        {1: "Engine oil and oil filter change: remove the oil drain bolt."}
    )
    retrieval.index_manual(manual_id, embed=_fake_embed)

    found = retrieval.search(
        "oil change",
        "demo_vehicle",
        manual_id,
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert found

    storage.update_manual(manual_id, enabled=False)
    assert (
        retrieval.search(
            "oil change",
            "demo_vehicle",
            manual_id,
            embed=_fake_embed,
            rerank=_fake_rerank,
        )
        == []
    )

    # Re-enabling brings the chunks straight back; nothing was deleted.
    storage.update_manual(manual_id, enabled=True)
    again = retrieval.search(
        "oil change",
        "demo_vehicle",
        manual_id,
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert again == found


def test_search_skips_only_disabled_manuals():
    keep_id = _store_ingested_manual(
        {1: "Engine oil and oil filter change: remove the oil drain bolt."}
    )
    drop_id = _store_ingested_manual({1: "Check the tire pressure monthly."})
    retrieval.index_manual(keep_id, embed=_fake_embed)
    retrieval.index_manual(drop_id, embed=_fake_embed)

    storage.update_manual(drop_id, enabled=False)

    result = retrieval.search(
        "oil change",
        "demo_vehicle",
        embed=_fake_embed,
        rerank=_fake_rerank,
    )
    assert result
    assert {c.manual_id for c in result} == {keep_id}


# --- Heavy end-to-end (real models; excluded from the default run) --------


@pytest.mark.heavy
def test_real_retrieval_ranks_relevant_chunk_first(tmp_path, monkeypatch):
    """Download real bi-encoder/cross-encoder models and verify retrieval order."""
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant"))
    get_settings.cache_clear()
    retrieval._client_for.cache_clear()

    manual_id = _store_ingested_manual(
        {
            1: "Engine oil and oil filter change: remove the oil drain bolt.",
            2: "Tightening torque for the engine oil drain bolt is 30 N·m.",
        }
    )
    retrieval.index_manual(manual_id)

    result = retrieval.search("oil drain bolt tightening torque", "demo_vehicle", manual_id)
    assert result
    assert result[0].page_number == 2
    assert result[0].score > 0.5