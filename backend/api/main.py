"""FastAPI app: health, model list, and a chat endpoint that runs the graph.

The `/chat` handler deliberately routes through `agent.graph.graph` rather than
calling `llm.chat` directly — this is what proves the reply went through the
LangGraph graph (the "done when" criterion).
"""

import hashlib
import json

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from backend.agent.graph import ask, graph
from backend.config import get_settings, model_label
from backend.llm import LLMError
from backend import ingest
from backend import retrieval
from backend import slicer
from backend import storage
from backend import thumbnails
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


class ManualUpdate(BaseModel):
    enabled: bool


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
    try:
        reply = ask(req.query, model=req.model, vehicle_id=req.vehicle_id)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"reply": reply, "model": model}


@app.post("/manuals")
async def create_manual(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    vehicle_id: str = Form(...),
    display_name: str = Form(...),
    description: str = Form(""),
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

    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="file is not a PDF")

    manual = storage.store_manual(
        source_pdf=content,
        vehicle_id=vehicle_id.strip(),
        display_name=display_name.strip(),
        description=description.strip() or None,
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


def _slice_etag(manual_id: str, start: int, end: int) -> str:
    """A strong ETag for one slice, from the stored PDF and the range.

    PyMuPDF stamps a fresh document id when it re-serialises the pages, so the
    slice bytes are not stable between requests. The manual's stored PDF and
    the page range are stable, because a manual never changes after upload
    (DECISIONS U1, V5).
    """
    stat = (storage.manual_dir(manual_id) / "source.pdf").stat()
    seed = f"{manual_id}:{start}-{end}:{stat.st_size}:{stat.st_mtime_ns}"
    return '"' + hashlib.sha256(seed.encode()).hexdigest()[:32] + '"'


def _viewer_cache_headers(etag: str | None = None) -> dict[str, str]:
    """Headers for the stored page bytes, which never change after upload."""
    max_age = get_settings().viewer_cache_max_age_seconds
    headers = {"Cache-Control": f"public, max-age={max_age}, immutable"}
    if etag is not None:
        headers["ETag"] = etag
    return headers


@app.get("/manuals/{manual_id}/pages/{page_range}")
def get_page_slice(
    manual_id: str, page_range: str, request: Request
) -> Response:
    """Serve a PDF holding one manual's pages ``start-end`` (DECISIONS V1).

    ``page_range`` looks like ``80-84``; both ends are inclusive 1-indexed
    physical PDF pages. The viewer asks for the pages around the page an
    answer cites, so it can render a small slice with selectable text.
    """
    try:
        start_s, end_s = page_range.split("-", 1)
        start, end = int(start_s), int(end_s)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="page range must be start-end"
        ) from None

    if storage.get_manual(manual_id) is None:
        raise HTTPException(status_code=404, detail="manual not found")

    try:
        data = slicer.slice_pages(manual_id, start, end)
    except slicer.SliceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    etag = _slice_etag(manual_id, start, end)
    headers = _viewer_cache_headers(etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=data, media_type="application/pdf", headers=headers
    )


@app.get("/manuals/{manual_id}/pdf")
def get_manual_pdf(manual_id: str) -> FileResponse:
    """Serve the manual's whole stored PDF (DECISIONS V2).

    The viewer shows the full manual on demand, so the reader can read it in
    the app. The bytes are the uploaded ``source.pdf``, streamed as-is.
    """
    if storage.get_manual(manual_id) is None:
        raise HTTPException(status_code=404, detail="manual not found")
    source = storage.manual_dir(manual_id) / "source.pdf"
    if not source.is_file():
        raise HTTPException(status_code=404, detail="source.pdf is missing")
    return FileResponse(
        source,
        media_type="application/pdf",
        headers=_viewer_cache_headers(),
    )


@app.patch("/manuals/{manual_id}")
def update_manual(manual_id: str, req: ManualUpdate) -> Manual:
    manual = storage.update_manual(manual_id, enabled=req.enabled)
    if manual is None:
        raise HTTPException(status_code=404, detail="manual not found")
    return manual


@app.delete("/manuals/{manual_id}")
def delete_manual(manual_id: str) -> dict:
    """Purge the manual's indexed chunks, then remove it and its directory.

    The purge runs first so a failure there leaves the record in place to
    retry; deleting the record first would strand searchable chunks.
    """
    if storage.get_manual(manual_id) is None:
        raise HTTPException(status_code=404, detail="manual not found")
    retrieval.delete_manual_index(manual_id)
    storage.delete_manual(manual_id)
    return {"deleted": manual_id}


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


# --- Manual viewer: page thumbnails (IMPLEMENTATION Task 5) ---


@app.get("/manuals/{manual_id}/thumbnails/{page}")
def get_page_thumbnail(manual_id: str, page: int) -> Response:
    """Serve one manual page as a raster PNG (IMPLEMENTATION §7 fallback).

    ``page`` is a 1-indexed physical PDF page. The resolution is the
    ``thumbnail_dpi`` config value, so a client can tune it without code edits.
    """
    if storage.get_manual(manual_id) is None:
        raise HTTPException(status_code=404, detail="manual not found")
    try:
        png = thumbnails.thumbnail_png(
            manual_id, page, get_settings().thumbnail_dpi
        )
    except thumbnails.ThumbnailError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


# --- Streaming chat (SSE) ---


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Stream the graph's reply as SSE JSON chunks (IMPLEMENTATION Task 5).

    Each event carries one JSON object on a ``data:`` line. Content arrives as
    ``{"type": "token", "content": "..."}``, then a final
    ``{"type": "done", "content": "<full reply>", "model": "<slug>"}``. An early
    failure ends the stream with ``{"type": "error", "message": "..."}``.
    """
    model = req.model or get_settings().model_default
    initial_state = {
        "messages": [HumanMessage(content=req.query)],
        "model": model,
        "vehicle_id": req.vehicle_id,
        "stream": True,
        "gathered": [],
        "next": "",
        "hops": 0,
    }

    def event_stream():
        parts: list[str] = []
        try:
            for chunk in graph.stream(initial_state, stream_mode="custom"):
                if isinstance(chunk, dict) and chunk.get("type") == "token":
                    parts.append(chunk["content"])
                    yield f"data: {json.dumps(chunk)}\n\n"
            done = {"type": "done", "content": "".join(parts), "model": model}
            yield f"data: {json.dumps(done)}\n\n"
        except LLMError as exc:
            err = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")