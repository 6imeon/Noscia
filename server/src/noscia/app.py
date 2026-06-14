"""FastAPI entrypoint. Run: ``uvicorn noscia.app:app --reload`` (from server/).

Phase 0: a real ``/health`` (pings Postgres) plus contract-valid stubs for
``/search`` and ``/providers`` so the frontend can wire against the HTTP contract
before the pipeline exists.
"""

from __future__ import annotations

from importlib.metadata import version as pkg_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import get_secret, mask
from .contract import (
    HealthResponse,
    PipelineTrace,
    ProviderKeyStatus,
    ProvidersResponse,
    SearchRequest,
    SearchResponse,
)

try:
    VERSION = pkg_version("noscia")
except Exception:  # not installed as a dist (e.g. some test runners)
    VERSION = "0.0.0"

# Vite dev origins (Step 4 wiring). The deployed app is same-origin behind the
# reverse proxy, so this matters only for the local dev loop. Port pinned to 5180
# in web/vite.config.ts to avoid the crowded 5173 default.
DEV_ORIGINS = ["http://localhost:5180", "http://127.0.0.1:5180"]

app = FastAPI(title="Noscia", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = db.ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok, version=VERSION)


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    # Phase 1 fills this in (ingest → hybrid → rerank → highlight). Stub for now:
    # contract-valid empty response so the UI can render empty/loading states.
    return SearchResponse(
        query=req.query,
        tier=req.tier,
        results=[],
        trace=PipelineTrace(dense=0, bm25=0, fused=0, reranked=0),
    )


@app.get("/providers", response_model=ProvidersResponse)
def providers() -> ProvidersResponse:
    # OpenRouter is the one demo secret; others are selectable but optional.
    key = get_secret("openrouter")
    return ProvidersResponse(
        providers=[
            ProviderKeyStatus(
                provider="openrouter",
                configured=bool(key),
                masked=mask(key),
            )
        ],
        default_provider="openrouter",
        default_tier="quality",
    )
