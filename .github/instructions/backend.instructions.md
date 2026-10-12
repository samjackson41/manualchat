---
name: Backend
description: Rules for changes under backend/ (Python, FastAPI, LangGraph, uv).
applyTo: backend/**
---

# Backend

- Config is env vars only via pydantic-settings. Reuse `get_settings()` from
  `backend/config.py`. No `.env` file.
- One LangGraph node does one job. Model calls go only in `backend/llm.py`.
- Add deps with `uv add` from `backend/`. Commit `uv.lock`.
- Before you finish, run:
  `cd backend && uv run python -m compileall -q agent api config.py llm.py __init__.py`