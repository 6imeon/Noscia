"""VectorStore seam (SPEC §9.3) + the Postgres implementation.

App/agent code calls ``store.hybrid_search(...)`` / ``store.upsert(...)`` — never
raw SQL scattered around — so a later dedicated engine (Qdrant) is a contained
swap, not a rewrite. ``PgVectorStore`` (ParadeDB: pgvector + pg_search) is the only
implementation.

The hybrid leg is the well-trodden ParadeDB pattern (IMPLEMENTATION §1): a dense
CTE (pgvector ``<=>`` cosine) and a BM25 CTE (``pg_search`` via ``@@@``) prefetch
top-N each, then **Reciprocal Rank Fusion in SQL** fuses them. Reranking +
highlighting happen one layer up.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .. import db

# Matryoshka-truncated embedding dimensionality (SPEC: 256-dim).
EMBED_DIM = 256

# Hybrid retrieval knobs.
PREFETCH = 100  # candidates pulled per leg (dense, bm25) before fusion
RRF_K = 60  # Reciprocal Rank Fusion constant (standard default)


@dataclass
class Chunk:
    id: str  # stable id; upsert key (content-addressed)
    url: str  # the page this chunk came from (citation target)
    title: str
    text: str
    source_type: str
    dense: list[float]  # EMBED_DIM-length vector
    org: str | None = None
    source_url: str | None = None  # the seed this page was discovered under (deep crawl)
    content_hash: str = ""
    token_count: int | None = None
    fresh: bool = False  # crawled recently (set on read; see SQL)


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fusion score (or dense similarity in Fast tier)


@dataclass
class Fused:
    """Retrieval output + the leg counts the UI shows as the pipeline trace."""

    hits: list[Hit]
    dense_n: int = 0
    bm25_n: int = 0


def _vec_literal(vec: list[float]) -> str:
    """pgvector text input form: ``[0.1,0.2,…]`` (cast to ``vector`` in SQL)."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _row_to_hit(row, score: float) -> Hit:
    return Hit(
        chunk=Chunk(
            id=row.id,
            url=row.url,
            title=row.title,
            text=row.text,
            source_type=row.source_type,
            org=row.org,
            content_hash=getattr(row, "content_hash", ""),
            fresh=bool(getattr(row, "fresh", False)),
            dense=[],  # not re-hydrated on read; not needed downstream
        ),
        score=score,
    )


class VectorStore(ABC):
    """Storage + retrieval for chunks. One impl now (PgVectorStore)."""

    @abstractmethod
    def upsert(self, chunks: list[Chunk]) -> int:
        """Insert/update chunks by id; return the number written."""

    @abstractmethod
    def hybrid_search(self, query: str, dense: list[float], top_k: int) -> Fused:
        """Dense (pgvector) + BM25 (pg_search) prefetch fused with RRF — Quality tier."""

    @abstractmethod
    def dense_search(self, dense: list[float], top_k: int) -> Fused:
        """Dense-only ANN — the low-latency Fast tier."""

    @abstractmethod
    def delete_url(self, url: str) -> int:
        """Drop all chunks for a page (clean re-ingest); return rows removed."""

    @abstractmethod
    def delete_ids(self, ids: list[str]) -> int:
        """Drop specific chunks by id (incremental crawl: prune vanished chunks)."""

    @abstractmethod
    def existing_hashes(self, url: str) -> dict[str, str]:
        """``{chunk_id: content_hash}`` for a page — the diff base for incremental crawl."""

    @abstractmethod
    def prune_pages(self, source_url: str, keep_urls: list[str]) -> int:
        """Deep crawl: drop chunks under a seed whose page URL is no longer reachable.

        After a site recrawl, any page not in ``keep_urls`` has vanished (de-linked or
        gone); remove its chunks. Returns rows removed.
        """

    @abstractmethod
    def count(self) -> int:
        """Total indexed chunks (Corpus view stat / rail counter)."""


_UPSERT_SQL = text(
    """
    INSERT INTO chunks (id, url, source_url, title, org, source_type, text,
                        content_hash, token_count, dense)
    VALUES (:id, :url, :source_url, :title, :org, :source_type, :text, :content_hash, :token_count,
            CAST(:dense AS vector(256)))
    ON CONFLICT (id) DO UPDATE SET
        url = EXCLUDED.url,
        source_url = EXCLUDED.source_url,
        title = EXCLUDED.title,
        org = EXCLUDED.org,
        source_type = EXCLUDED.source_type,
        text = EXCLUDED.text,
        content_hash = EXCLUDED.content_hash,
        token_count = EXCLUDED.token_count,
        dense = EXCLUDED.dense,
        crawled_at = now()
    """
)

# Dense + BM25 prefetch → RRF fuse, all in one round-trip. `:qvec` is the query
# embedding; `:q` drives BM25 (paradedb.match keeps arbitrary query text safe — it's
# a match query, not query-string syntax). FULL OUTER JOIN so a hit found by only
# one leg still survives.
_HYBRID_SQL = text(
    """
    WITH dense AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY dense <=> CAST(:qvec AS vector(256))) AS rnk
        FROM chunks
        ORDER BY dense <=> CAST(:qvec AS vector(256))
        LIMIT :prefetch
    ),
    lexical AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rnk
        FROM chunks
        WHERE id @@@ paradedb.match('text', :q)
        LIMIT :prefetch
    ),
    fused AS (
        SELECT COALESCE(d.id, l.id) AS id,
               COALESCE(1.0 / (:rrf_k + d.rnk), 0.0)
                 + COALESCE(1.0 / (:rrf_k + l.rnk), 0.0) AS rrf,
               (d.id IS NOT NULL) AS in_dense,
               (l.id IS NOT NULL) AS in_lex
        FROM dense d FULL OUTER JOIN lexical l ON d.id = l.id
    )
    SELECT c.id, c.url, c.title, c.org, c.source_type, c.text, c.content_hash,
           (c.crawled_at > now() - interval '7 days') AS fresh,
           f.rrf AS score, f.in_dense, f.in_lex
    FROM fused f JOIN chunks c ON c.id = f.id
    ORDER BY f.rrf DESC
    LIMIT :top_k
    """
)

_DENSE_SQL = text(
    """
    SELECT id, url, title, org, source_type, text, content_hash,
           (crawled_at > now() - interval '7 days') AS fresh,
           1.0 - (dense <=> CAST(:qvec AS vector(256))) AS score
    FROM chunks
    ORDER BY dense <=> CAST(:qvec AS vector(256))
    LIMIT :top_k
    """
)


class PgVectorStore(VectorStore):
    """ParadeDB-backed store: pgvector HNSW (dense) + pg_search BM25 (lexical)."""

    def __init__(self, engine: Engine | None = None):
        self._engine = engine or db.get_engine()

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        params = [
            {
                "id": c.id,
                "url": c.url,
                "source_url": c.source_url,
                "title": c.title,
                "org": c.org,
                "source_type": c.source_type,
                "text": c.text,
                "content_hash": c.content_hash,
                "token_count": c.token_count,
                "dense": _vec_literal(c.dense),
            }
            for c in chunks
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_SQL, params)
        return len(chunks)

    def hybrid_search(self, query: str, dense: list[float], top_k: int) -> Fused:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _HYBRID_SQL,
                {
                    "qvec": _vec_literal(dense),
                    "q": query,
                    "prefetch": PREFETCH,
                    "rrf_k": RRF_K,
                    "top_k": top_k,
                },
            ).all()
        hits = [_row_to_hit(r, float(r.score)) for r in rows]
        dense_n = sum(1 for r in rows if r.in_dense)
        bm25_n = sum(1 for r in rows if r.in_lex)
        return Fused(hits=hits, dense_n=dense_n, bm25_n=bm25_n)

    def dense_search(self, dense: list[float], top_k: int) -> Fused:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _DENSE_SQL, {"qvec": _vec_literal(dense), "top_k": top_k}
            ).all()
        hits = [_row_to_hit(r, float(r.score)) for r in rows]
        return Fused(hits=hits, dense_n=len(hits), bm25_n=0)

    def delete_url(self, url: str) -> int:
        with self._engine.begin() as conn:
            res = conn.execute(text("DELETE FROM chunks WHERE url = :url"), {"url": url})
            return res.rowcount or 0

    def delete_ids(self, ids: list[str]) -> int:
        if not ids:
            return 0
        with self._engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM chunks WHERE id = ANY(:ids)"), {"ids": ids}
            )
            return res.rowcount or 0

    def existing_hashes(self, url: str) -> dict[str, str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, content_hash FROM chunks WHERE url = :url"), {"url": url}
            ).all()
        return {r.id: r.content_hash for r in rows}

    def prune_pages(self, source_url: str, keep_urls: list[str]) -> int:
        with self._engine.begin() as conn:
            res = conn.execute(
                text(
                    "DELETE FROM chunks "
                    "WHERE source_url = :src AND NOT (url = ANY(:keep))"
                ),
                {"src": source_url, "keep": keep_urls},
            )
            return res.rowcount or 0

    def count(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM chunks")).scalar_one())


_store: PgVectorStore | None = None


def get_store() -> PgVectorStore:
    """Process-wide store singleton (the one VectorStore impl)."""
    global _store
    if _store is None:
        _store = PgVectorStore()
    return _store
