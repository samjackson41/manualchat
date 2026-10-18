"""End-to-end tests for the SSE chat stream (IMPLEMENTATION Task 5).

These go through the real FastAPI app and the real LangGraph graph. Only the
OpenRouter boundary is stubbed — the streaming node calls `llm.stream_chat`, so
that is the seam these tests replace.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import llm
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


def test_chat_stream_emits_tokens_then_done(monkeypatch):
    def fake_stream_chat(*args, **kwargs):
        yield {"content": "Hello", "tool_calls": None}
        yield {"content": " world.", "tool_calls": None}

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
    """A first streamed turn that asks for the calculator still resolves."""
    turns = iter(
        [
            [
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "calculator",
                                "arguments": '{"expression": "3*7+2"}',
                            },
                        }
                    ],
                }
            ],
            [{"content": "3*7+2 is 23.", "tool_calls": None}],
        ]
    )

    def fake_stream_chat(*args, **kwargs):
        yield from next(turns)

    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "what is 3*7+2?"})
    events = _events(resp)
    tokens = [e["content"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "3*7+2 is 23."

    done = next(e for e in events if e["type"] == "done")
    assert done["content"] == "3*7+2 is 23."


def test_chat_stream_without_api_key_emits_error(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(app)

    resp = client.post("/chat/stream", json={"query": "hi"})
    assert resp.status_code == 200
    events = _events(resp)
    assert events[-1]["type"] == "error"
    assert "OPENROUTER_API_KEY" in events[-1]["message"]