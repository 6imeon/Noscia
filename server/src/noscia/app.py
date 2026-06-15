"""FastAPI entrypoint. Run: ``uvicorn noscia.app:app --reload`` (from server/).

Phase 0: a real ``/health`` (pings Postgres) plus contract-valid stubs for
``/search`` and ``/providers`` so the frontend can wire against the HTTP contract
before the pipeline exists.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import corpus, db
from . import user as user_mod
from .config import get_secret, mask
from .contract import (
    AddSeedRequest,
    CorpusResponse,
    CorpusSource,
    CorpusStats,
    HealthResponse,
    IndustriesResponse,
    Industry,
    IngestRequest,
    IngestResponse,
    ProviderKeyStatus,
    ProvidersResponse,
    RemoveSeedRequest,
    RemoveSeedResponse,
    SearchRequest,
    SearchResponse,
    SelectIndustryRequest,
    StructuredRequest,
    StructuredResponse,
    Tier,
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


# A tiny in-process cache of the last few retrievals, keyed by (industry, query, tier).
# The Structured tab fires right after a search with the same query, so this lets it reuse
# the retrieval instead of re-running the whole embed+rerank pipeline (the ~1 min the
# user saw). The industry is part of the key so two verticals' identical queries never
# collide. Snapshots are answer-free deep copies, so a cached entry never leaks a stale
# synthesized answer. dev == prod single process, so a module-level cache is enough.
_SEARCH_CACHE: OrderedDict[tuple[str, str, str], SearchResponse] = OrderedDict()
_SEARCH_CACHE_MAX = 32


def _remember(industry: str, resp: SearchResponse) -> None:
    key = (industry, resp.query, resp.tier)
    _SEARCH_CACHE[key] = resp.model_copy(deep=True)
    _SEARCH_CACHE.move_to_end(key)
    while len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
        _SEARCH_CACHE.popitem(last=False)


def _recall(industry: str, query: str, tier: Tier) -> SearchResponse | None:
    key = (industry, query, tier)
    hit = _SEARCH_CACHE.get(key)
    if hit is not None:
        _SEARCH_CACHE.move_to_end(key)
    return hit


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    # embed → (hybrid+rerank | dense) → highlight. See search/pipeline.py.
    resp = run_search(req)
    # answer-free snapshot for a follow-up /structured on the same query+vertical
    _remember(req.industry, resp)
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


@app.post("/structured", response_model=StructuredResponse)
async def structured(req: StructuredRequest) -> StructuredResponse:
    """BYOK structured extraction: run the same search, then return the answer as typed,
    cited fields from the top passages — null when unsupported (rule 8). AUTO mode (no
    fields requested) derives the salient fields from the query so Structured mirrors the
    prose Answer; MANUAL mode fills exactly the pinned fields. See search/structured.py.
    Stateless: re-runs the pipeline so [n] maps to the returned results regardless of what
    the client last searched."""
    from .search import structured as st

    # Reuse the just-run retrieval when the query+vertical match (the common case —
    # Structured fires right after a search), else run it. Avoids embed+rerank twice.
    resp = _recall(req.industry, req.query, req.tier) or run_search(
        SearchRequest(query=req.query, tier=req.tier, industry=req.industry)
    )
    passages = [_passage_text(r.highlight) for r in resp.results[: st.DEFAULT_TOP_N]]
    auto = not req.fields
    fields = (
        await st.auto_extract(req.query, passages)
        if auto
        else await st.extract_structured(req.query, passages, req.fields)
    )
    return StructuredResponse(
        query=req.query,
        tier=req.tier,
        results=resp.results,
        fields=fields,
        extracted=bool(get_secret("openrouter")),
        auto=auto,
    )


@app.get("/corpus", response_model=CorpusResponse)
def corpus_state(industry: str = "esg") -> CorpusResponse:
    # Scoped to the active vertical so the Corpus view never mixes verticals.
    return CorpusResponse(
        stats=CorpusStats(**corpus.stats(industry)),
        sources=[CorpusSource(**s) for s in corpus.list_sources(industry)],
        industry=industry,
    )


@app.post("/corpus/ingest", response_model=IngestResponse)
async def corpus_ingest(req: IngestRequest) -> IngestResponse:
    seeds = ingest.register_seeds(req.industry)
    if req.urls:
        wanted = set(req.urls)
        specs = [s for s in seeds if s["url"] in wanted]
    else:
        specs = seeds
    summary = await ingest.ingest_specs(specs, industry=req.industry)
    return IngestResponse(
        ok=summary["ok"],
        indexed_pages=summary["indexed_pages"],
        chunks=summary["chunks"],
        errors=[f"{e['url']}: {e['error']}" for e in summary["errors"]],
    )


@app.post("/corpus/add", response_model=IngestResponse)
async def corpus_add(req: AddSeedRequest) -> IngestResponse:
    corpus.upsert_source(req.url, req.source_type, req.org, req.cadence, req.industry)
    spec = {"url": req.url, "source_type": req.source_type, "org": req.org, "cadence": req.cadence}
    summary = await ingest.ingest_specs([spec], industry=req.industry)
    return IngestResponse(
        ok=summary["ok"],
        indexed_pages=summary["indexed_pages"],
        chunks=summary["chunks"],
        errors=[f"{e['url']}: {e['error']}" for e in summary["errors"]],
    )


@app.post("/corpus/remove", response_model=RemoveSeedResponse)
def corpus_remove(req: RemoveSeedRequest) -> RemoveSeedResponse:
    """Remove a seed and all the chunks it produced from a vertical (industry-scoped).
    The client confirms the chunk count first — removal throws away crawl+embed work that
    re-adding re-pays (MULTI_INDUSTRY.md §5.7)."""
    removed = corpus.delete_source(req.url, req.industry)
    return RemoveSeedResponse(ok=True, removed_chunks=removed)


def _industries_for(user: user_mod.User) -> IndustriesResponse:
    """Catalog (corpus/industries.yaml) ⨯ this user's state: each entry marked `loaded`
    (crawled) and `active` (the user's current pick). The shared body of both endpoints."""
    active = user_mod.get_active_industry(user)
    loaded = corpus.industries_loaded()
    items = [
        Industry(
            id=c["id"],
            label=c["label"],
            blurb=c.get("blurb", ""),
            icon=c.get("icon", ""),
            active=(c["id"] == active),
            loaded=(c["id"] in loaded),
        )
        for c in ingest.load_industries()
    ]
    return IndustriesResponse(industries=items, active=active)


@app.get("/industries", response_model=IndustriesResponse)
def industries_list(request: Request) -> IndustriesResponse:
    """The setup menu / switcher source: the catalog plus which vertical is loaded/active."""
    return _industries_for(user_mod.current_user(request))


@app.post("/industries/select", response_model=IndustriesResponse)
def industries_select(req: SelectIndustryRequest, request: Request) -> IndustriesResponse:
    """Set the caller's active vertical, then return the refreshed catalog. The client kicks
    off ingest when the chosen vertical isn't yet `loaded` (MULTI_INDUSTRY.md §5.5)."""
    if req.id not in {c["id"] for c in ingest.load_industries()}:
        raise HTTPException(status_code=404, detail=f"unknown industry '{req.id}'")
    user = user_mod.current_user(request)
    user_mod.set_active_industry(user, req.id)
    return _industries_for(user)


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
