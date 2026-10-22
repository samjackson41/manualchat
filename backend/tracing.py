"""LangSmith tracing for the OpenRouter wrapper (MVP+1 monitoring).

One LangSmith ``llm`` run per model call. Each run carries the model slug,
the token usage, the wall-clock latency, and any error. Tracing stays off
until ``LANGSMITH_TRACING=true`` and ``LANGSMITH_API_KEY`` are both set
(backend/config.py). A failed post is dropped rather than raised, so an
unreachable LangSmith never breaks the chat.
"""

from datetime import datetime, timezone

from langsmith import Client

from backend.config import get_settings


def record(
    *,
    name: str,
    model: str,
    messages: list[dict],
    started: datetime,
    ended: datetime,
    output: object = None,
    usage: dict | None = None,
    error: str | None = None,
    client: Client | None = None,
) -> None:
    """Post one LLM run to LangSmith, swallowing any recording failure."""
    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return

    if client is None:
        client = Client(
            api_key=settings.langsmith_api_key,
            api_url=settings.langsmith_endpoint,
        )

    usage = usage or {}
    run_fields: dict = {
        "name": name,
        "inputs": {"model": model, "messages": messages},
        "run_type": "llm",
        "project_name": settings.langsmith_project,
        "start_time": started,
        "end_time": ended,
        "extra": {
            "metadata": {
                "model": model,
                "latency_ms": round((ended - started).total_seconds() * 1000),
            }
        },
    }
    if output is not None:
        run_fields["outputs"] = {"output": output}
    if error:
        run_fields["error"] = error
    if usage.get("prompt_tokens") is not None:
        run_fields["prompt_tokens"] = usage["prompt_tokens"]
    if usage.get("completion_tokens") is not None:
        run_fields["completion_tokens"] = usage["completion_tokens"]
    if usage.get("total_tokens") is not None:
        run_fields["total_tokens"] = usage["total_tokens"]

    try:
        client.create_run(**run_fields)
    except Exception:
        # LangSmith is best-effort; a failed post must not break the chat.
        pass