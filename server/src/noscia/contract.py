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


class SearchResponse(BaseModel):
    query: str
    tier: Tier
    results: list[SearchResult]
    trace: PipelineTrace


# --- /providers (BYOK key status; never the raw key) ---------------------
class ProviderKeyStatus(BaseModel):
    provider: str  # "openrouter" | "anthropic" | "openai" | "ollama"
    configured: bool
    masked: str  # masked confirmation only — never the raw key


class ProvidersResponse(BaseModel):
    providers: list[ProviderKeyStatus]
    default_provider: str
    default_tier: Tier
