"""FastAPI app: health, model list, and a chat endpoint that runs the graph.

The `/chat` handler deliberately routes through `agent.graph.graph` rather than
calling `llm.chat` directly — this is what proves the reply went through the
LangGraph graph (the "done when" criterion).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from backend.agent.graph import graph
from backend.config import get_settings, model_label
from backend.llm import LLMError

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
    }
    try:
        result = graph.invoke(initial_state)
    except LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reply = result["messages"][-1].content
    return {"reply": reply, "model": model}