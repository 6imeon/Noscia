"""The stable HTTP contract (SPEC §2 rule 3 / §11).

Pydantic models for the Phase 0/1 endpoints. These are mirrored 1:1 in
``web/src/lib/api.ts`` — the two must match exactly. Change this file and the
TS mirror together, never one alone.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Tier = Literal["fast", "quality"]

# Single source of truth for source-type strings; the frontend maps these to
# the §8.2 color tokens. Keep in sync with corpus seed `source_type` values.
SourceType = Literal["framework", "regulator", "ratings", "report", "ngo", "news"]


# --- /health -------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool  # Postgres reachable (SELECT 1)
    version: str


# --- /search -------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    tier: Tier = "quality"
    top_k: int = Field(default=20, ge=1, le=100)
    # Opt-in, BYOK: synthesize a query-focused answer per top result. Silently
    # ignored (summaries stay null) when no reasoning key is configured.
    summarize: bool = False


class PipelineTrace(BaseModel):
    """The retrieval trace shown in the result header (§8.4):
    `dense 112 + bm25 98 → rrf → rerank 50`."""

    dense: int
    bm25: int
    fused: int
    reranked: int


class SearchResult(BaseModel):
    rank: int
    url: str
    title: str
    org: str | None = None
    source_type: SourceType
    score: float
    highlight: str  # best-matching passage; may contain <mark>…</mark> spans
    fresh: bool = False
    summary: str | None = None  # BYOK query-focused answer (only when `summarize` asked)


class SearchResponse(BaseModel):
    query: str
    tier: Tier
    results: list[SearchResult]
    trace: PipelineTrace
    summarized: bool = False  # AI summaries actually ran (a reasoning key was configured)


# --- /corpus (index stats + sources; Corpus view §8.4) -------------------
class CorpusStats(BaseModel):
    chunks: int  # total indexed passages
    sources: int  # registered seed URLs
    pages: int  # crawled pages
    index_bytes: int  # pg_total_relation_size('chunks')
    embed_model: str
    embed_dims: int


class CorpusSource(BaseModel):
    url: str
    source_type: SourceType
    org: str | None = None
    cadence: str
    status: Literal["idle", "crawling", "done", "error"]
    pages: int
    chunks: int
    last_crawl: str | None = None  # ISO-8601
    error: str | None = None


class CorpusResponse(BaseModel):
    stats: CorpusStats
    sources: list[CorpusSource]


class AddSeedRequest(BaseModel):
    url: str = Field(min_length=1)
    source_type: SourceType
    org: str | None = None
    cadence: str = "monthly"


class IngestRequest(BaseModel):
    # Omit `urls` to (re)ingest every registered seed.
    urls: list[str] | None = None


class IngestResponse(BaseModel):
    ok: bool
    indexed_pages: int
    chunks: int
    errors: list[str] = Field(default_factory=list)


# --- /providers (BYOK key status; never the raw key) ---------------------
class ProviderKeyStatus(BaseModel):
    provider: str  # "openrouter" | "anthropic" | "openai" | "ollama"
    configured: bool
    masked: str  # masked confirmation only — never the raw key


class ProvidersResponse(BaseModel):
    providers: list[ProviderKeyStatus]
    default_provider: str
    default_tier: Tier
