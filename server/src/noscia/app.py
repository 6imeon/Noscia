"""FastAPI entrypoint. Run: ``uvicorn noscia.app:app --reload`` (from server/).

Phase 0: a real ``/health`` (pings Postgres) plus contract-valid stubs for
``/search`` and ``/providers`` so the frontend can wire against the HTTP contract
before the pipeline exists.
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import corpus, db
from .config import get_secret, mask
from .contract import (
    AddSeedRequest,
    CorpusResponse,
    CorpusSource,
    CorpusStats,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    ProviderKeyStatus,
    ProvidersResponse,
    SearchRequest,
    SearchResponse,
)
from .ingest import run as ingest
from .search.pipeline import run_search

try:
    VERSION = pkg_version("noscia")
except Exception:  # not installed as a dist (e.g. some test runners)
    VERSION = "0.0.0"

# Vite dev origins (Step 4 wiring). The deployed app is same-origin behind the
# reverse proxy, so this matters only for the local dev loop. Port pinned to 5180
# in web/vite.config.ts to avoid the crowded 5173 default.
DEV_ORIGINS = ["http://localhost:5180", "http://127.0.0.1:5180"]

def _prewarm_models() -> None:
    """Load the embedder + cross-encoder off the request path (see search/embed.py,
    rerank.py). The models are lazy + ``lru_cache``'d, so without this the *first*
    search pays the full ≈1 GB cold-start (minutes on CPU). Loading them here at boot
    moves that cost off the user's first query. Best-effort: a missing model cache
    logs and returns — it must never crash the API."""
    import time

    from .search import embed, rerank

    t0 = time.perf_counter()
    try:
        embed.warm()
        rerank.warm()
    except Exception as exc:  # noqa: BLE001 — warmup is best-effort, never fatal
        print(f"[prewarm] search models failed to load: {type(exc).__name__}: {exc}")
        return
    print(f"[prewarm] search models ready in {time.perf_counter() - t0:.0f}s")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Idempotent: ensure the schema exists and seeds are registered for the
    # Corpus view even before the first crawl. Never blocks on model loading.
    try:
        db.init_schema()
        ingest.register_seeds()
    except Exception:  # a missing DB shouldn't stop the API from booting
        pass
    # Warm the search models in the background so boot stays instant and the first
    # search is as fast as the rest. Skipped under pytest (tests never load models).
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        threading.Thread(target=_prewarm_models, name="model-prewarm", daemon=True).start()
    yield


app = FastAPI(title="Noscia", version=VERSION, lifespan=lifespan)
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
async def search(req: SearchRequest) -> SearchResponse:
    # embed → (hybrid+rerank | dense) → highlight. See search/pipeline.py.
    resp = run_search(req)
    if req.summarize:
        resp = await _attach_answer(req.query, resp)
    return resp


async def _attach_answer(query: str, resp: SearchResponse) -> SearchResponse:
    """BYOK, opt-in: synthesize one grounded answer over the top results' passages.

    Sees the top passages together (the answer is often split across them), cites the
    rows it used, and stays honest — null when the corpus doesn't answer (rule 8). No
    key configured ⇒ answer null and ``summarized`` False, so the UI falls back to the
    cited passages rather than erroring. See search/summarize.py.
    """
    from .search import summarize as summ

    passages = [_passage_text(r.highlight) for r in resp.results[: summ.DEFAULT_TOP_N]]
    answer, citations = await summ.synthesize_answer(query, passages)
    resp.answer = answer
    resp.answer_citations = citations
    resp.summarized = bool(get_secret("openrouter"))
    return resp


def _passage_text(highlight: str) -> str:
    """The plain-text passage behind a highlight — drop <mark> spans, unescape entities."""
    import html
    import re

    return html.unescape(re.sub(r"</?mark>", "", highlight))


@app.get("/corpus", response_model=CorpusResponse)
def corpus_state() -> CorpusResponse:
    return CorpusResponse(
        stats=CorpusStats(**corpus.stats()),
        sources=[CorpusSource(**s) for s in corpus.list_sources()],
    )


@app.post("/corpus/ingest", response_model=IngestResponse)
async def corpus_ingest(req: IngestRequest) -> IngestResponse:
    seeds = ingest.register_seeds()
    if req.urls:
        wanted = set(req.urls)
        specs = [s for s in seeds if s["url"] in wanted]
    else:
        specs = seeds
    summary = await ingest.ingest_specs(specs)
    return IngestResponse(
        ok=summary["ok"],
        indexed_pages=summary["indexed_pages"],
        chunks=summary["chunks"],
        errors=[f"{e['url']}: {e['error']}" for e in summary["errors"]],
    )


@app.post("/corpus/add", response_model=IngestResponse)
async def corpus_add(req: AddSeedRequest) -> IngestResponse:
    corpus.upsert_source(req.url, req.source_type, req.org, req.cadence)
    spec = {"url": req.url, "source_type": req.source_type, "org": req.org, "cadence": req.cadence}
    summary = await ingest.ingest_specs([spec])
    return IngestResponse(
        ok=summary["ok"],
        indexed_pages=summary["indexed_pages"],
        chunks=summary["chunks"],
        errors=[f"{e['url']}: {e['error']}" for e in summary["errors"]],
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
