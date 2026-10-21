"""End-to-end tests for the HTTP API.

These go through the real FastAPI app, the real LangGraph graph, and the real
tool executor. Only the external OpenRouter boundary (`llm.chat`) is stubbed so
the tests are deterministic and need no API key or network.
"""

import pytest
from fastapi.testclient import TestClient

from backend import ingest
from backend import llm
from backend import retrieval
from backend.api.main import app
from backend.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():
    """get_settings is lru-cached; reset it so env changes don't leak between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_llm(worker_reply="Hello there.", synth_reply=None):
    """A stand-in llm.chat that answers the supervisor, worker, and synthesize nodes.

    The nodes are told apart by their messages: the supervisor is the only
    caller whose first message is not the grounding system prompt; the
    synthesize node is the grounding-prompt caller that asks for the final
    answer. Each call is recorded.
    """
    calls = []
    grounding = get_settings().agent_system_prompt
    final = synth_reply if synth_reply is not None else worker_reply

    def fake(messages, model, params=None, tools=None):
        calls.append(
            {"messages": messages, "model": model, "params": params, "tools": tools}
        )
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        if "Write the final answer" in messages[-1]["content"]:
            return {"role": "assistant", "content": final, "tool_calls": None}
        return {"role": "assistant", "content": worker_reply, "tool_calls": None}

    return fake, calls


def _node_calls(calls):
    """Split recorded llm.chat calls into (worker, supervisor, synthesize)."""
    grounding = get_settings().agent_system_prompt
    supervisor = [c for c in calls if c["messages"][0]["content"] != grounding]
    synthesize = [
        c
        for c in calls
        if c["messages"][0]["content"] == grounding
        and "Write the final answer" in c["messages"][-1]["content"]
    ]
    worker = [
        c
        for c in calls
        if c["messages"][0]["content"] == grounding and c not in synthesize
    ]
    return worker, supervisor, synthesize


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
    fake, calls = _fake_llm("Hello there.")
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "Hello there.",
        "model": "~deepseek/deepseek-flash-latest",
    }

    # The worker is the first model call; it leads with the system prompt, then the query.
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["messages"][1] == {"role": "user", "content": "hi"}


def test_chat_system_prompt_is_first(monkeypatch):
    """The grounding prompt is the first message the model receives."""
    fake, calls = _fake_llm("ok")
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
    """A query that needs the calculator runs the tool loop inside the worker."""
    grounding = get_settings().agent_system_prompt
    calls = []
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

    def fake(messages, model, params=None, tools=None):
        calls.append(
            {"messages": messages, "model": model, "params": params, "tools": tools}
        )
        if messages[0]["content"] != grounding:
            return {"role": "assistant", "content": "synthesize", "tool_calls": None}
        if "Write the final answer" in messages[-1]["content"]:
            return {"role": "assistant", "content": "3*7+2 is 23.", "tool_calls": None}
        return next(worker_turns)

    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "what is 3*7+2?"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "3*7+2 is 23."

    # The second worker call was handed the tool result, proving the calculator ran.
    worker_calls, _, _ = _node_calls(calls)
    assert len(worker_calls) == 2
    tool_msg = next(m for m in worker_calls[1]["messages"] if m["role"] == "tool")
    assert tool_msg["content"] == "23"


def test_chat_fast_tier_models_and_effort(monkeypatch):
    """Flash: routing and worker on Flash @ low, answer on Flash @ high."""
    fake, calls = _fake_llm("ok")
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    assert client.post("/chat", json={"query": "hi"}).status_code == 200

    worker, supervisor, synthesize = _node_calls(calls)
    assert worker[0]["model"] == "~deepseek/deepseek-flash-latest"
    assert worker[0]["params"] == {"reasoning_effort": "low"}
    assert supervisor[0]["model"] == "~deepseek/deepseek-flash-latest"
    assert supervisor[0]["params"] == {"reasoning_effort": "low"}
    assert synthesize[0]["model"] == "~deepseek/deepseek-flash-latest"
    assert synthesize[0]["params"] == {"reasoning_effort": "high"}


def test_chat_pro_tier_models_and_effort(monkeypatch):
    """Pro spends Pro only on the answer; routing and worker stay on Flash."""
    fake, calls = _fake_llm("ok")
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post(
        "/chat",
        json={"query": "hi", "model": "~deepseek/deepseek-pro-latest"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"] == "~deepseek/deepseek-pro-latest"

    worker, supervisor, synthesize = _node_calls(calls)
    assert supervisor[0]["model"] == "~deepseek/deepseek-flash-latest"
    assert supervisor[0]["params"] == {"reasoning_effort": "low"}
    assert worker[0]["model"] == "~deepseek/deepseek-flash-latest"
    assert worker[0]["params"] == {"reasoning_effort": "low"}
    assert synthesize[0]["model"] == "~deepseek/deepseek-pro-latest"
    assert synthesize[0]["params"] == {"reasoning_effort": "high"}


def test_chat_without_api_key_returns_400(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi"})
    assert resp.status_code == 400
    assert "OPENROUTER_API_KEY" in resp.json()["detail"]


# --- Manual storage (DECISIONS U1) ---


@pytest.fixture
def manuals_dir(tmp_path, monkeypatch):
    """Point storage at a throwaway directory (MANUALS_DIR, cleared per test)."""
    monkeypatch.setenv("MANUALS_DIR", str(tmp_path / "manuals"))
    return tmp_path / "manuals"


def _pdf(name="rhino.pdf", body=b"%PDF-1.4 fake manual"):
    return {"file": (name, body, "application/pdf")}


@pytest.fixture
def no_ingest(monkeypatch):
    """Stub the background ingest so an upload starts without running Docling."""
    scheduled = []
    monkeypatch.setattr(ingest, "ingest_in_background", lambda mid: scheduled.append(mid))
    return scheduled


def test_upload_list_and_get_manual(manuals_dir, no_ingest):
    client = TestClient(app)
    resp = client.post(
        "/manuals",
        files=_pdf(),
        data={
            "vehicle_id": "v1",
            "display_name": "Rhino 700",
            "description": "Full service manual",
        },
    )
    assert resp.status_code == 200
    manual = resp.json()
    assert manual["vehicle_id"] == "v1"
    assert manual["display_name"] == "Rhino 700"
    assert manual["source_filename"] == "rhino.pdf"
    assert manual["description"] == "Full service manual"
    assert manual["status"] == "processing"

    # Upload schedules the ingest pipeline for the new manual.
    assert no_ingest == [manual["manual_id"]]

    # The PDF bytes and the record both landed in a UUID subdirectory.
    manual_dir = manuals_dir / manual["manual_id"]
    assert (manual_dir / "source.pdf").read_bytes() == b"%PDF-1.4 fake manual"
    assert (manual_dir / "manual.json").is_file()

    listing = client.get("/manuals")
    assert listing.status_code == 200
    assert [m["manual_id"] for m in listing.json()] == [manual["manual_id"]]

    fetched = client.get(f"/manuals/{manual['manual_id']}")
    assert fetched.status_code == 200
    assert fetched.json() == manual


def test_get_unknown_manual_returns_404(manuals_dir):
    client = TestClient(app)
    resp = client.get("/manuals/does-not-exist")
    assert resp.status_code == 404


def test_upload_rejects_non_pdf(manuals_dir):
    client = TestClient(app)
    resp = client.post(
        "/manuals",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
        data={"vehicle_id": "v1", "display_name": "Notes"},
    )
    assert resp.status_code == 400
    assert "not a PDF" in resp.json()["detail"]


def test_upload_description_is_optional(manuals_dir, no_ingest):
    client = TestClient(app)
    resp = client.post(
        "/manuals",
        files=_pdf(),
        data={"vehicle_id": "v1", "display_name": "Rhino 700"},
    )
    assert resp.status_code == 200
    assert resp.json()["description"] is None


# --- Manual management: enable, disable, delete (DECISIONS M1/M2) ---


def test_update_manual_toggles_enabled(manuals_dir, no_ingest):
    client = TestClient(app)
    manual = client.post(
        "/manuals",
        files=_pdf(),
        data={"vehicle_id": "v1", "display_name": "Rhino 700"},
    ).json()
    assert manual["enabled"] is True

    resp = client.patch(f"/manuals/{manual['manual_id']}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # The toggle is persisted, not just returned.
    fetched = client.get(f"/manuals/{manual['manual_id']}")
    assert fetched.json()["enabled"] is False

    # And back on again.
    resp = client.patch(f"/manuals/{manual['manual_id']}", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_update_unknown_manual_returns_404(manuals_dir):
    client = TestClient(app)
    resp = client.patch("/manuals/does-not-exist", json={"enabled": False})
    assert resp.status_code == 404


def test_delete_manual(manuals_dir, no_ingest, monkeypatch):
    purged = []
    monkeypatch.setattr(
        retrieval, "delete_manual_index", lambda manual_id: purged.append(manual_id)
    )

    client = TestClient(app)
    manual = client.post(
        "/manuals",
        files=_pdf(),
        data={"vehicle_id": "v1", "display_name": "Rhino 700"},
    ).json()
    manual_dir = manuals_dir / manual["manual_id"]
    assert manual_dir.is_dir()

    resp = client.delete(f"/manuals/{manual['manual_id']}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": manual["manual_id"]}
    assert not manual_dir.exists()
    assert purged == [manual["manual_id"]]
    assert client.get("/manuals").json() == []


def test_delete_unknown_manual_returns_404(manuals_dir):
    client = TestClient(app)
    resp = client.delete("/manuals/does-not-exist")
    assert resp.status_code == 404


# --- Vehicle profiles (SPECIFICATION §5) ---


@pytest.fixture
def vehicles_dir(tmp_path, monkeypatch):
    """Point vehicle storage at a throwaway directory (VEHICLES_DIR)."""
    monkeypatch.setenv("VEHICLES_DIR", str(tmp_path / "vehicles"))
    return tmp_path / "vehicles"


def test_create_and_list_vehicles(vehicles_dir):
    client = TestClient(app)
    resp = client.post("/vehicles", json={"display_name": "2023 Civic"})
    assert resp.status_code == 200
    vehicle = resp.json()
    assert vehicle["display_name"] == "2023 Civic"
    assert vehicle["user_id"] == "default_user"
    assert vehicle["vehicle_id"]

    # The record landed in a UUID subdirectory.
    assert (vehicles_dir / vehicle["vehicle_id"] / "vehicle.json").is_file()

    listing = client.get("/vehicles")
    assert listing.status_code == 200
    assert [v["vehicle_id"] for v in listing.json()] == [vehicle["vehicle_id"]]


def test_list_vehicles_returns_all(vehicles_dir):
    client = TestClient(app)
    first = client.post("/vehicles", json={"display_name": "Subaru"}).json()
    second = client.post("/vehicles", json={"display_name": "Civic"}).json()
    ids = {v["vehicle_id"] for v in client.get("/vehicles").json()}
    assert ids == {first["vehicle_id"], second["vehicle_id"]}


def test_create_vehicle_rejects_blank_name(vehicles_dir):
    client = TestClient(app)
    resp = client.post("/vehicles", json={"display_name": "   "})
    assert resp.status_code == 400
    assert "display_name is required" in resp.json()["detail"]


def test_rename_vehicle(vehicles_dir):
    client = TestClient(app)
    vehicle = client.post("/vehicles", json={"display_name": "Civic"}).json()

    resp = client.patch(
        f"/vehicles/{vehicle['vehicle_id']}",
        json={"display_name": "2023 Civic"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "2023 Civic"
    assert resp.json()["vehicle_id"] == vehicle["vehicle_id"]

    # The rename is persisted, not just returned.
    assert client.get("/vehicles").json()[0]["display_name"] == "2023 Civic"


def test_rename_unknown_vehicle_returns_404(vehicles_dir):
    client = TestClient(app)
    resp = client.patch("/vehicles/does-not-exist", json={"display_name": "X"})
    assert resp.status_code == 404


def test_delete_vehicle(vehicles_dir):
    client = TestClient(app)
    vehicle = client.post("/vehicles", json={"display_name": "Civic"}).json()
    vehicle_dir = vehicles_dir / vehicle["vehicle_id"]
    assert vehicle_dir.is_dir()

    resp = client.delete(f"/vehicles/{vehicle['vehicle_id']}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": vehicle["vehicle_id"]}
    assert not vehicle_dir.exists()
    assert client.get("/vehicles").json() == []


def test_delete_unknown_vehicle_returns_404(vehicles_dir):
    client = TestClient(app)
    resp = client.delete("/vehicles/does-not-exist")
    assert resp.status_code == 404


def test_chat_accepts_vehicle_id(monkeypatch):
    fake, _ = _fake_llm("ok")
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi", "vehicle_id": "v1"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "ok"
