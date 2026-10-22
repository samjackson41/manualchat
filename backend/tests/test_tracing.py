"""Tests for the LangSmith tracing layer (MVP+1 monitoring).

No network is used: the direct `record` tests inject a fake client, and the
wiring tests stub `llm.httpx` and `tracing.record` (DECISIONS T1).
"""

import json
from datetime import datetime, timezone

import httpx
import pytest

from backend import llm, tracing
from backend.config import get_settings


class FakeClient:
    """Captures `create_run` calls; no network."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.runs = []

    def create_run(self, **kwargs):
        self.runs.append(kwargs)


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _enable_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_key")
    get_settings.cache_clear()


def _times():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 0, 0, 1, 250000, tzinfo=timezone.utc)
    return start, end


def test_record_is_noop_when_tracing_disabled():
    client = FakeClient()
    start, end = _times()
    tracing.record(
        name="chat", model="m", messages=[], started=start, ended=end, client=client
    )
    assert client.runs == []


def test_record_posts_run_with_usage_and_latency(monkeypatch):
    _enable_tracing(monkeypatch)
    client = FakeClient()
    start, end = _times()
    tracing.record(
        name="chat",
        model="~deepseek/deepseek-flash-latest",
        messages=[{"role": "user", "content": "hi"}],
        started=start,
        ended=end,
        output={"role": "assistant", "content": "hello"},
        usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        client=client,
    )
    assert len(client.runs) == 1
    run = client.runs[0]
    assert run["name"] == "chat"
    assert run["run_type"] == "llm"
    assert run["project_name"] == "manualchat"
    assert run["start_time"] == start
    assert run["end_time"] == end
    assert run["prompt_tokens"] == 12
    assert run["completion_tokens"] == 3
    assert run["total_tokens"] == 15
    assert run["outputs"] == {"output": {"role": "assistant", "content": "hello"}}
    assert run.get("error") is None
    assert run["extra"]["metadata"]["latency_ms"] == 1250
    assert run["extra"]["metadata"]["model"] == "~deepseek/deepseek-flash-latest"


def test_record_posts_error_without_output(monkeypatch):
    _enable_tracing(monkeypatch)
    client = FakeClient()
    start, end = _times()
    tracing.record(
        name="chat",
        model="m",
        messages=[],
        started=start,
        ended=end,
        error="OpenRouter error 500: boom",
        client=client,
    )
    assert len(client.runs) == 1
    run = client.runs[0]
    assert run["error"] == "OpenRouter error 500: boom"
    assert "outputs" not in run


def test_chat_records_output_and_usage(monkeypatch):
    _enable_tracing(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_settings.cache_clear()

    recorded = []
    monkeypatch.setattr(tracing, "record", lambda **kw: recorded.append(kw))

    class FakeResponse:
        is_error = False
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
            }

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: FakeResponse())

    reply = llm.chat([{"role": "user", "content": "hi"}], "~deepseek/deepseek-flash-latest")
    assert reply["content"] == "hi"
    assert len(recorded) == 1
    run = recorded[0]
    assert run["name"] == "chat"
    assert run["output"] == {"role": "assistant", "content": "hi"}
    assert run["usage"] == {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5}
    assert run["error"] is None


def test_stream_chat_records_usage_and_streams_deltas(monkeypatch):
    _enable_tracing(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_settings.cache_clear()

    recorded = []
    monkeypatch.setattr(tracing, "record", lambda **kw: recorded.append(kw))

    class FakeStream:
        is_error = False
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def iter_lines(self):
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]})
            yield "data: " + json.dumps({"choices": [{"delta": {"content": " world"}}]})
            yield "data: " + json.dumps(
                {
                    "choices": [{"delta": {"content": ""}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                }
            )
            yield "data: [DONE]"

    monkeypatch.setattr(llm.httpx, "stream", lambda *a, **k: FakeStream())

    deltas = list(
        llm.stream_chat([{"role": "user", "content": "hi"}], "~deepseek/deepseek-flash-latest")
    )
    contents = [d["content"] for d in deltas if d["content"]]
    assert "".join(contents) == "Hello world"

    assert len(recorded) == 1
    run = recorded[0]
    assert run["name"] == "stream_chat"
    assert run["output"] == "Hello world"
    assert run["usage"] == {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
    assert run["error"] is None


def test_chat_records_transport_error(monkeypatch):
    _enable_tracing(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    get_settings.cache_clear()

    recorded = []
    monkeypatch.setattr(tracing, "record", lambda **kw: recorded.append(kw))

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(llm.httpx, "post", boom)

    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}], "~deepseek/deepseek-flash-latest")

    assert len(recorded) == 1
    run = recorded[0]
    assert run["error"] == "OpenRouter request failed: down"
    assert run["usage"] is None
    assert run["output"] is None