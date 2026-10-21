"""Tests for the RAG tool executors (IMPLEMENTATION Task 4).

These verify that the three tools in ``backend/tools.py`` call the real
retrieval backend and read a manual's ingest output from disk. Search runs two
ways: through a stubbed ``retrieval.search`` for the output contract, and
through the real search with an injected fake embedder and reranker, so no
model is downloaded (DECISIONS T1). One end-to-end test drives the LangGraph
graph with only ``llm.chat`` stubbed. The file-reading tools need no model.
"""

import json
import math
import uuid

import pytest
from langchain_core.messages import HumanMessage

from backend import llm, retrieval, storage, tools
from backend.agent.graph import graph
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


# Fake models so the real search path never downloads (DECISIONS T1).


def _fake_embed(texts: list[str], dim: int = 16) -> list[list[float]]:
    """A deterministic, text-sensitive stand-in for the bi-encoder."""
    vectors = []
    for text in texts:
        vec = [0.0] * dim
        for ch in text:
            vec[ord(ch) % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors


def _fake_rerank(_query, chunks, top_n):
    return chunks[:top_n]


def test_search_manual_runs_real_retrieval_with_fake_models(monkeypatch):
    """search_manual goes through the real index+search path, no model download."""
    manual_id = _store_manual_with_pages(
        {3: "Spark plug torque is 18 to 21 ft. lbs. (24 to 28 N-m)."}
    )
    monkeypatch.setattr(retrieval, "embed_texts", _fake_embed)
    monkeypatch.setattr(retrieval, "rerank_chunks", _fake_rerank)

    retrieval.index_manual(manual_id, embed=_fake_embed)

    result = SearchResult.model_validate_json(
        tools.search_manual("spark plug torque", "demo_vehicle")
    )
    assert [c.page_number for c in result.results] == [3]
    assert "18 to 21" in result.results[0].text


def test_search_manual_out_of_scope_returns_zero_results(monkeypatch):
    """An unmatched query surfaces zero results, not an error."""
    monkeypatch.setattr(retrieval, "search", lambda *a, **k: [])

    result = SearchResult.model_validate_json(
        tools.search_manual("valve clearance", "demo_vehicle")
    )
    assert result.results == []


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


def test_extract_specs_skips_disabled_manual():
    tables = [
        IngestTable(
            page_number=1,
            caption=None,
            markdown="| item | value |\n|---|---|\n| Displacement | 105.4 cu. in. |",
        ).model_dump(mode="json")
    ]
    manual_id = _store_manual_with_pages({}, tables)
    storage.update_manual(manual_id, enabled=False)

    result = ExtractSpecsResult.model_validate_json(
        tools.extract_specs("displacement", "demo_vehicle", manual_id)
    )
    assert result.specs == []


# --- Graph end to end -----------------------------------------------------


def test_graph_state_vehicle_id_overrides_model_argument(monkeypatch):
    """The state's vehicle scope wins over a vehicle_id the model supplied."""
    tables = [
        IngestTable(
            page_number=1,
            caption=None,
            markdown=(
                "| item | value |\n"
                "|---|---|\n"
                "| Displacement | 105.4 cu. in. (1726 cc) |"
            ),
        ).model_dump(mode="json")
    ]
    _store_manual_with_pages({}, tables)  # owned by demo_vehicle

    grounding = get_settings().agent_system_prompt
    calls: list[list[dict]] = []
    worker_turns = iter(
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "extract_specs",
                            "arguments": json.dumps(
                                {"subject": "displacement", "vehicle_id": "evil_vehicle"}
                            ),
                        },
                    }
                ],
            },
            {"content": "Displacement is 105.4 cu. in.", "tool_calls": None},
        ]
    )

    def fake_chat(messages, model=None, params=None, tools=None):
        # Only the worker records messages that carry a tool result.
        calls.append(messages)
        if messages[0]["content"] != grounding:
            return {"content": "synthesize", "tool_calls": None}
        if "Write the final answer" in messages[-1]["content"]:
            return {"content": "Displacement is 105.4 cu. in.", "tool_calls": None}
        return next(worker_turns)

    monkeypatch.setattr(llm, "chat", fake_chat)

    result = graph.invoke(
        {
            "messages": [HumanMessage(content="what is the displacement?")],
            "model": "test-model",
            "vehicle_id": "demo_vehicle",
            "stream": False,
            "gathered": [],
            "next": "",
            "hops": 0,
        }
    )

    # The worker's second call carried the tool result of the extract_specs call.
    worker_call = next(m for m in calls if any(x["role"] == "tool" for x in m))
    tool_message = next(x for x in worker_call if x["role"] == "tool")
    specs = ExtractSpecsResult.model_validate_json(tool_message["content"])
    assert specs.specs[0].value == "105.4 cu. in. (1726 cc)"
