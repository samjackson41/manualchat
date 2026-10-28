"""End-to-end tests for the SSE chat stream (IMPLEMENTATION Task 5).

These go through the real FastAPI app and the real LangGraph graph. Only the
OpenRouter boundary is stubbed: `llm.chat` for the supervisor and worker, and
`llm.stream_chat` for the `synthesize` node, which is the only streamed node.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import llm, retrieval
from backend.api.main import app
from backend.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _events(resp) -> list[dict]:
    """Parse the SSE ``data:`` lines out of a streamed response."""
    return [
        json.loads(line[5:])
        for line in resp.text.splitlines()
        if line.startswith("data:")
    ]


def _supervisor_chat(worker_reply="draft"):
    """A stand-in ``llm.chat`` for the supervisor and the worker nodes.

    The supervisor is the only caller whose first message is not the grounding
    system prompt; it always chooses synthesis so the answer can be streamed.
    """
    grounding = get_settings().agent_system_prompt

    def fake_chat(messages, model, params=None, tools=None):
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        return {"role": "assistant", "content": worker_reply, "tool_calls": None}

    return fake_chat


def test_chat_stream_emits_tokens_then_done(monkeypatch):
    def fake_stream_chat(*args, **kwargs):
        yield {"content": "Hello", "tool_calls": None}
        yield {"content": " world.", "tool_calls": None}

    monkeypatch.setattr(llm, "chat", _supervisor_chat())
    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "hi"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _events(resp)
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Hello world."

    done = next(e for e in events if e["type"] == "done")
    assert done["content"] == "Hello world."
    assert done["model"] == "~deepseek/deepseek-flash-latest"


def test_chat_stream_runs_the_tool_loop(monkeypatch):
    """A worker turn that asks for the calculator still resolves, then streams."""
    grounding = get_settings().agent_system_prompt
    worker_turns = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "3*7+2"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "3*7+2 is 23.", "tool_calls": None},
        ]
    )

    def fake_chat(messages, model, params=None, tools=None):
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        return next(worker_turns)

    def fake_stream_chat(*args, **kwargs):
        yield {"content": "3*7+2 is 23.", "tool_calls": None}

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "what is 3*7+2?"})
    events = _events(resp)
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "3*7+2 is 23."

    done = next(e for e in events if e["type"] == "done")
    assert done["content"] == "3*7+2 is 23."


def test_chat_stream_emits_tool_call_events(monkeypatch):
    """A worker turn that runs a tool also streams its call and result events."""
    grounding = get_settings().agent_system_prompt
    worker_turns = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "3*7+2"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "3*7+2 is 23.", "tool_calls": None},
        ]
    )

    def fake_chat(messages, model, params=None, tools=None):
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        return next(worker_turns)

    def fake_stream_chat(*args, **kwargs):
        yield {"content": "3*7+2 is 23.", "tool_calls": None}

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "what is 3*7+2?"})
    events = _events(resp)

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "calculator"
    assert calls[0]["args_text"] == '{"expression": "3*7+2"}'
    assert "tool_call_id" in calls[0]

    results = [e for e in events if e["type"] == "tool_result"]
    assert len(results) == 1
    assert results[0]["tool_call_id"] == calls[0]["tool_call_id"]
    assert results[0]["result"] == "23"
    assert results[0]["error"] is False


def test_chat_stream_shows_injected_vehicle_id(monkeypatch):
    """The streamed tool args show the state's vehicle, not the model's guess."""
    grounding = get_settings().agent_system_prompt
    worker_turns = iter(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_manual",
                            "arguments": '{"query": "valve adjustment", "vehicle_id": "demo_vehicle"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "See the manual.", "tool_calls": None},
        ]
    )

    def fake_chat(messages, model, params=None, tools=None):
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        return next(worker_turns)

    def fake_stream_chat(*args, **kwargs):
        yield {"content": "See the manual.", "tool_calls": None}

    def fake_search(query, vehicle_id, manual_id=None, top_n=None):
        return []

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(retrieval, "search", fake_search)
    client = TestClient(app)

    resp = client.post(
        "/chat/stream",
        json={"query": "how do I adjust the valves?", "vehicle_id": "outboard_vehicle"},
    )
    events = _events(resp)

    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    args = json.loads(calls[0]["args_text"])
    assert args["vehicle_id"] == "outboard_vehicle"
    assert args["query"] == "valve adjustment"


def test_chat_stream_without_api_key_emits_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "hi"})
    assert resp.status_code == 200
    events = _events(resp)
    assert events[-1]["type"] == "error"
    assert "OPENROUTER_API_KEY" in events[-1]["message"]