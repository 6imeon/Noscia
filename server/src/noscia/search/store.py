"""VectorStore seam (SPEC §9.3).

App/agent code calls ``store.hybrid_search(...)`` / ``store.upsert(...)`` — never
raw SQL scattered around — so a later dedicated engine (Qdrant) is a contained
swap, not a rewrite. ``PgVectorStore`` (Postgres: pgvector + pg_search) is the
only implementation; it lands in Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Matryoshka-truncated embedding dimensionality (SPEC: 256-dim).
EMBED_DIM = 256


@dataclass
class Chunk:
    id: str  # stable id; upsert key
    url: str
    title: str
    text: str
    source_type: str
    dense: list[float]  # EMBED_DIM-length vector


@dataclass
class Hit:
    chunk: Chunk
    score: float


class VectorStore(ABC):
    """Storage + retrieval for chunks. One impl now (PgVectorStore)."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk]) -> int:
        """Insert/update chunks by id; return the number written."""

    @abstractmethod
    def hybrid_search(self, query: str, dense: list[float], top_k: int) -> list[Hit]:
        """Dense (pgvector) + BM25 (pg_search) prefetch fused with RRF.

        ``query`` drives the BM25 leg; ``dense`` is the query embedding for the
        vector leg. Reranking + highlighting happen above this layer.
        """
