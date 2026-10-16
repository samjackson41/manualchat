"""End-to-end tests for the HTTP API.

These go through the real FastAPI app, the real LangGraph graph, and the real
tool executor. Only the external OpenRouter boundary (`llm.chat`) is stubbed so
the tests are deterministic and need no API key or network.
"""

import pytest
from fastapi.testclient import TestClient

from backend import llm
from backend.api.main import app
from backend.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():
    """get_settings is lru-cached; reset it so env changes don't leak between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_llm(responses):
    """Return a stand-in llm.chat that records each call and pops a canned reply."""
    calls = []

    def fake(messages, model, params=None, tools=None):
        calls.append({"messages": messages, "model": model, "tools": tools})
        return responses.pop(0)

    return fake, calls


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_models():
    client = TestClient(app)
    resp = client.get("/models")
    assert resp.status_code == 200
    assert resp.json() == {
        "default": "~deepseek/deepseek-flash-latest",
        "options": [
            {"id": "~deepseek/deepseek-flash-latest", "label": "DeepSeek Flash"},
            {"id": "~deepseek/deepseek-pro-latest", "label": "DeepSeek Pro"},
        ],
    }


def test_chat_plain_reply(monkeypatch):
    fake, calls = _fake_llm(
        [{"role": "assistant", "content": "Hello there.", "tool_calls": None}]
    )
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "Hello there.",
        "model": "~deepseek/deepseek-flash-latest",
    }

    # The graph leads with the system prompt, then the user's query.
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["messages"][1] == {"role": "user", "content": "hi"}


def test_chat_system_prompt_is_first(monkeypatch):
    """The grounding prompt is the first message the model receives."""
    fake, calls = _fake_llm(
        [{"role": "assistant", "content": "ok", "tool_calls": None}]
    )
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "what is the oil capacity?"})
    assert resp.status_code == 200

    messages = calls[0]["messages"]
    assert messages[0] == {
        "role": "system",
        "content": get_settings().agent_system_prompt,
    }
    assert messages[1] == {"role": "user", "content": "what is the oil capacity?"}


def test_chat_tool_loop(monkeypatch):
    """A query that needs the calculator runs tool -> chat inside the graph."""
    fake, calls = _fake_llm(
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
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "what is 3*7+2?"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "3*7+2 is 23."

    # Two model calls: first asks for the calculator, then answers.
    assert len(calls) == 2
    # The second call was handed the tool result, proving the calculator ran.
    tool_msg = next(m for m in calls[1]["messages"] if m["role"] == "tool")
    assert tool_msg["content"] == "23"


def test_chat_without_api_key_returns_400(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi"})
    assert resp.status_code == 400
    assert "OPENROUTER_API_KEY" in resp.json()["detail"]
