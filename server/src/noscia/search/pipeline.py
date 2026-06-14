"""Search pipeline — the Quality / Fast tiers wired end to end (SPEC §4, §8.4).

    Quality : embed → hybrid (dense + BM25, RRF) → cross-encoder rerank → highlight
    Fast    : embed → dense-only ANN → highlight        (rerank skipped, <200ms target)

Returns a contract ``SearchResponse`` with the pipeline trace the UI header shows
(`dense 112 + bm25 98 → rrf → rerank 50`). This is the only place that composes the
retrieval steps; ``/search`` in app.py just calls ``run_search``.
"""

from __future__ import annotations

from typing import cast

from ..contract import (
    PipelineTrace,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SourceType,
)
from . import rerank as rerank_mod
from .embed import embed_query
from .highlight import highlight
from .store import Fused, Hit, get_store

# Quality tier reranks this many fused candidates down to req.top_k.
RERANK_CANDIDATES = 50


def _to_results(query: str, hits: list[Hit]) -> list[SearchResult]:
    results: list[SearchResult] = []
    for i, h in enumerate(hits, start=1):
        c = h.chunk
        results.append(
            SearchResult(
                rank=i,
                url=c.url,
                title=c.title or c.url,
                org=c.org,
                source_type=cast(SourceType, c.source_type),
                score=round(h.score, 4),
                highlight=highlight(query, c.text),
                fresh=c.fresh,
            )
        )
    return results


def run_search(req: SearchRequest) -> SearchResponse:
    qvec = embed_query(req.query)

    if req.tier == "fast":
        fused: Fused = get_store().dense_search(qvec, req.top_k)
        hits = fused.hits
        trace = PipelineTrace(
            dense=fused.dense_n, bm25=0, fused=len(hits), reranked=0
        )
    else:  # quality
        fused = get_store().hybrid_search(req.query, qvec, RERANK_CANDIDATES)
        hits = rerank_mod.rerank(req.query, fused.hits, req.top_k)
        trace = PipelineTrace(
            dense=fused.dense_n,
            bm25=fused.bm25_n,
            fused=len(fused.hits),
            reranked=len(hits),
        )

    return SearchResponse(
        query=req.query,
        tier=req.tier,
        results=_to_results(req.query, hits),
        trace=trace,
    )
