# Noscia API (FastAPI) — dev container for `docker compose up`.
# Heavy by nature: torch + sentence-transformers + crawl4ai's Playwright Chromium.
# The image holds the venv; source (./server/src), corpus, db/init and the model
# cache (./data) are bind-mounted at runtime so edits hot-reload and models persist.
# syntax=docker/dockerfile:1

FROM python:3.12-slim

# uv, pinned to the repo's version (CLAUDE.md ledger).
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/server/.venv \
    HF_HOME=/app/data/models \
    PYTHONUNBUFFERED=1

WORKDIR /app/server

# 1. Dependency layer — cached unless pyproject/uv.lock change. Honors the
#    pinned cooldown via [tool.uv] exclude-newer already in pyproject.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 2. Playwright Chromium + its system libraries (crawl4ai's headless renderer).
#    Call the venv binary directly — `uv run` would try to build the project, whose
#    source isn't copied yet, and we want this large layer independent of src/.
RUN /app/server/.venv/bin/playwright install --with-deps chromium

# 3. Project source + editable install (overlaid by the bind-mount at runtime).
#    README.md is required: pyproject's `readme = "README.md"` is read when the
#    project wheel is built.
COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000
# --reload + --reload-dir watches the bind-mounted source for dev parity.
CMD ["uv", "run", "uvicorn", "noscia.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/server/src"]
