"""Corpus state — the `sources` table + index stats behind the Corpus view (§8.4).

Read/write helpers for seed registration, crawl-status transitions, and the stat
cards. Kept separate from ``ingest/`` (the write pipeline) so the API's read path
doesn't pull in crawl4ai/torch.
"""

from __future__ import annotations

from sqlalchemy import text

from . import db
from .search.embed import MODEL_NAME
from .search.store import EMBED_DIM, get_store


def upsert_source(
    url: str, source_type: str, org: str | None, cadence: str, industry: str = "esg"
) -> None:
    """Register/refresh a seed's metadata without disturbing its status/counts."""
    with db.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO sources (url, source_type, org, cadence, industry)
                VALUES (:url, :source_type, :org, :cadence, :industry)
                ON CONFLICT (url) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    org = EXCLUDED.org,
                    cadence = EXCLUDED.cadence,
                    industry = EXCLUDED.industry
                """
            ),
            {
                "url": url,
                "source_type": source_type,
                "org": org,
                "cadence": cadence,
                "industry": industry,
            },
        )


def delete_source(url: str, industry: str = "esg") -> int:
    """Remove a seed from a vertical: drop every chunk it produced (seed page + all
    deep-crawled pages, matched by ``source_url``) and its `sources` row. Industry-scoped
    so you can only delete from the vertical you're in. Returns chunks removed.

    Re-adding the seed re-pays its crawl+embed, so the UI confirms before calling this
    (MULTI_INDUSTRY.md §5.7)."""
    removed = get_store().delete_source(url, industry)
    with db.get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM sources WHERE url = :url AND industry = :industry"),
            {"url": url, "industry": industry},
        )
    return removed


def set_status(url: str, status: str, error: str | None = None) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE sources SET status = :status, error = :error WHERE url = :url"),
            {"url": url, "status": status, "error": error},
        )


def finish_source(url: str, pages: int, chunks: int) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE sources
                SET status = 'done', pages = :pages, chunks = :chunks,
                    last_crawl = now(), error = NULL
                WHERE url = :url
                """
            ),
            {"url": url, "pages": pages, "chunks": chunks},
        )


def save_validators(url: str, etag: str | None, last_modified: str | None) -> None:
    """Persist HTTP ETag / Last-Modified for the next conditional crawl."""
    with db.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE sources SET etag = :etag, last_modified = :lm WHERE url = :url"),
            {"url": url, "etag": etag, "lm": last_modified},
        )


def get_validators(url: str) -> tuple[str | None, str | None]:
    with db.get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT etag, last_modified FROM sources WHERE url = :url"), {"url": url}
        ).first()
    return (row.etag, row.last_modified) if row else (None, None)


def touch_unmodified(url: str) -> None:
    """304 path: page unchanged — record the crawl happened, keep counts as-is."""
    with db.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE sources
                SET status = 'done', last_crawl = now(), error = NULL
                WHERE url = :url
                """
            ),
            {"url": url},
        )


# Recrawl rhythm: cadence label → SQL interval. Adaptive freshness (SPEC §7) — news
# churns hourly, frameworks monthly. A source is "due" when never crawled or its
# last crawl predates its cadence window.
def sources_due(industry: str | None = None) -> list[dict]:
    """Seeds whose cadence window has elapsed (or that were never crawled).

    ``industry`` scopes to one vertical (so ``--due`` recrawls only the active corpus);
    ``None`` considers every vertical.
    """
    with db.get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT url, source_type, org, cadence, status, pages, chunks,
                       last_crawl, error
                FROM sources
                WHERE (CAST(:industry AS text) IS NULL OR industry = :industry)
                  AND (last_crawl IS NULL
                   OR last_crawl < now() - (CASE cadence
                        WHEN 'hourly' THEN interval '1 hour'
                        WHEN 'daily'  THEN interval '1 day'
                        WHEN 'weekly' THEN interval '7 days'
                        ELSE               interval '30 days' END))
                ORDER BY source_type, url
                """
            ),
            {"industry": industry},
        ).all()
    return [
        {
            "url": r.url,
            "source_type": r.source_type,
            "org": r.org,
            "cadence": r.cadence,
            "status": r.status,
            "pages": r.pages,
            "chunks": r.chunks,
            "last_crawl": r.last_crawl.isoformat() if r.last_crawl else None,
            "error": r.error,
        }
        for r in rows
    ]


def list_sources(industry: str | None = None) -> list[dict]:
    """Registered seeds, optionally scoped to one vertical (``None`` ⇒ all)."""
    with db.get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT url, source_type, org, cadence, status, pages, chunks,
                       last_crawl, error
                FROM sources
                WHERE (CAST(:industry AS text) IS NULL OR industry = :industry)
                ORDER BY source_type, url
                """
            ),
            {"industry": industry},
        ).all()
    return [
        {
            "url": r.url,
            "source_type": r.source_type,
            "org": r.org,
            "cadence": r.cadence,
            "status": r.status,
            "pages": r.pages,
            "chunks": r.chunks,
            "last_crawl": r.last_crawl.isoformat() if r.last_crawl else None,
            "error": r.error,
        }
        for r in rows
    ]


def industries_loaded() -> set[str]:
    """The verticals that have at least one registered seed — i.e. are "loaded" and can be
    searched. Drives the `loaded` flag in the setup menu (MULTI_INDUSTRY.md §5.5)."""
    with db.get_engine().connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT industry FROM sources")).all()
    return {r.industry for r in rows}


def stats(industry: str | None = None) -> dict:
    """Index stat cards, optionally scoped to one vertical.

    ``index_bytes`` stays whole-table — ``pg_total_relation_size`` measures physical
    storage, which isn't partitioned per vertical under Model A (MULTI_INDUSTRY.md §5.1).
    Chunk/source/page counts honour ``industry`` so the Corpus view reflects the active
    vertical.
    """
    with db.get_engine().connect() as conn:
        sources = int(
            conn.execute(
                text(
                    "SELECT count(*) FROM sources "
                    "WHERE (CAST(:industry AS text) IS NULL OR industry = :industry)"
                ),
                {"industry": industry},
            ).scalar_one()
        )
        pages = int(
            conn.execute(
                text(
                    "SELECT COALESCE(sum(pages), 0) FROM sources "
                    "WHERE (CAST(:industry AS text) IS NULL OR industry = :industry)"
                ),
                {"industry": industry},
            ).scalar_one()
        )
        index_bytes = int(
            conn.execute(text("SELECT pg_total_relation_size('chunks')")).scalar_one()
        )
    return {
        "chunks": get_store().count(industry),
        "sources": sources,
        "pages": pages,
        "index_bytes": index_bytes,
        "embed_model": MODEL_NAME,
        "embed_dims": EMBED_DIM,
    }
