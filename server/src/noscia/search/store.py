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
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .. import db

# Matryoshka-truncated embedding dimensionality (SPEC: 256-dim).
EMBED_DIM = 256

# Hybrid retrieval knobs.
PREFETCH = 100  # candidates pulled per leg (dense, bm25) before fusion
RRF_K = 60  # Reciprocal Rank Fusion constant (standard default)
# Filtered-ANN recall guard (MULTI_INDUSTRY.md §5.1): HNSW's default `ef_search` (40) is
# below PREFETCH, and `WHERE industry = …` filters the candidate set *after* the index
# traversal — so a sparse vertical can be starved of dense hits. Raise the search-list size
# so the index explores enough nodes to fill PREFETCH within one vertical. SET LOCAL keeps
# it transaction-scoped (never leaks onto the pooled connection).
EF_SEARCH = 200


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
    published_at: datetime | None = None  # document publish date (None = unknown); drives recency
    industry: str = "esg"  # the vertical this chunk belongs to (multi-industry scope key)


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
            industry=getattr(row, "industry", "esg"),
            content_hash=getattr(row, "content_hash", ""),
            fresh=bool(getattr(row, "fresh", False)),
            published_at=getattr(row, "published_at", None),
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
    def hybrid_search(
        self, query: str, dense: list[float], top_k: int, industry: str = "esg"
    ) -> Fused:
        """Dense (pgvector) + BM25 (pg_search) prefetch fused with RRF — Quality tier.

        Both legs filter ``WHERE industry = :industry`` so retrieval never crosses
        verticals (MULTI_INDUSTRY.md §5.2)."""

    @abstractmethod
    def dense_search(self, dense: list[float], top_k: int, industry: str = "esg") -> Fused:
        """Dense-only ANN — the low-latency Fast tier. Scoped to ``industry``."""

    @abstractmethod
    def delete_url(self, url: str) -> int:
        """Drop all chunks for a page (clean re-ingest); return rows removed."""

    @abstractmethod
    def delete_ids(self, ids: list[str]) -> int:
        """Drop specific chunks by id (incremental crawl: prune vanished chunks)."""

    @abstractmethod
    def delete_source(self, source_url: str, industry: str = "esg") -> int:
        """Drop every chunk discovered under a seed — the seed page *and* all its
        deep-crawled pages share ``source_url`` — scoped to ``industry`` so removing a
        seed never touches another vertical. Returns rows removed (the chunk count the
        UI confirms). The `sources` row is dropped by ``corpus.delete_source``."""

    @abstractmethod
    def existing_hashes(self, url: str, industry: str = "esg") -> dict[str, str]:
        """``{chunk_id: content_hash}`` for a page — the diff base for incremental crawl."""

    @abstractmethod
    def prune_pages(self, source_url: str, keep_urls: list[str], industry: str = "esg") -> int:
        """Deep crawl: drop chunks under a seed whose page URL is no longer reachable.

        After a site recrawl, any page not in ``keep_urls`` has vanished (de-linked or
        gone); remove its chunks. Scoped to ``industry`` so verticals never prune each
        other. Returns rows removed.
        """

    @abstractmethod
    def stamp_published_at(self, url: str, published_at: datetime) -> int:
        """Set ``published_at`` on every chunk of a page (publication date is page-level).

        Lets an *incremental* recrawl backfill the date even on chunks whose content
        didn't change (so the per-chunk hash diff skipped their upsert). Returns rows set.
        """

    @abstractmethod
    def count(self, industry: str | None = None) -> int:
        """Indexed chunks (Corpus view stat / rail counter). ``None`` ⇒ every vertical;
        an ``industry`` scopes the count to that one."""


_UPSERT_SQL = text(
    """
    INSERT INTO chunks (id, url, source_url, title, org, source_type, text,
                        content_hash, token_count, dense, published_at, industry)
    VALUES (:id, :url, :source_url, :title, :org, :source_type, :text, :content_hash, :token_count,
            CAST(:dense AS vector(256)), :published_at, :industry)
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
        published_at = EXCLUDED.published_at,
        industry = EXCLUDED.industry,
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
        WHERE industry = :industry
        ORDER BY dense <=> CAST(:qvec AS vector(256))
        LIMIT :prefetch
    ),
    lexical AS (
        SELECT id, ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rnk
        FROM chunks
        WHERE industry = :industry
          AND id @@@ paradedb.match('text', :q)
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
           c.industry, c.published_at,
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
           industry, published_at,
           (crawled_at > now() - interval '7 days') AS fresh,
           1.0 - (dense <=> CAST(:qvec AS vector(256))) AS score
    FROM chunks
    WHERE industry = :industry
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
                "published_at": c.published_at,
                "industry": c.industry,
            }
            for c in chunks
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_SQL, params)
        return len(chunks)

    def hybrid_search(
        self, query: str, dense: list[float], top_k: int, industry: str = "esg"
    ) -> Fused:
        with self._engine.begin() as conn:
            conn.execute(text(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}"))
            rows = conn.execute(
                _HYBRID_SQL,
                {
                    "qvec": _vec_literal(dense),
                    "q": query,
                    "industry": industry,
                    "prefetch": PREFETCH,
                    "rrf_k": RRF_K,
                    "top_k": top_k,
                },
            ).all()
        hits = [_row_to_hit(r, float(r.score)) for r in rows]
        dense_n = sum(1 for r in rows if r.in_dense)
        bm25_n = sum(1 for r in rows if r.in_lex)
        return Fused(hits=hits, dense_n=dense_n, bm25_n=bm25_n)

    def dense_search(self, dense: list[float], top_k: int, industry: str = "esg") -> Fused:
        with self._engine.begin() as conn:
            conn.execute(text(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}"))
            rows = conn.execute(
                _DENSE_SQL,
                {"qvec": _vec_literal(dense), "industry": industry, "top_k": top_k},
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

    def delete_source(self, source_url: str, industry: str = "esg") -> int:
        with self._engine.begin() as conn:
            res = conn.execute(
                text(
                    "DELETE FROM chunks WHERE source_url = :src AND industry = :industry"
                ),
                {"src": source_url, "industry": industry},
            )
            return res.rowcount or 0

    def existing_hashes(self, url: str, industry: str = "esg") -> dict[str, str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, content_hash FROM chunks "
                    "WHERE url = :url AND industry = :industry"
                ),
                {"url": url, "industry": industry},
            ).all()
        return {r.id: r.content_hash for r in rows}

    def prune_pages(self, source_url: str, keep_urls: list[str], industry: str = "esg") -> int:
        with self._engine.begin() as conn:
            res = conn.execute(
                text(
                    "DELETE FROM chunks "
                    "WHERE source_url = :src AND industry = :industry "
                    "AND NOT (url = ANY(:keep))"
                ),
                {"src": source_url, "keep": keep_urls, "industry": industry},
            )
            return res.rowcount or 0

    def stamp_published_at(self, url: str, published_at: datetime) -> int:
        with self._engine.begin() as conn:
            res = conn.execute(
                text(
                    "UPDATE chunks SET published_at = :ts "
                    "WHERE url = :url AND published_at IS DISTINCT FROM :ts"
                ),
                {"url": url, "ts": published_at},
            )
            return res.rowcount or 0

    def count(self, industry: str | None = None) -> int:
        with self._engine.connect() as conn:
            if industry is None:
                return int(conn.execute(text("SELECT count(*) FROM chunks")).scalar_one())
            return int(
                conn.execute(
                    text("SELECT count(*) FROM chunks WHERE industry = :industry"),
                    {"industry": industry},
                ).scalar_one()
            )


_store: PgVectorStore | None = None


def get_store() -> PgVectorStore:
    """Process-wide store singleton (the one VectorStore impl)."""
    global _store
    if _store is None:
        _store = PgVectorStore()
    return _store
