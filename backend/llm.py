"""Thin OpenRouter wrapper — the ONLY module that talks to OpenRouter directly.

Chosen over the `openai` SDK to keep the dependency surface lean: a single
`httpx.post` to the OpenAI-compatible chat-completions endpoint is all we need
for the skeleton. When RAG/tool-calling lands, this is the one place to swap in
a streaming client or the full SDK without touching the graph.
"""

import httpx

from backend.config import get_settings


class LLMError(RuntimeError):
    """Raised when the OpenRouter call fails or the secret is missing."""


def _sampling_params() -> dict:
    """Build the sampling params dict from config, omitting unset values.

    Only non-None, non-empty values are forwarded, so MODEL_TEMPERATURE /
    MODEL_MAX_TOKENS (TBD) are simply left to the provider default until a
    value is chosen.
    """
    settings = get_settings()
    candidates = {
        "reasoning_effort": settings.model_reasoning_effort,
        "temperature": settings.model_temperature,
        "max_tokens": settings.model_max_tokens,
    }
    return {key: value for key, value in candidates.items() if value not in (None, "")}


def chat(
    messages: list[dict],
    model: str,
    params: dict | None = None,
    tools: list[dict] | None = None,
) -> dict:
    """Send a chat request to OpenRouter and return the assistant's message.

    Args:
        messages: OpenAI-shaped `[{"role": "user"|"assistant"|"system"|"tool", "content": str}]`.
        model:    OpenRouter slug (e.g. "~deepseek/deepseek-flash-latest").
        params:   Optional per-call sampling overrides, merged over config defaults.
        tools:    Optional OpenAI function-calling schemas to offer the model.

    Returns:
        The assistant message dict, shaped like OpenAI's `choices[0].message`:
        `{"role": "assistant", "content": str|None, "tool_calls": list|None}`.
        `tool_calls` is present only when the model asks to run a tool.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise LLMError(
            "OPENROUTER_API_KEY is not set. Export it in the shell before starting "
            "the backend, e.g.: OPENROUTER_API_KEY=sk-or-... docker compose up backend"
        )

    body: dict = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    body.update(_sampling_params())
    if params:
        body.update({k: v for k, v in params.items() if v not in (None, "")})

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}

    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120.0)
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenRouter request failed: {exc}") from exc

    if resp.is_error:
        raise LLMError(f"OpenRouter error {resp.status_code}: {resp.text}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected OpenRouter response shape: {data}") from exc