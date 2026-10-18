"""ManualChat backend package.

Layout (matches IMPLEMENTATION.md conventions):
    config.py      -> Pydantic BaseSettings, env-var only (no .env in repo)
    llm.py         -> thin OpenRouter wrapper (httpx, no OpenAI SDK)
    tools.py       -> agent tools (schemas + executors) for tool calling / RAG
    retrieval.py   -> chunking, embedding, reranking, Qdrant index/search
    agent/graph.py -> LangGraph StateGraph with a chat -> tools -> chat loop
    api/main.py    -> FastAPI routes
"""