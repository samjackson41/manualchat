"""End-to-end tests for the HTTP API.

These go through the real FastAPI app, the real LangGraph graph, and the real
tool executor. Only the external OpenRouter boundary (`llm.chat`) is stubbed so
the tests are deterministic and need no API key or network.
"""

import json

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


def test_upload_rejects_duplicate_manual_for_same_vehicle(manuals_dir, no_ingest):
    client = TestClient(app)
    first = client.post(
        "/manuals",
        files=_pdf(body=b"%PDF-1.4 same bytes"),
        data={"vehicle_id": "v1", "display_name": "Rhino 700"},
    )
    assert first.status_code == 200

    resp = client.post(
        "/manuals",
        files=_pdf(name="rhino-copy.pdf", body=b"%PDF-1.4 same bytes"),
        data={"vehicle_id": "v1", "display_name": "Rhino 700 again"},
    )
    assert resp.status_code == 409
    # The reply names the already-stored manual.
    assert "already uploaded" in resp.json()["detail"]

    # Only one manual was stored, regardless of the file name difference.
    assert len(no_ingest) == 1
    assert [m["manual_id"] for m in client.get("/manuals").json()] == [
        first.json()["manual_id"]
    ]


def test_upload_allows_same_pdf_for_different_vehicle(manuals_dir, no_ingest):
    client = TestClient(app)
    first = client.post(
        "/manuals",
        files=_pdf(body=b"%PDF-1.4 shared bytes"),
        data={"vehicle_id": "v1", "display_name": "Rhino 700"},
    )
    assert first.status_code == 200

    resp = client.post(
        "/manuals",
        files=_pdf(body=b"%PDF-1.4 shared bytes"),
        data={"vehicle_id": "v2", "display_name": "Same manual, other car"},
    )
    assert resp.status_code == 200
    assert len(no_ingest) == 2


def test_upload_detects_duplicate_of_manual_without_stored_hash(manuals_dir, no_ingest):
    """A manual stored before `content_hash` existed is still caught.

    The digest is computed from the stored PDF when the record carries none.
    """
    client = TestClient(app)
    first = client.post(
        "/manuals",
        files=_pdf(body=b"%PDF-1.4 legacy bytes"),
        data={"vehicle_id": "v1", "display_name": "Legacy manual"},
    ).json()

    # Mimic a record written before the field existed.
    record_path = manuals_dir / first["manual_id"] / "manual.json"
    record = json.loads(record_path.read_text())
    del record["content_hash"]
    record_path.write_text(json.dumps(record))

    resp = client.post(
        "/manuals",
        files=_pdf(body=b"%PDF-1.4 legacy bytes"),
        data={"vehicle_id": "v1", "display_name": "Legacy manual again"},
    )
    assert resp.status_code == 409
    assert len(no_ingest) == 1

    # The computed digest is written back to the old record.
    assert json.loads(record_path.read_text())["content_hash"]


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
    fake, _ = _fake_llm(
        [{"role": "assistant", "content": "ok", "tool_calls": None}]
    )
    monkeypatch.setattr(llm, "chat", fake)

    client = TestClient(app)
    resp = client.post("/chat", json={"query": "hi", "vehicle_id": "v1"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "ok"
