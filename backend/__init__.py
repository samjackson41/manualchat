"""ManualChat backend package.

Layout (matches IMPLEMENTATION.md conventions):
    config.py      -> Pydantic BaseSettings, env-var only (no .env in repo)
    llm.py         -> thin OpenRouter wrapper (httpx, no OpenAI SDK)
    agent/graph.py -> minimal LangGraph StateGraph (the iteration point)
    api/main.py    -> FastAPI routes
"""