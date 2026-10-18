"""FastAPI app: health, model list, and a chat endpoint that runs the graph.

The `/chat` handler deliberately routes through `agent.graph.graph` rather than
calling `llm.chat` directly — this is what proves the reply went through the
LangGraph graph (the "done when" criterion).
"""

from typing import get_args

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from backend.agent.graph import graph
from backend.config import get_settings, model_label
from backend.llm import LLMError
from backend import ingest
from backend import storage
from backend.schemas import Manual, Vehicle

app = FastAPI(title="ManualChat API", version="0.1.0")

# The Next.js dev server (localhost:3000) calls this API from the browser, so
# allow that origin during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str
    model: str | None = None  # optional per-request override (DECISIONS M3)
    vehicle_id: str | None = None  # scopes the conversation (SPECIFICATION §6)


class VehicleCreate(BaseModel):
    display_name: str


class VehicleUpdate(BaseModel):
    display_name: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/models")
def models() -> dict:
    settings = get_settings()
    return {
        "default": settings.model_default,
        "options": [
            {"id": slug, "label": model_label(slug)} for slug in settings.model_options
        ],
    }


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    model = req.model or get_settings().model_default
    initial_state: dict = {
        "messages": [HumanMessage(content=req.query)],
        "model": model,
        "vehicle_id": req.vehicle_id,
    }
    try:
        result = graph.invoke(initial_state)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reply = result["messages"][-1].content
    return {"reply": reply, "model": model}


# The kinds allowed for an uploaded manual, taken from the `Manual` schema's
# `Literal` so the two cannot drift apart.
_MANUAL_KINDS: set[str] = set(get_args(Manual.model_fields["kind"].annotation))


@app.post("/manuals")
async def create_manual(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    vehicle_id: str = Form(...),
    display_name: str = Form(...),
    kind: str = Form("oem"),
) -> Manual:
    """Store an uploaded manual PDF and run ingest on it in the background.

    The reply returns the manual with `status="processing"`. The background
    task sets `status="ready"` when the pipeline finishes or `status="error"`
    when it fails, so clients poll `GET /manuals/{id}` for the outcome.
    """
    if not vehicle_id.strip():
        raise HTTPException(status_code=400, detail="vehicle_id is required")
    if not display_name.strip():
        raise HTTPException(status_code=400, detail="display_name is required")
    if kind not in _MANUAL_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(_MANUAL_KINDS)}",
        )

    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="file is not a PDF")

    manual = storage.store_manual(
        source_pdf=content,
        vehicle_id=vehicle_id.strip(),
        display_name=display_name.strip(),
        kind=kind,
        source_filename=file.filename or "manual.pdf",
    )
    background_tasks.add_task(ingest.ingest_in_background, manual.manual_id)
    return manual


@app.get("/manuals")
def list_manuals() -> list[Manual]:
    return storage.list_manuals()


@app.get("/manuals/{manual_id}")
def get_manual(manual_id: str) -> Manual:
    manual = storage.get_manual(manual_id)
    if manual is None:
        raise HTTPException(status_code=404, detail="manual not found")
    return manual


# --- Vehicle profiles (SPECIFICATION §5) ---


@app.get("/vehicles")
def list_vehicles() -> list[Vehicle]:
    return storage.list_vehicles()


@app.post("/vehicles")
def create_vehicle(req: VehicleCreate) -> Vehicle:
    display_name = req.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    return storage.store_vehicle(display_name)


@app.patch("/vehicles/{vehicle_id}")
def rename_vehicle(vehicle_id: str, req: VehicleUpdate) -> Vehicle:
    display_name = req.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    vehicle = storage.rename_vehicle(vehicle_id, display_name)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    return vehicle


@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: str) -> dict:
    if not storage.delete_vehicle(vehicle_id):
        raise HTTPException(status_code=404, detail="vehicle not found")
    return {"deleted": vehicle_id}