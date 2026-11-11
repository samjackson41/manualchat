# Slim serving image for Cloud Run. Carries only the serving dependencies —
# the `ingest` group (Docling, torchvision) is omitted, so this image cannot
# run ingest. It serves, searches, and imports preprocessed zips (DEPLOYMENT M1).

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.11-slim

# uv binaries from the official image.
COPY --from=uv /uv /uvx /bin/

WORKDIR /app

# `backend` is the Python package, copied to /app/backend below; its parent is
# on PYTHONPATH so `import backend` resolves.
ENV PYTHONPATH=/app \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Serving dependencies only: no dev group, no ingest group.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-group ingest

# The package source (the build context is `backend/`).
COPY . ./backend

# The service is stateless — it reads and writes GCS and Qdrant Cloud, never
# local disk — so it runs as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080

CMD exec /app/.venv/bin/uvicorn backend.api.main:app --host 0.0.0.0 --port "${PORT:-8080}"
