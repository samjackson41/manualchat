# Build and run the ManualChat backend with uv + uvicorn hot-reload.
# Source (`backend/` = the package) is bind-mounted at run time for --reload;
# the image just carries the resolved dependencies.

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.11-slim

# uv binaries from the official image.
COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# `backend` is the Python package (its __init__.py/config.py/... live directly
# in the mounted source dir), so its PARENT (/app) is on PYTHONPATH.
ENV PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install dependencies (layer-cached). The package itself is NOT installed —
# `[tool.uv] package = false` — and the source is bind-mounted by compose, so
# there is no `COPY backend` here.
COPY pyproject.toml uv.lock ./
# Persist uv's download cache across builds so a changed uv.lock re-resolves
# from already-downloaded wheels instead of fetching them again.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/backend"]